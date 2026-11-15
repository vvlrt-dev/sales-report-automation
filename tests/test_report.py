from pathlib import Path

import openpyxl
import pandas as pd
import pytest

from sales_report import metrics
from sales_report.cli import build_parser, main, run
from sales_report.load import SalesDataError, load_sales, map_columns

ROOT = Path(__file__).resolve().parent.parent


def write_csv(tmp_path, text, name="sales.csv"):
    path = tmp_path / name
    path.write_text(text.strip() + "\n", encoding="utf-8")
    return path


SMALL = """
date,order_id,product,category,quantity,unit_price
2026-03-01 10:00,A1,Plov,Mains,2,9.50
2026-03-01 10:00,A1,Tea,Drinks,1,2.50
2026-03-01 18:30,A2,Samsa,Bakery,3,3.00
2026-03-03 12:00,A3,Plov,Mains,1,9.50
"""


# ---- loading ----------------------------------------------------------------

def test_column_aliases_are_recognised():
    mapping = map_columns(["Order Date", "Receipt ID", "Item", "Qty", "Price"])
    assert mapping == {"date": "Order Date", "order_id": "Receipt ID", "product": "Item",
                       "quantity": "Qty", "unit_price": "Price"}


def test_russian_headers_are_recognised():
    mapping = map_columns(["Дата", "Номер чека", "Товар", "Количество", "Сумма"])
    assert set(mapping) == {"date", "order_id", "product", "quantity", "revenue"}


def test_missing_required_column_explains_what_is_wrong():
    with pytest.raises(SalesDataError, match="order_id"):
        map_columns(["date", "product", "revenue"])


def test_needs_revenue_or_quantity_and_price():
    with pytest.raises(SalesDataError, match="revenue"):
        map_columns(["date", "order_id", "product", "quantity"])


def test_revenue_is_computed_from_quantity_and_price(tmp_path):
    data = load_sales(write_csv(tmp_path, SMALL)).data
    assert data["revenue"].tolist() == [19.0, 2.5, 9.0, 9.5]


def test_semicolon_csv_with_decimal_commas_and_currency(tmp_path):
    path = write_csv(tmp_path, """
Date;Receipt;Item;Qty;Total
01.03.2026;1;Plov;1;"9,50 $"
02.03.2026;2;Tea;2;"$5,00"
""")
    loaded = load_sales(path, dayfirst=True)
    assert loaded.data["revenue"].tolist() == [9.5, 5.0]
    assert loaded.data["date"].dt.day.tolist() == [1, 2]


def test_bad_rows_are_reported_not_silently_used(tmp_path):
    path = write_csv(tmp_path, SMALL + """
yesterday,A9,Plov,Mains,1,9.50
2026-03-02 11:00,A10,,Mains,1,9.50
2026-03-02 11:00,A11,Tea,Drinks,0,2.50
2026-03-02 11:00,A12,Tea,Drinks,1,abc
2026-03-03 12:00,A3,Plov,Mains,1,9.50
""")
    loaded = load_sales(path)
    assert len(loaded.data) == 4
    assert loaded.rejected["reason"].tolist() == [
        "unreadable date", "missing product", "quantity missing or not positive",
        "revenue missing or not a number", "exact duplicate row"]
    assert loaded.rejected["source_row"].tolist() == [6, 7, 8, 9, 10]


def test_keep_duplicates_option(tmp_path):
    path = write_csv(tmp_path, SMALL + "2026-03-03 12:00,A3,Plov,Mains,1,9.50")
    assert len(load_sales(path, drop_duplicates=False).data) == 5


def test_unsupported_file_type(tmp_path):
    path = tmp_path / "sales.pdf"
    path.write_bytes(b"%PDF")
    with pytest.raises(SalesDataError, match="Unsupported"):
        load_sales(path)


# ---- metrics ----------------------------------------------------------------

def test_daily_includes_days_without_sales(tmp_path):
    by_day = metrics.daily(load_sales(write_csv(tmp_path, SMALL)).data)
    assert by_day["day"].dt.day.tolist() == [1, 2, 3]
    assert by_day["revenue"].tolist() == [30.5, 0.0, 9.5]
    assert by_day["orders"].tolist() == [2, 0, 1]
    assert by_day["average_check"].iloc[0] == 15.25
    assert pd.isna(by_day["average_check"].iloc[1])


def test_top_products_and_shares(tmp_path):
    top = metrics.top_products(load_sales(write_csv(tmp_path, SMALL)).data, n=2)
    assert top["product"].tolist() == ["Plov", "Samsa"]
    assert top["revenue"].tolist() == [28.5, 9.0]
    assert top["quantity"].tolist() == [3, 3]
    assert top["share"].iloc[0] == pytest.approx(28.5 / 40)


def test_summary_average_check(tmp_path):
    data = load_sales(write_csv(tmp_path, SMALL)).data
    summary = metrics.summarize(data, metrics.daily(data))
    assert summary.revenue == 40.0
    assert summary.orders == 3
    assert summary.average_check == 13.33
    assert summary.best_day.day == 1
    assert summary.days_with_sales == 2


# ---- end to end -------------------------------------------------------------

def test_cli_writes_excel_and_charts(tmp_path):
    out = tmp_path / "out"
    files = run(build_parser().parse_args([str(write_csv(tmp_path, SMALL)), "--out", str(out), "--currency", "€"]))
    for key in ("revenue", "top", "check"):
        assert files[key].stat().st_size > 10_000
        assert files[key].read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"

    book = openpyxl.load_workbook(files["xlsx"])
    assert book.sheetnames == ["Summary", "Daily", "Top products", "Data issues", "Clean data"]
    summary = {r[1]: r[2] for r in book["Summary"].iter_rows(min_row=5, max_row=11, values_only=True)}
    assert summary["Revenue"] == "€40.00"
    assert summary["Average check"] == "€13.33"
    daily = list(book["Daily"].iter_rows(min_row=2, values_only=True))
    assert [row[3] for row in daily] == [30.5, 0, 9.5]
    assert book["Top products"]["B2"].value == "Plov"
    assert "No issues" in book["Data issues"]["A1"].value
    assert len(book["Summary"]._images) == 3


def test_cli_date_filter(tmp_path):
    out = tmp_path / "out"
    files = run(build_parser().parse_args([str(write_csv(tmp_path, SMALL)), "--out", str(out), "--from", "2026-03-02"]))
    assert files["xlsx"].name == "sales_report_2026-03-03_2026-03-03.xlsx"


def test_cli_reports_errors_without_traceback(tmp_path, capsys):
    assert main([str(tmp_path / "missing.csv")]) == 1
    assert "File not found" in capsys.readouterr().err


def test_bundled_examples_run(tmp_path):
    for name in ("sales_sample.csv", "sales_sample_ru.xlsx"):
        files = run(build_parser().parse_args([str(ROOT / "examples" / name), "--out", str(tmp_path / name)]))
        assert files["xlsx"].exists()
