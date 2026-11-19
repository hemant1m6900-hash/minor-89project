from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

import pandas as pd
from sqlalchemy.orm import Session

from backend.models import Customer, Dataset, Order, OrderItem, Product, Sale
from backend.schemas import CleaningOptions
from backend.services.csv_processor import clean_and_validate_dataframe


def _safe_str(val: Any, max_len: int = 250) -> Optional[str]:
    if val is None or (isinstance(val, float) and pd.isna(val)) or pd.isna(val):
        return None
    s = str(val).strip()
    if not s or s.lower() == "nan":
        return None
    return s[:max_len]


def _safe_float(val: Any, default: float = 0.0) -> float:
    if val is None or pd.isna(val):
        return default
    return float(val)


def _safe_int(val: Any, default: int = 0) -> int:
    if val is None or pd.isna(val):
        return default
    return int(round(float(val)))


def purge_dataset_records(db: Session, user_id: int, dataset_id: int) -> None:
    """
    Remove records belonging strictly to `dataset_id` so re-importing or deleting
    never leaves stale revenue or duplicate rows in SQLite.
    """
    db.query(Sale).filter(Sale.user_id == user_id, Sale.dataset_id == dataset_id).delete(synchronize_session=False)
    db.query(OrderItem).filter(OrderItem.user_id == user_id, OrderItem.dataset_id == dataset_id).delete(synchronize_session=False)
    db.query(Order).filter(Order.user_id == user_id, Order.dataset_id == dataset_id).delete(synchronize_session=False)
    # Customers and Products may be referenced by other datasets; delete only unreferenced ones created by this dataset
    referenced_cust_ids = {
        r[0]
        for r in db.query(Order.customer_id).filter(Order.user_id == user_id, Order.customer_id.isnot(None)).all()
    } | {
        r[0]
        for r in db.query(Sale.customer_id).filter(Sale.user_id == user_id, Sale.customer_id.isnot(None)).all()
    }
    custs = db.query(Customer).filter(Customer.user_id == user_id, Customer.dataset_id == dataset_id).all()
    for c in custs:
        if c.id not in referenced_cust_ids:
            db.delete(c)
        else:
            c.dataset_id = None

    referenced_prod_ids = {
        r[0]
        for r in db.query(OrderItem.product_id).filter(OrderItem.user_id == user_id, OrderItem.product_id.isnot(None)).all()
    } | {
        r[0]
        for r in db.query(Sale.product_id).filter(Sale.user_id == user_id, Sale.product_id.isnot(None)).all()
    }
    prods = db.query(Product).filter(Product.user_id == user_id, Product.dataset_id == dataset_id).all()
    for p in prods:
        if p.id not in referenced_prod_ids:
            db.delete(p)
        else:
            p.dataset_id = None
    db.flush()


def ingest_dataframe_to_db(
    db: Session,
    dataset: Dataset,
    raw_df: pd.DataFrame,
    dataset_type: str,
    column_mapping: Dict[str, str],
    cleaning: CleaningOptions,
) -> Dict[str, Any]:
    cleaned_df, stats = clean_and_validate_dataframe(
        raw_df, dataset_type, column_mapping, cleaning
    )

    # Clear prior imported data for this dataset (supports idempotent re-import)
    purge_dataset_records(db, dataset.user_id, dataset.id)

    # Preload lookup caches scoped to user to upsert smoothly and prevent duplicate keys
    customer_cache: Dict[str, Customer] = {
        c.external_id: c
        for c in db.query(Customer).filter(Customer.user_id == dataset.user_id).all()
    }
    product_cache: Dict[str, Product] = {
        p.external_id: p
        for p in db.query(Product).filter(Product.user_id == dataset.user_id).all()
    }
    order_cache: Dict[str, Order] = {
        o.external_id: o
        for o in db.query(Order).filter(Order.user_id == dataset.user_id).all()
    }

    rows_imported = 0

    def get_or_upsert_customer(row: pd.Series) -> Optional[Customer]:
        ext_id = (
            _safe_str(row.get("customer_id"), 150)
            or _safe_str(row.get("customer_email"), 150)
            or _safe_str(row.get("customer_name"), 150)
        )
        if not ext_id:
            return None
        name = _safe_str(row.get("customer_name"), 250)
        email = _safe_str(row.get("customer_email"), 250)
        country = _safe_str(row.get("country"), 120)

        cust = customer_cache.get(ext_id)
        if cust is None:
            cust = Customer(
                user_id=dataset.user_id,
                dataset_id=dataset.id,
                external_id=ext_id,
                name=name or ext_id,
                email=email,
                country=country,
            )
            db.add(cust)
            db.flush()
            customer_cache[ext_id] = cust
        else:
            if name and (not cust.name or cust.name == cust.external_id):
                cust.name = name
            if email and not cust.email:
                cust.email = email
            if country and not cust.country:
                cust.country = country
        return cust

    def get_or_upsert_product(row: pd.Series) -> Optional[Product]:
        ext_id = (
            _safe_str(row.get("product_id"), 150)
            or _safe_str(row.get("sku"), 150)
            or _safe_str(row.get("product_name"), 150)
        )
        if not ext_id:
            return None
        name = _safe_str(row.get("product_name"), 250) or ext_id
        sku = _safe_str(row.get("sku"), 150) or ext_id
        category = _safe_str(row.get("category"), 150)
        unit_price = _safe_float(row.get("unit_price"), default=-1.0)
        cost_price = _safe_float(row.get("cost_price"), default=-1.0)
        stock_qty = row.get("stock_quantity")
        reorder_lvl = row.get("reorder_level")

        prod = product_cache.get(ext_id)
        if prod is None:
            prod = Product(
                user_id=dataset.user_id,
                dataset_id=dataset.id,
                external_id=ext_id,
                sku=sku,
                name=name,
                category=category,
                unit_price=unit_price if unit_price >= 0 else None,
                cost_price=cost_price if cost_price >= 0 else None,
                stock_quantity=_safe_int(stock_qty) if stock_qty is not None and not pd.isna(stock_qty) else None,
                reorder_level=_safe_int(reorder_lvl) if reorder_lvl is not None and not pd.isna(reorder_lvl) else None,
            )
            db.add(prod)
            db.flush()
            product_cache[ext_id] = prod
        else:
            if name and prod.name == prod.external_id:
                prod.name = name
            if category and (not prod.category or prod.category == "Unknown"):
                prod.category = category
            if unit_price >= 0:
                prod.unit_price = unit_price
            if cost_price >= 0:
                prod.cost_price = cost_price
            if stock_qty is not None and not pd.isna(stock_qty):
                prod.stock_quantity = _safe_int(stock_qty)
            if reorder_lvl is not None and not pd.isna(reorder_lvl):
                prod.reorder_level = _safe_int(reorder_lvl)
        return prod

    if dataset_type == "customers":
        for _, row in cleaned_df.iterrows():
            if get_or_upsert_customer(row) is not None:
                rows_imported += 1

    elif dataset_type in ("products", "inventory"):
        for _, row in cleaned_df.iterrows():
            if get_or_upsert_product(row) is not None:
                rows_imported += 1

    else:
        # orders, sales, transactions
        for idx, row in cleaned_df.iterrows():
            cust = get_or_upsert_customer(row)
            prod = get_or_upsert_product(row)

            qty = max(1, _safe_int(row.get("quantity"), 1)) if "quantity" in cleaned_df.columns else 1
            unit_price = _safe_float(row.get("unit_price"), -1.0)
            total_amount = _safe_float(row.get("total_amount"), -1.0)
            discount_amount = _safe_float(row.get("discount_amount"), 0.0)

            if total_amount < 0 and unit_price >= 0:
                total_amount = round(qty * unit_price - discount_amount, 2)
            elif total_amount >= 0 and unit_price < 0:
                unit_price = round(total_amount / max(1, qty), 2)
            elif total_amount < 0:
                total_amount = 0.0
                unit_price = 0.0

            raw_dt = row.get("order_date")
            dt_val: Optional[datetime] = raw_dt.to_pydatetime() if pd.notna(raw_dt) else None
            payment_method = _safe_str(row.get("payment_method"), 80)
            status_val = _safe_str(row.get("status"), 60) or "completed"

            ext_order_id = (
                _safe_str(row.get("order_id"), 150)
                or _safe_str(row.get("transaction_id"), 150)
                or f"ds{dataset.id}-row-{idx + 1}"
            )

            order = order_cache.get(ext_order_id)
            if order is None:
                order = Order(
                    user_id=dataset.user_id,
                    dataset_id=dataset.id,
                    external_id=ext_order_id,
                    customer_id=cust.id if cust else None,
                    order_date=dt_val,
                    total_amount=0.0,
                    discount_amount=discount_amount,
                    payment_method=payment_method,
                    status=status_val,
                )
                db.add(order)
                db.flush()
                order_cache[ext_order_id] = order

            # Accumulate line-item revenue onto order if multiple rows share an order_id
            order.total_amount = round(float(order.total_amount) + float(total_amount), 2)

            if prod is not None:
                order_item = OrderItem(
                    user_id=dataset.user_id,
                    dataset_id=dataset.id,
                    order_id=order.id,
                    product_id=prod.id,
                    quantity=qty,
                    unit_price=max(0.0, unit_price),
                    line_total=round(float(total_amount), 2),
                )
                db.add(order_item)

            sale = Sale(
                user_id=dataset.user_id,
                dataset_id=dataset.id,
                external_id=_safe_str(row.get("transaction_id"), 150) or ext_order_id,
                order_id=order.id,
                customer_id=cust.id if cust else None,
                product_id=prod.id if prod else None,
                sale_date=dt_val,
                quantity=qty,
                unit_price=max(0.0, unit_price),
                total_amount=round(float(total_amount), 2),
                payment_method=payment_method,
                category_snapshot=prod.category if prod else _safe_str(row.get("category"), 150),
                product_name_snapshot=prod.name if prod else _safe_str(row.get("product_name"), 250),
            )
            db.add(sale)
            rows_imported += 1

    dataset.dataset_type = dataset_type
    dataset.import_status = "imported"
    dataset.rows_parsed = stats["rows_parsed"]
    dataset.rows_imported = rows_imported
    dataset.rows_skipped = stats["rows_skipped"]
    dataset.duplicates_removed = stats["duplicates_removed"]
    dataset.column_mapping = column_mapping
    dataset.cleaning_options = cleaning.model_dump()
    dataset.error_message = "; ".join(stats["warnings"]) if stats["warnings"] else None

    db.commit()
    db.refresh(dataset)

    return {
        "dataset_id": dataset.id,
        "dataset_name": dataset.name,
        "dataset_type": dataset.dataset_type,
        "status": dataset.import_status,
        "rows_parsed": dataset.rows_parsed,
        "rows_imported": dataset.rows_imported,
        "rows_skipped": dataset.rows_skipped,
        "duplicates_removed": dataset.duplicates_removed,
        "warnings": stats["warnings"],
    }
