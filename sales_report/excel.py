"""Excel report built with XlsxWriter: summary with charts, daily table, top products, data issues."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .metrics import Summary

HEADER = {"bold": True, "font_color": "#FFFFFF", "bg_color": "#2F6F8F", "border": 0, "valign": "vcenter"}


def write_report(path: Path, *, title: str, summary: Summary, by_day: pd.DataFrame, top: pd.DataFrame,
                 categories: pd.DataFrame | None, data: pd.DataFrame, rejected: pd.DataFrame,
                 charts: dict[str, Path], currency: str, source_name: str) -> Path:
    money_fmt = f'"{currency}"#,##0.00'
    with pd.ExcelWriter(path, engine="xlsxwriter", datetime_format="yyyy-mm-dd", date_format="yyyy-mm-dd") as writer:
        book = writer.book
        f = {
            "title": book.add_format({"bold": True, "font_size": 18, "font_color": "#1F2A37"}),
            "muted": book.add_format({"font_color": "#6B7785", "italic": True}),
            "label": book.add_format({"font_color": "#6B7785"}),
            "kpi": book.add_format({"bold": True, "font_size": 12}),
            "section": book.add_format({"bold": True, "font_size": 12, "font_color": "#2F6F8F"}),
            "header": book.add_format(HEADER),
            "money": book.add_format({"num_format": money_fmt}),
            "int": book.add_format({"num_format": "#,##0"}),
            "pct": book.add_format({"num_format": "0.0%"}),
            "date": book.add_format({"num_format": "ddd dd mmm yyyy"}),
        }

        # ---- Summary -------------------------------------------------------
        ws = book.add_worksheet("Summary")
        writer.sheets["Summary"] = ws
        ws.hide_gridlines(2)
        ws.set_landscape()
        ws.set_paper(9)  # A4
        ws.fit_to_pages(1, 1)
        ws.set_column("A:A", 2)
        ws.set_column("B:B", 20)
        ws.set_column("C:C", 30)
        ws.write("B2", title, f["title"])
        ws.write("B3", f"Source: {source_name} · {len(data):,} sales lines"
                       + (f" · {len(rejected):,} rows skipped (see Data issues)" if len(rejected) else ""), f["muted"])
        money = f"{currency}{{:,.2f}}"
        row = 4
        for label, value in summary.as_rows(money):
            ws.write(row, 1, label, f["label"])
            ws.write(row, 2, value, f["kpi"])
            row += 1

        if categories is not None:
            row += 1
            ws.write(row, 1, "Revenue by category", f["section"])
            row += 1
            for col, head in enumerate(("Category", "Revenue", "Share")):
                ws.write(row, 1 + col, head, f["header"])
            ws.set_column("D:D", 10)
            for _, c in categories.iterrows():
                row += 1
                ws.write(row, 1, c["category"])
                ws.write_number(row, 2, c["revenue"], f["money"])
                ws.write_number(row, 3, c["share"], f["pct"])

        ws.insert_image("F2", str(charts["revenue"]), {"x_scale": 0.52, "y_scale": 0.52})
        ws.insert_image("F21", str(charts["top"]), {"x_scale": 0.52, "y_scale": 0.52})
        ws.insert_image("F" + str(23 + int(len(top) * 0.95) + 4), str(charts["check"]), {"x_scale": 0.52, "y_scale": 0.52})

        # ---- Daily ---------------------------------------------------------
        daily_out = by_day.rename(columns={
            "day": "Date", "orders": "Orders", "items": "Items sold", "revenue": "Revenue",
            "average_check": "Average check", "revenue_7d_avg": "Revenue, 7-day avg"})
        daily_out = daily_out[["Date", "Orders", "Items sold", "Revenue", "Average check", "Revenue, 7-day avg"]]
        _table(writer, daily_out, "Daily", f, widths=[18, 10, 12, 14, 15, 18],
               formats=[f["date"], f["int"], f["int"], f["money"], f["money"], f["money"]])
        ws = writer.sheets["Daily"]
        n = len(daily_out)
        chart = book.add_chart({"type": "column"})
        chart.add_series({"name": "Revenue", "categories": ["Daily", 1, 0, n, 0], "values": ["Daily", 1, 3, n, 3],
                          "fill": {"color": "#2F6F8F"}, "gap": 40})
        line = book.add_chart({"type": "line"})
        line.add_series({"name": "7-day average", "categories": ["Daily", 1, 0, n, 0], "values": ["Daily", 1, 5, n, 5],
                         "line": {"color": "#E0892F", "width": 2.25}})
        chart.combine(line)
        chart.set_title({"name": "Revenue by day"})
        chart.set_x_axis({"date_axis": True, "num_format": "dd mmm", "major_unit": 7, "major_unit_type": "days"})
        chart.set_y_axis({"num_format": f'"{currency}"#,##0', "major_gridlines": {"visible": True, "line": {"color": "#E5E9EE"}}})
        chart.set_legend({"position": "bottom"})
        chart.set_size({"width": 820, "height": 360})
        ws.insert_chart("H2", chart)

        # ---- Top products --------------------------------------------------
        top_out = top.rename(columns={"rank": "#", "product": "Product", "category": "Category", "revenue": "Revenue",
                                      "quantity": "Quantity", "orders": "Orders", "share": "Share of revenue"})
        cols = ["#", "Product"] + (["Category"] if "Category" in top_out else []) + ["Quantity", "Orders", "Revenue", "Share of revenue"]
        top_out = top_out[cols]
        fmt_by_col = {"#": f["int"], "Product": None, "Category": None, "Quantity": f["int"], "Orders": f["int"],
                      "Revenue": f["money"], "Share of revenue": f["pct"]}
        width_by_col = {"#": 5, "Product": 28, "Category": 18, "Quantity": 11, "Orders": 10, "Revenue": 14, "Share of revenue": 16}
        _table(writer, top_out, "Top products", f, widths=[width_by_col[c] for c in cols],
               formats=[fmt_by_col[c] for c in cols])

        # ---- Data issues ---------------------------------------------------
        if len(rejected):
            issues = rejected.rename(columns={"source_row": "Row in file", "reason": "Reason"})
            _table(writer, issues, "Data issues", f, widths=[12, 32] + [16] * (issues.shape[1] - 2))
        else:
            ws = book.add_worksheet("Data issues")
            ws.write("A1", "No issues found: every row was used in the report.", f["muted"])

        # ---- Clean data ----------------------------------------------------
        clean_cols = [c for c in ("date", "order_id", "product", "category", "quantity", "unit_price", "revenue") if c in data]
        clean_out = data[clean_cols].rename(columns=lambda c: c.replace("_", " ").capitalize())
        clean_fmt = {"Date": f["date"], "Quantity": f["int"], "Unit price": f["money"], "Revenue": f["money"]}
        _table(writer, clean_out, "Clean data", f, widths=[18, 14, 26, 18, 10, 12, 12][:len(clean_cols)],
               formats=[clean_fmt.get(c) for c in clean_out.columns])
    return path


def _table(writer, df: pd.DataFrame, sheet: str, f: dict, widths: list[int], formats: list | None = None) -> None:
    df.to_excel(writer, sheet_name=sheet, index=False)
    ws = writer.sheets[sheet]
    for col, name in enumerate(df.columns):
        ws.write(0, col, name, f["header"])
        ws.set_column(col, col, widths[col] if col < len(widths) else 14, formats[col] if formats else None)
    ws.set_row(0, 22)
    ws.freeze_panes(1, 0)
    ws.repeat_rows(0)
    ws.fit_to_pages(1, 0)  # print to page width
    ws.autofilter(0, 0, len(df), len(df.columns) - 1)
