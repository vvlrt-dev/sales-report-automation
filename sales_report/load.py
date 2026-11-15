"""Read a sales export, map its columns to a standard schema and clean the rows."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

# Standard column -> accepted header spellings (compared after lower-casing and stripping symbols).
COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "date": ("date", "order date", "sale date", "datetime", "created at", "timestamp", "дата"),
    "order_id": ("order id", "order", "order no", "order number", "receipt", "receipt id", "check id",
                 "invoice", "transaction id", "номер чека", "чек"),
    "product": ("product", "item", "product name", "item name", "sku name", "товар", "наименование"),
    "category": ("category", "group", "product category", "категория"),
    "quantity": ("quantity", "qty", "units", "count", "количество", "кол во"),
    "unit_price": ("unit price", "price", "price each", "цена"),
    "revenue": ("revenue", "total", "amount", "line total", "sales", "sum", "сумма", "выручка"),
}
REQUIRED = ("date", "order_id", "product")


class SalesDataError(ValueError):
    """The file can't be turned into a report; the message explains why."""


@dataclass
class LoadResult:
    data: pd.DataFrame          # clean rows, standard columns
    rejected: pd.DataFrame      # dropped rows with a "reason" column
    column_map: dict[str, str]  # standard name -> original header


def _normalize(header: str) -> str:
    return re.sub(r"[^\w]+", " ", str(header).lower(), flags=re.UNICODE).replace("_", " ").strip()


def map_columns(columns: list[str]) -> dict[str, str]:
    normalized = {_normalize(c): c for c in columns}
    mapping = {}
    for standard, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                mapping[standard] = normalized[alias]
                break
    missing = [c for c in REQUIRED if c not in mapping]
    if missing:
        raise SalesDataError(
            f"Missing required column(s): {', '.join(missing)}. Found: {', '.join(map(str, columns))}"
        )
    if "revenue" not in mapping and not {"quantity", "unit_price"} <= mapping.keys():
        raise SalesDataError("Need either a revenue/total column or both quantity and unit price columns.")
    return mapping


def read_table(path: Path, sheet: str | int | None = None) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise SalesDataError(f"File not found: {path}")
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xlsm", ".xls"):
        return pd.read_excel(path, sheet_name=sheet if sheet is not None else 0)
    if suffix in (".csv", ".txt"):
        # sep=None sniffs commas vs semicolons (common in European exports)
        return pd.read_csv(path, sep=None, engine="python", encoding="utf-8-sig")
    raise SalesDataError(f"Unsupported file type '{suffix}'. Use .csv or .xlsx.")


def _to_number(series: pd.Series) -> pd.Series:
    if series.dtype.kind in "if":
        return series.astype(float)
    cleaned = (series.astype(str).str.strip()
               .str.replace(r"[^\d,.\-]", "", regex=True)       # drop currency signs and spaces
               .str.replace(r"^(-?\d+),(\d{1,2})$", r"\1.\2", regex=True)  # 12,50 -> 12.50
               .str.replace(",", "", regex=False))               # 1,250.00 -> 1250.00
    return pd.to_numeric(cleaned, errors="coerce")


def clean(raw: pd.DataFrame, column_map: dict[str, str], dayfirst: bool = False,
          drop_duplicates: bool = True) -> LoadResult:
    df = pd.DataFrame({std: raw[orig] for std, orig in column_map.items()})
    df["source_row"] = raw.index + 2  # spreadsheet row number (header is row 1)

    df["date"] = pd.to_datetime(df["date"], errors="coerce", dayfirst=dayfirst, format="mixed")
    for col in ("order_id", "product"):  # fillna first: pandas 3 keeps NaN through astype(str)
        df[col] = df[col].fillna("").astype(str).str.strip()
    df["order_id"] = df["order_id"].str.replace(r"^(\d+)\.0$", r"\1", regex=True)  # 10001.0 from Excel -> 10001
    if "category" in df:
        df["category"] = df["category"].fillna("Uncategorized").astype(str).str.strip()
    df["quantity"] = _to_number(df["quantity"]) if "quantity" in df else 1.0
    if "unit_price" in df:
        df["unit_price"] = _to_number(df["unit_price"])
    if "revenue" in df:
        df["revenue"] = _to_number(df["revenue"])
        if "unit_price" in df:
            df["revenue"] = df["revenue"].fillna(df["quantity"] * df["unit_price"])
    else:
        df["revenue"] = df["quantity"] * df["unit_price"]

    reasons = pd.Series("", index=df.index)
    checks = [
        (df["date"].isna(), "unreadable date"),
        (df["order_id"].isin(["", "nan", "None"]), "missing order id"),
        (df["product"].isin(["", "nan", "None"]), "missing product"),
        (df["quantity"].isna() | (df["quantity"] <= 0), "quantity missing or not positive"),
        (df["revenue"].isna(), "revenue missing or not a number"),
        (df["revenue"] < 0, "negative revenue (refund)"),
    ]
    for mask, reason in checks:
        reasons = reasons.where(~mask | (reasons != ""), reason)

    if drop_duplicates:  # identical lines are usually a double export; disable if your POS splits lines
        duplicate = df.drop(columns="source_row").duplicated(keep="first") & (reasons == "")
        reasons = reasons.where(~duplicate, "exact duplicate row")

    bad = reasons != ""
    rejected = raw.loc[bad].copy()
    rejected.insert(0, "reason", reasons[bad])
    rejected.insert(0, "source_row", df.loc[bad, "source_row"])

    data = df.loc[~bad].drop(columns="source_row").reset_index(drop=True)
    data["revenue"] = data["revenue"].round(2)
    if data.empty:
        raise SalesDataError("No valid sales rows left after cleaning. Check the 'Data issues' sheet or the input file.")
    return LoadResult(data=data, rejected=rejected.reset_index(drop=True), column_map=column_map)


def load_sales(path: Path, sheet: str | int | None = None, dayfirst: bool = False,
               drop_duplicates: bool = True) -> LoadResult:
    raw = read_table(path, sheet)
    raw = raw.dropna(how="all")
    if raw.empty:
        raise SalesDataError("The file has no rows.")
    return clean(raw.reset_index(drop=True), map_columns(list(raw.columns)),
                 dayfirst=dayfirst, drop_duplicates=drop_duplicates)
