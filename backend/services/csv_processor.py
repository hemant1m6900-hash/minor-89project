from __future__ import annotations

import hashlib
import io
import re
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

from backend.schemas import CleaningOptions

CANONICAL_SYNONYMS: Dict[str, List[str]] = {
    "order_id": ["order_id", "orderid", "order_no", "order_number", "invoice", "invoiceno", "invoice_no", "invoice_id"],
    "order_date": ["order_date", "orderdate", "date", "sale_date", "transaction_date", "invoice_date", "created_at", "purchase_date", "timestamp"],
    "transaction_id": ["transaction_id", "txn_id", "tx_id", "payment_id", "receipt_id", "reference"],
    "customer_id": ["customer_id", "customerid", "cust_id", "client_id", "user_id", "buyer_id", "account_id"],
    "customer_name": ["customer_name", "customer", "client_name", "buyer_name", "full_name", "customer_full_name"],
    "customer_email": ["customer_email", "email", "email_address", "mail"],
    "country": ["country", "region", "market", "nation", "location", "city", "state"],
    "product_id": ["product_id", "productid", "item_id", "prod_id", "stockcode", "stock_code"],
    "sku": ["sku", "sku_code", "barcode", "asin", "upc"],
    "product_name": ["product_name", "product", "item_name", "item", "description", "title", "product_title"],
    "category": ["category", "product_category", "sub_category", "department", "segment", "type"],
    "quantity": ["quantity", "qty", "units", "units_sold", "count", "order_qty", "item_qty"],
    "unit_price": ["unit_price", "price", "unitprice", "selling_price", "sale_price", "item_price", "rate"],
    "cost_price": ["cost_price", "cost", "unit_cost", "cogs", "wholesale_price"],
    "total_amount": ["total_amount", "total", "amount", "revenue", "sales", "line_total", "grand_total", "net_amount", "subtotal", "gross_sales"],
    "discount_amount": ["discount_amount", "discount", "promo_discount"],
    "stock_quantity": ["stock_quantity", "stock", "inventory", "on_hand", "qty_on_hand", "available_qty", "stock_level"],
    "reorder_level": ["reorder_level", "reorder_point", "min_stock", "safety_stock", "threshold"],
    "payment_method": ["payment_method", "payment_type", "payment", "pay_method", "channel"],
    "status": ["status", "order_status", "state", "fulfillment_status"],
}

NUMERIC_FIELDS = {
    "quantity",
    "unit_price",
    "cost_price",
    "total_amount",
    "discount_amount",
    "stock_quantity",
    "reorder_level",
}


def compute_sha256(raw_bytes: bytes) -> str:
    return hashlib.sha256(raw_bytes).hexdigest()


def read_csv_bytes(raw_bytes: bytes) -> pd.DataFrame:
    if not raw_bytes or len(raw_bytes.strip()) == 0:
        raise ValueError("The uploaded CSV file is empty.")
    last_err: Exception | None = None
    for encoding in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            df = pd.read_csv(io.BytesIO(raw_bytes), encoding=encoding, dtype=str, keep_default_na=True)
            if df.empty and len(df.columns) == 0:
                raise ValueError("CSV contains no headers or rows.")
            # Clean column header whitespace
            df.columns = [str(c).strip() for c in df.columns]
            return df
        except Exception as exc:
            last_err = exc
    raise ValueError(f"Unable to parse CSV file: {last_err}")


def _clean_numeric_series(series: pd.Series) -> pd.Series:
    cleaned = (
        series.astype(str)
        .str.strip()
        .replace({"": np.nan, "nan": np.nan, "None": np.nan, "NULL": np.nan, "null": np.nan, "N/A": np.nan, "n/a": np.nan, "-": np.nan})
    )
    cleaned = cleaned.str.replace(r"[$€£₹,\s]", "", regex=True)
    return pd.to_numeric(cleaned, errors="coerce")


def _detect_column_type(series: pd.Series, col_name: str) -> str:
    non_null = series.dropna().astype(str).str.strip()
    non_null = non_null[non_null != ""]
    if non_null.empty:
        return "text"

    sample = non_null.head(200)
    lower_name = col_name.lower()

    if sample.str.contains(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", regex=True).mean() >= 0.7:
        return "email"

    bool_vals = {"true", "false", "yes", "no", "0", "1"}
    if sample.str.lower().isin(bool_vals).mean() >= 0.95 and "id" not in lower_name:
        if not sample.str.fullmatch(r"\d+").all():
            return "boolean"

    num_parsed = _clean_numeric_series(sample)
    if num_parsed.notna().mean() >= 0.85:
        if "id" in lower_name or "code" in lower_name or "sku" in lower_name:
            return "identifier"
        if (num_parsed.dropna() % 1 == 0).all():
            return "integer"
        return "float"

    # Only test datetime if column looks date-like or strings contain separators
    if any(k in lower_name for k in ("date", "time", "created", "updated", "day")) or sample.str.contains(r"[-/]", regex=True).mean() > 0.5:
        dt_parsed = pd.to_datetime(sample, errors="coerce", format="mixed")
        if dt_parsed.notna().mean() >= 0.8:
            return "datetime"

    if "id" in lower_name or "sku" in lower_name:
        return "identifier"

    return "text"


def _normalize_col_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")


def suggest_column_mapping(columns: List[str]) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    used_targets: set[str] = set()
    for col in columns:
        norm = _normalize_col_key(col)
        matched_target = None
        for canonical, synonyms in CANONICAL_SYNONYMS.items():
            if norm in synonyms and canonical not in used_targets:
                matched_target = canonical
                break
        if not matched_target:
            for canonical, synonyms in CANONICAL_SYNONYMS.items():
                if any(s in norm for s in synonyms if len(s) >= 4) and canonical not in used_targets:
                    matched_target = canonical
                    break
        if matched_target:
            mapping[col] = matched_target
            used_targets.add(matched_target)
    return mapping


def classify_dataset(suggested_mapping: Dict[str, str], filename: str) -> Tuple[str, float, str]:
    targets = set(suggested_mapping.values())
    fname = filename.lower()

    scores: Dict[str, float] = {
        "orders": 0.0,
        "sales": 0.0,
        "transactions": 0.0,
        "products": 0.0,
        "customers": 0.0,
        "inventory": 0.0,
    }

    if {"stock_quantity", "reorder_level"} & targets or "inventory" in fname or "stock" in fname:
        scores["inventory"] += 0.55
        if "product_id" in targets or "product_name" in targets or "sku" in targets:
            scores["inventory"] += 0.3

    if {"order_id", "order_date"} <= targets:
        scores["orders"] += 0.65
    if "order_id" in targets:
        scores["orders"] += 0.2
    if "transaction_id" in targets or "payment_method" in targets or "transaction" in fname:
        scores["transactions"] += 0.55
        if "total_amount" in targets or "order_date" in targets:
            scores["transactions"] += 0.25

    if {"product_name", "unit_price"} <= targets or "category" in targets:
        if "order_id" not in targets and "order_date" not in targets and "total_amount" not in targets:
            scores["products"] += 0.65
        else:
            scores["sales"] += 0.35

    if "order_date" in targets and ("total_amount" in targets or ("quantity" in targets and "unit_price" in targets)):
        scores["sales"] += 0.5
        scores["orders"] += 0.45

    if ({"customer_id", "customer_email"} & targets or "customer_name" in targets) and not (
        {"order_id", "order_date", "total_amount", "product_id", "stock_quantity"} & targets
    ):
        scores["customers"] += 0.75

    # Filename tie-breakers
    for key in scores:
        if key in fname or key.rstrip("s") in fname:
            scores[key] += 0.2

    best_type = max(scores, key=lambda k: scores[k])
    best_score = min(0.98, max(0.35, round(scores[best_type], 2)))
    if scores[best_type] == 0.0:
        best_type = "sales"
        best_score = 0.35

    reason = f"Matched canonical fields ({', '.join(sorted(targets)) or 'none'}) and filename signals."
    return best_type, best_score, reason


def profile_dataframe(df: pd.DataFrame, filename: str) -> Dict[str, Any]:
    total_rows = int(len(df))
    total_cols = int(len(df.columns))
    if total_rows == 0:
        raise ValueError("CSV file contains headers but zero data rows.")

    missing_cells = int(df.isna().sum().sum())
    duplicate_rows = int(df.duplicated().sum())

    columns_meta: List[Dict[str, Any]] = []
    for col in df.columns:
        series = df[col]
        # Treat blank strings as missing
        blank_mask = series.isna() | (series.astype(str).str.strip() == "")
        missing_count = int(blank_mask.sum())
        missing_pct = round((missing_count / total_rows) * 100, 1) if total_rows else 0.0
        non_blank = series[~blank_mask]
        unique_count = int(non_blank.nunique())
        detected_type = _detect_column_type(non_blank, col)
        sample_values = [str(v) for v in non_blank.head(4).tolist()]
        columns_meta.append(
            {
                "name": col,
                "detected_type": detected_type,
                "missing_count": missing_count,
                "missing_pct": missing_pct,
                "unique_count": unique_count,
                "sample_values": sample_values,
            }
        )

    suggested_mapping = suggest_column_mapping(list(df.columns))
    detected_type, confidence, reason = classify_dataset(suggested_mapping, filename)

    preview_df = df.head(20).replace({np.nan: None})
    preview_rows = preview_df.to_dict(orient="records")

    return {
        "row_count": total_rows,
        "column_count": total_cols,
        "missing_cells": missing_cells,
        "duplicate_rows": duplicate_rows,
        "detected_type": detected_type,
        "classification_confidence": confidence,
        "classification_reason": reason,
        "columns": columns_meta,
        "suggested_mapping": suggested_mapping,
        "preview_rows": preview_rows,
    }


def clean_and_validate_dataframe(
    df: pd.DataFrame,
    dataset_type: str,
    column_mapping: Dict[str, str],
    cleaning: CleaningOptions,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Validates semantic column mappings, cleans whitespace/currency/duplicates/missing values,
    and returns a normalized DataFrame keyed by canonical field names plus preprocessing stats.
    """
    if not column_mapping:
        raise ValueError("At least one CSV column must be mapped to a canonical field.")

    missing_csv_cols = [c for c in column_mapping.keys() if c not in df.columns]
    if missing_csv_cols:
        raise ValueError(f"Mapped columns not found in CSV: {', '.join(missing_csv_cols)}")

    # Check duplicate target mappings
    target_counts: Dict[str, int] = {}
    for target in column_mapping.values():
        if target:
            target_counts[target] = target_counts.get(target, 0) + 1
    dup_targets = [t for t, cnt in target_counts.items() if cnt > 1]
    if dup_targets:
        raise ValueError(f"Multiple CSV columns mapped to the same field: {', '.join(dup_targets)}")

    mapped_targets = set(target_counts.keys())

    # Semantic validation per dataset type
    if dataset_type in ("orders", "sales", "transactions"):
        has_amount = "total_amount" in mapped_targets or (
            "quantity" in mapped_targets and "unit_price" in mapped_targets
        )
        if not has_amount:
            raise ValueError(
                f"A '{dataset_type}' dataset requires 'total_amount' (or both 'quantity' and 'unit_price') to calculate revenue."
            )
        if "order_date" not in mapped_targets:
            raise ValueError(
                f"A '{dataset_type}' dataset requires 'order_date' mapped so time-series trends, RFM recency, and forecasting work accurately."
            )
    elif dataset_type == "products":
        if not ({"product_name", "product_id", "sku"} & mapped_targets):
            raise ValueError("A 'products' dataset requires at least 'product_name', 'product_id', or 'sku'.")
    elif dataset_type == "inventory":
        if not ({"product_name", "product_id", "sku"} & mapped_targets):
            raise ValueError("An 'inventory' dataset requires at least 'product_name', 'product_id', or 'sku'.")
        if "stock_quantity" not in mapped_targets:
            raise ValueError("An 'inventory' dataset requires 'stock_quantity' mapped.")
    elif dataset_type == "customers":
        if not ({"customer_id", "customer_email", "customer_name"} & mapped_targets):
            raise ValueError("A 'customers' dataset requires at least 'customer_id', 'customer_email', or 'customer_name'.")

    work = df[list(column_mapping.keys())].rename(columns=column_mapping).copy()
    rows_parsed = int(len(work))
    warnings: List[str] = []

    if cleaning.trim_whitespace:
        for col in work.columns:
            work[col] = work[col].apply(lambda v: v.strip() if isinstance(v, str) else v)
            work[col] = work[col].replace({"": np.nan, "nan": np.nan, "None": np.nan, "NULL": np.nan, "null": np.nan})

    duplicates_removed = 0
    if cleaning.drop_duplicates:
        before = len(work)
        work = work.drop_duplicates().reset_index(drop=True)
        duplicates_removed = int(before - len(work))

    # Parse numeric columns cleanly
    for col in work.columns:
        if col in NUMERIC_FIELDS:
            raw_non_null = work[col].notna().sum()
            parsed = _clean_numeric_series(work[col])
            bad_count = int(raw_non_null - parsed.notna().sum())
            if bad_count > 0:
                if bad_count == raw_non_null and raw_non_null > 0:
                    raise ValueError(
                        f"Column mapped to '{col}' contains no valid numeric values (e.g. '{work[col].dropna().iloc[0]}')."
                    )
                warnings.append(f"Coerced {bad_count} non-numeric entries in '{col}' to missing.")
            work[col] = parsed

    # Parse order_date if present
    if "order_date" in work.columns:
        raw_non_null = work["order_date"].notna().sum()
        parsed_dates = pd.to_datetime(work["order_date"], errors="coerce", format="mixed", utc=True)
        bad_dates = int(raw_non_null - parsed_dates.notna().sum())
        if raw_non_null > 0 and parsed_dates.notna().sum() == 0:
            sample_bad = str(work["order_date"].dropna().iloc[0])
            raise ValueError(
                f"Column mapped to 'order_date' could not be parsed as dates (sample value: '{sample_bad}')."
            )
        if bad_dates > 0:
            warnings.append(f"Dropped {bad_dates} rows with unparseable 'order_date' values.")
        work["order_date"] = parsed_dates
        work = work[work["order_date"].notna()].copy()

    # Apply missing value strategies
    num_cols_present = [c for c in work.columns if c in NUMERIC_FIELDS]
    if num_cols_present:
        if cleaning.missing_numeric == "drop":
            before = len(work)
            work = work.dropna(subset=num_cols_present)
            dropped = int(before - len(work))
            if dropped:
                warnings.append(f"Dropped {dropped} rows with missing numeric values.")
        elif cleaning.missing_numeric == "median":
            for c in num_cols_present:
                med = work[c].median()
                fill_val = 0.0 if pd.isna(med) else float(med)
                work[c] = work[c].fillna(fill_val)
        else:
            for c in num_cols_present:
                default_val = 1.0 if c == "quantity" else 0.0
                work[c] = work[c].fillna(default_val)

    text_cols_present = [c for c in work.columns if c not in NUMERIC_FIELDS and c != "order_date"]
    if text_cols_present:
        if cleaning.missing_text == "drop":
            before = len(work)
            work = work.dropna(subset=text_cols_present)
            dropped = int(before - len(work))
            if dropped:
                warnings.append(f"Dropped {dropped} rows with missing text values.")
        elif cleaning.missing_text == "unknown":
            for c in text_cols_present:
                if c not in ("customer_id", "customer_email", "product_id", "sku", "order_id", "transaction_id"):
                    work[c] = work[c].fillna("Unknown")

    if work.empty:
        raise ValueError("Zero valid rows remained after cleaning and validation.")

    rows_skipped = max(0, rows_parsed - duplicates_removed - int(len(work)))
    stats = {
        "rows_parsed": rows_parsed,
        "rows_valid": int(len(work)),
        "rows_skipped": rows_skipped,
        "duplicates_removed": duplicates_removed,
        "warnings": warnings,
    }
    return work.reset_index(drop=True), stats
