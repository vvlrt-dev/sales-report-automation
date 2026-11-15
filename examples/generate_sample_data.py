"""Generate the fictional example data in this folder.

    python examples/generate_sample_data.py

Writes:
  sales_sample.csv     two months of POS line items for a fictional cafe,
                       with a handful of deliberately broken rows to show the "Data issues" sheet
  sales_sample_ru.xlsx two weeks of the same data with Russian column headers,
                       to show automatic column mapping
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
RNG = np.random.default_rng(2026)

MENU = [  # product, category, price, popularity weight
    ("Tashkent plov", "Mains", 9.50, 10),
    ("Lagman", "Mains", 8.00, 6),
    ("Lamb shashlik", "Mains", 11.00, 5),
    ("Manti (5 pcs)", "Mains", 7.50, 5),
    ("Beef samsa", "Bakery", 3.00, 9),
    ("Pumpkin samsa", "Bakery", 2.80, 4),
    ("Tandoor bread", "Bakery", 1.50, 7),
    ("Achichuk salad", "Salads", 3.50, 5),
    ("Shakarob salad", "Salads", 3.20, 3),
    ("Green tea pot", "Drinks", 2.50, 8),
    ("Fruit compote", "Drinks", 2.00, 5),
    ("Ayran", "Drinks", 2.20, 3),
    ("Chak-chak", "Desserts", 3.80, 3),
    ("Halva plate", "Desserts", 4.20, 2),
]
WEEKDAY_ORDERS = {0: 62, 1: 66, 2: 70, 3: 72, 4: 88, 5: 104, 6: 96}


def generate(start: date, end: date) -> pd.DataFrame:
    weights = np.array([m[3] for m in MENU], dtype=float)
    weights /= weights.sum()
    rows, order_no = [], 10000
    day = start
    while day <= end:
        n_orders = int(RNG.poisson(WEEKDAY_ORDERS[day.weekday()] * (1.12 if day.day <= 3 else 1.0)))
        for _ in range(n_orders):
            order_no += 1
            hour = int(RNG.choice([11, 12, 13, 14, 17, 18, 19, 20], p=[.08, .2, .2, .08, .1, .14, .13, .07]))
            ts = datetime(day.year, day.month, day.day, hour, int(RNG.integers(0, 60)))
            picks = RNG.choice(len(MENU), size=int(RNG.integers(1, 5)), replace=False, p=weights)
            for i in picks:
                product, category, price, _ = MENU[i]
                qty = int(RNG.choice([1, 1, 1, 2, 2, 3]))
                rows.append({"order_date": ts.strftime("%Y-%m-%d %H:%M"), "receipt_id": f"R{order_no}",
                             "item": product, "category": category, "qty": qty,
                             "unit_price": f"{price:.2f}", "line_total": f"{price * qty:.2f}"})
        day += timedelta(days=1)
    return pd.DataFrame(rows)


def add_messy_rows(df: pd.DataFrame) -> pd.DataFrame:
    broken = [
        {"order_date": "not a date", "receipt_id": "R99901", "item": "Beef samsa", "category": "Bakery",
         "qty": 2, "unit_price": "3.00", "line_total": "6.00"},
        {"order_date": "2026-10-12 13:05", "receipt_id": "R99902", "item": "", "category": "Mains",
         "qty": 1, "unit_price": "9.50", "line_total": "9.50"},
        {"order_date": "2026-10-14 19:40", "receipt_id": "R99903", "item": "Lagman", "category": "Mains",
         "qty": 1, "unit_price": "8.00", "line_total": "-8.00"},
        {"order_date": "2026-10-20 12:10", "receipt_id": "R99904", "item": "Green tea pot", "category": "Drinks",
         "qty": 0, "unit_price": "2.50", "line_total": "0.00"},
    ]
    duplicate = df.iloc[[120]].to_dict("records")
    return pd.concat([df, pd.DataFrame(broken + duplicate)], ignore_index=True)


if __name__ == "__main__":
    sales = generate(date(2026, 9, 1), date(2026, 10, 31))
    add_messy_rows(sales).to_csv(HERE / "sales_sample.csv", index=False)

    two_weeks = sales[sales["order_date"] < "2026-09-15"].rename(columns={
        "order_date": "Дата", "receipt_id": "Номер чека", "item": "Товар", "category": "Категория",
        "qty": "Количество", "unit_price": "Цена", "line_total": "Сумма"})
    for col in ("Цена", "Сумма"):
        two_weeks[col] = two_weeks[col].astype(float)
    two_weeks.to_excel(HERE / "sales_sample_ru.xlsx", index=False)
    print(f"sales_sample.csv: {len(sales) + 5} rows; sales_sample_ru.xlsx: {len(two_weeks)} rows")
