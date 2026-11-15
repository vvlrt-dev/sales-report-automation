"""Report numbers: revenue by day, top products, average check."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class Summary:
    date_from: pd.Timestamp
    date_to: pd.Timestamp
    revenue: float
    orders: int
    items_sold: float
    average_check: float
    best_day: pd.Timestamp
    best_day_revenue: float
    days_with_sales: int

    def as_rows(self, money: str) -> list[tuple[str, str]]:
        return [
            ("Period", f"{self.date_from:%d %b %Y} – {self.date_to:%d %b %Y}"),
            ("Revenue", money.format(self.revenue)),
            ("Orders", f"{self.orders:,}"),
            ("Average check", money.format(self.average_check)),
            ("Items sold", f"{self.items_sold:,.0f}"),
            ("Best day", f"{self.best_day:%a %d %b} · {money.format(self.best_day_revenue)}"),
            ("Days with sales", f"{self.days_with_sales}"),
        ]


def daily(data: pd.DataFrame) -> pd.DataFrame:
    """One row per calendar day in the period, including days with no sales."""
    by_day = data.assign(day=data["date"].dt.normalize()).groupby("day").agg(
        revenue=("revenue", "sum"),
        orders=("order_id", "nunique"),
        items=("quantity", "sum"),
    )
    full_range = pd.date_range(by_day.index.min(), by_day.index.max(), freq="D", name="day")
    by_day = by_day.reindex(full_range, fill_value=0)
    by_day["average_check"] = (by_day["revenue"] / by_day["orders"].where(by_day["orders"] > 0)).round(2)
    by_day["revenue_7d_avg"] = by_day["revenue"].rolling(7, min_periods=1).mean().round(2)
    by_day["revenue"] = by_day["revenue"].round(2)
    return by_day.reset_index()


def top_products(data: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    cols = ["product"] + (["category"] if "category" in data else [])
    grouped = data.groupby(cols, as_index=False).agg(
        revenue=("revenue", "sum"),
        quantity=("quantity", "sum"),
        orders=("order_id", "nunique"),
    )
    total = grouped["revenue"].sum()
    grouped["share"] = grouped["revenue"] / total if total else 0.0
    grouped = grouped.sort_values(["revenue", "quantity"], ascending=False).head(n).reset_index(drop=True)
    grouped.insert(0, "rank", range(1, len(grouped) + 1))
    grouped["revenue"] = grouped["revenue"].round(2)
    return grouped


def by_category(data: pd.DataFrame) -> pd.DataFrame | None:
    if "category" not in data:
        return None
    grouped = data.groupby("category", as_index=False).agg(revenue=("revenue", "sum"), quantity=("quantity", "sum"))
    grouped["share"] = grouped["revenue"] / grouped["revenue"].sum()
    grouped["revenue"] = grouped["revenue"].round(2)
    return grouped.sort_values("revenue", ascending=False).reset_index(drop=True)


def summarize(data: pd.DataFrame, by_day: pd.DataFrame) -> Summary:
    orders = data["order_id"].nunique()
    revenue = round(float(data["revenue"].sum()), 2)
    best = by_day.loc[by_day["revenue"].idxmax()]
    return Summary(
        date_from=by_day["day"].min(),
        date_to=by_day["day"].max(),
        revenue=revenue,
        orders=int(orders),
        items_sold=float(data["quantity"].sum()),
        average_check=round(revenue / orders, 2) if orders else 0.0,
        best_day=best["day"],
        best_day_revenue=float(best["revenue"]),
        days_with_sales=int((by_day["orders"] > 0).sum()),
    )
