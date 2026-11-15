"""Command line entry point.

    python -m sales_report examples/sales_sample.csv
    python -m sales_report export.xlsx --out reports/ --currency "€" --top 15
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from . import charts, metrics
from .excel import write_report
from .load import SalesDataError, load_sales


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sales_report", description="Build an Excel + PNG sales report from a CSV/Excel export.")
    p.add_argument("input", type=Path, help="Sales export (.csv or .xlsx)")
    p.add_argument("--out", type=Path, default=Path("report"), help="Output folder (default: ./report)")
    p.add_argument("--title", default="Sales report", help="Report title")
    p.add_argument("--currency", default="$", help="Currency symbol for labels (default: $)")
    p.add_argument("--top", type=int, default=10, help="How many top products to show (default: 10)")
    p.add_argument("--sheet", help="Sheet name for Excel input (default: first sheet)")
    p.add_argument("--from", dest="date_from", help="Only include sales on or after YYYY-MM-DD")
    p.add_argument("--to", dest="date_to", help="Only include sales on or before YYYY-MM-DD")
    p.add_argument("--dayfirst", action="store_true", help="Dates are written day first (31/12/2026)")
    p.add_argument("--keep-duplicates", action="store_true", help="Keep identical rows instead of skipping them")
    return p


def run(args: argparse.Namespace) -> dict[str, Path]:
    loaded = load_sales(args.input, sheet=args.sheet, dayfirst=args.dayfirst,
                        drop_duplicates=not args.keep_duplicates)
    data = loaded.data
    if args.date_from:
        data = data[data["date"] >= pd.Timestamp(args.date_from)]
    if args.date_to:
        data = data[data["date"] < pd.Timestamp(args.date_to) + pd.Timedelta(days=1)]
    if data.empty:
        raise SalesDataError("No sales in the selected date range.")

    by_day = metrics.daily(data)
    top = metrics.top_products(data, args.top)
    summary = metrics.summarize(data, by_day)
    categories = metrics.by_category(data)

    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    png = {
        "revenue": charts.revenue_by_day(by_day, out / "revenue_by_day.png", args.currency),
        "top": charts.top_products_chart(top, out / "top_products.png", args.currency),
        "check": charts.average_check_chart(by_day, out / "average_check.png", args.currency, summary.average_check),
    }
    stem = f"sales_report_{summary.date_from:%Y-%m-%d}_{summary.date_to:%Y-%m-%d}"
    xlsx = write_report(out / f"{stem}.xlsx", title=args.title, summary=summary, by_day=by_day, top=top,
                        categories=categories, data=data, rejected=loaded.rejected, charts=png,
                        currency=args.currency, source_name=args.input.name)

    print(f"{args.title}: {summary.date_from:%d %b %Y} – {summary.date_to:%d %b %Y}")
    for label, value in summary.as_rows(f"{args.currency}{{:,.2f}}")[1:]:
        print(f"  {label:<16}{value}")
    if len(loaded.rejected):
        print(f"  Skipped rows    {len(loaded.rejected)} (listed on the 'Data issues' sheet)")
    print(f"\nSaved:\n  {xlsx}\n" + "\n".join(f"  {p}" for p in png.values()))
    return {"xlsx": xlsx, **png}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        run(args)
    except SalesDataError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
