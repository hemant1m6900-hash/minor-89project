from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.models import AnalyticsMetadata, Customer, Dataset, Order, Product, Sale

DEFAULT_THRESHOLDS: Dict[str, Any] = {
    "low_stock_threshold": 10,
    "at_risk_days": 60,
    "rfm_clusters": 5,
    "forecast_horizon": 4,
    "anomaly_z_threshold": 2.0,
}


def get_user_thresholds(db: Session, user_id: int) -> Dict[str, Any]:
    row = (
        db.query(AnalyticsMetadata)
        .filter(AnalyticsMetadata.user_id == user_id, AnalyticsMetadata.meta_key == "thresholds")
        .first()
    )
    merged = dict(DEFAULT_THRESHOLDS)
    if row and isinstance(row.meta_value, dict):
        merged.update(row.meta_value)
    return merged


def save_user_thresholds(db: Session, user_id: int, values: Dict[str, Any]) -> Dict[str, Any]:
    row = (
        db.query(AnalyticsMetadata)
        .filter(AnalyticsMetadata.user_id == user_id, AnalyticsMetadata.meta_key == "thresholds")
        .first()
    )
    if row is None:
        row = AnalyticsMetadata(user_id=user_id, meta_key="thresholds", meta_value=values)
        db.add(row)
    else:
        row.meta_value = values
    db.commit()
    return values


def get_data_capabilities(db: Session, user_id: int) -> Dict[str, Dict[str, Any]]:
    order_count = db.query(func.count(Order.id)).filter(Order.user_id == user_id).scalar() or 0
    sale_count = db.query(func.count(Sale.id)).filter(Sale.user_id == user_id).scalar() or 0
    dated_sales = (
        db.query(func.count(Sale.id))
        .filter(Sale.user_id == user_id, Sale.sale_date.isnot(None))
        .scalar()
        or 0
    )
    rfm_cust_count = (
        db.query(func.count(func.distinct(Order.customer_id)))
        .filter(
            Order.user_id == user_id,
            Order.customer_id.isnot(None),
            Order.order_date.isnot(None),
            Order.total_amount > 0,
        )
        .scalar()
        or 0
    )
    stock_prod_count = (
        db.query(func.count(Product.id))
        .filter(Product.user_id == user_id, Product.stock_quantity.isnot(None))
        .scalar()
        or 0
    )

    # Check weekly periods available for product demand forecasting
    sales_dates = (
        db.query(Sale.sale_date, Sale.product_id)
        .filter(Sale.user_id == user_id, Sale.sale_date.isnot(None))
        .all()
    )
    weekly_periods = 0
    if sales_dates:
        df = pd.DataFrame([{"dt": r[0]} for r in sales_dates])
        df["dt"] = pd.to_datetime(df["dt"], utc=True)
        weekly_periods = int(df["dt"].dt.to_period("W").nunique())

    sales_ready = (order_count > 0 or sale_count > 0) and dated_sales > 0
    rfm_ready = rfm_cust_count >= 5
    forecast_ready = weekly_periods >= 3
    inventory_ready = stock_prod_count > 0
    insights_ready = sales_ready or inventory_ready

    return {
        "sales": {
            "ready": sales_ready,
            "reason": (
                f"{order_count} orders and {sale_count} transaction lines imported."
                if sales_ready
                else "Requires an orders, sales, or transactions CSV with dates and amounts."
            ),
        },
        "rfm": {
            "ready": rfm_ready,
            "reason": (
                f"{rfm_cust_count} distinct customers with dated monetary orders ready for K-Means."
                if rfm_ready
                else f"Requires >= 5 customers with order dates and revenue. Currently: {rfm_cust_count}."
            ),
        },
        "forecasting": {
            "ready": forecast_ready,
            "reason": (
                f"{weekly_periods} weekly historical periods detected ({'Scikit-learn ML ready' if weekly_periods >= 6 else 'Baseline moving average only; >= 6 needed for ML'})."
                if forecast_ready
                else f"Requires >= 3 historical time periods of sales data. Currently: {weekly_periods}."
            ),
        },
        "inventory_alerts": {
            "ready": inventory_ready,
            "reason": (
                f"{stock_prod_count} products have stock quantity tracked."
                if inventory_ready
                else "Requires a products or inventory CSV with 'stock_quantity' mapped."
            ),
        },
        "insights": {
            "ready": insights_ready,
            "reason": (
                "Active detectors evaluate sales trends, anomalies, top products, churn risk, and stock."
                if insights_ready
                else "Upload sales, orders, or inventory CSVs to activate automated insights."
            ),
        },
    }


def _load_sales_dataframe(db: Session, user_id: int) -> pd.DataFrame:
    rows = (
        db.query(
            Sale.id,
            Sale.external_id,
            Sale.order_id,
            Sale.customer_id,
            Sale.product_id,
            Sale.sale_date,
            Sale.quantity,
            Sale.unit_price,
            Sale.total_amount,
            Sale.payment_method,
            Sale.category_snapshot,
            Sale.product_name_snapshot,
            Customer.name.label("customer_name"),
            Customer.external_id.label("customer_ext_id"),
            Product.name.label("product_name"),
            Product.sku.label("product_sku"),
            Product.category.label("product_category"),
            Order.status.label("order_status"),
            Order.external_id.label("order_ext_id"),
        )
        .outerjoin(Customer, Sale.customer_id == Customer.id)
        .outerjoin(Product, Sale.product_id == Product.id)
        .outerjoin(Order, Sale.order_id == Order.id)
        .filter(Sale.user_id == user_id)
        .all()
    )
    if not rows:
        return pd.DataFrame()

    records = []
    for r in rows:
        records.append(
            {
                "sale_id": r.id,
                "reference": r.order_ext_id or r.external_id or f"TXN-{r.id}",
                "order_id": r.order_id or r.id,
                "sale_date": r.sale_date,
                "quantity": int(r.quantity or 1),
                "unit_price": float(r.unit_price or 0.0),
                "total_amount": float(r.total_amount or 0.0),
                "payment_method": r.payment_method or "Unspecified",
                "status": r.order_status or "completed",
                "customer": r.customer_name or r.customer_ext_id or "Guest / Unmapped",
                "product_id": r.product_id,
                "product_name": r.product_name or r.product_name_snapshot or "Unmapped Product",
                "sku": r.product_sku or "—",
                "category": r.product_category or r.category_snapshot or "Uncategorized",
            }
        )
    df = pd.DataFrame(records)
    df["sale_date"] = pd.to_datetime(df["sale_date"], errors="coerce", utc=True)
    return df


def get_dashboard_analytics(db: Session, user_id: int) -> Dict[str, Any]:
    active_datasets = (
        db.query(func.count(Dataset.id))
        .filter(Dataset.user_id == user_id, Dataset.import_status == "imported")
        .scalar()
        or 0
    )
    total_customers = db.query(func.count(Customer.id)).filter(Customer.user_id == user_id).scalar() or 0
    total_products = db.query(func.count(Product.id)).filter(Product.user_id == user_id).scalar() or 0
    total_orders = db.query(func.count(Order.id)).filter(Order.user_id == user_id).scalar() or 0

    df = _load_sales_dataframe(db, user_id)
    if df.empty:
        return {
            "summary": {
                "total_revenue": 0.0,
                "total_orders": total_orders,
                "total_customers": total_customers,
                "total_products": total_products,
                "total_sales_rows": 0,
                "average_order_value": 0.0,
                "active_datasets": active_datasets,
                "date_range_label": None,
            },
            "monthly_sales": [],
            "category_performance": [],
            "top_products": [],
            "recent_transactions": [],
        }

    total_revenue = round(float(df["total_amount"].sum()), 2)
    distinct_orders = int(df["order_id"].nunique()) if total_orders == 0 else total_orders
    aov = round(total_revenue / distinct_orders, 2) if distinct_orders > 0 else 0.0

    valid_dates = df[df["sale_date"].notna()].copy()
    date_range_label = None
    monthly_sales: List[Dict[str, Any]] = []
    if not valid_dates.empty:
        min_dt = valid_dates["sale_date"].min().strftime("%b %Y")
        max_dt = valid_dates["sale_date"].max().strftime("%b %Y")
        date_range_label = min_dt if min_dt == max_dt else f"{min_dt} – {max_dt}"

        valid_dates["month"] = valid_dates["sale_date"].dt.tz_localize(None).dt.to_period("M").astype(str)
        grouped = (
            valid_dates.groupby("month", as_index=False)
            .agg(revenue=("total_amount", "sum"), orders=("order_id", "nunique"), units=("quantity", "sum"))
            .sort_values("month")
        )
        monthly_sales = [
            {
                "period": row["month"],
                "revenue": round(float(row["revenue"]), 2),
                "orders": int(row["orders"]),
                "units": int(row["units"]),
            }
            for _, row in grouped.iterrows()
        ]

    cat_group = (
        df.groupby("category", as_index=False)
        .agg(revenue=("total_amount", "sum"), units=("quantity", "sum"))
        .sort_values("revenue", ascending=False)
    )
    category_performance = [
        {
            "category": row["category"],
            "revenue": round(float(row["revenue"]), 2),
            "units": int(row["units"]),
        }
        for _, row in cat_group.iterrows()
    ]

    prod_group = (
        df.groupby(["product_name", "category"], as_index=False)
        .agg(revenue=("total_amount", "sum"), units_sold=("quantity", "sum"))
        .sort_values("revenue", ascending=False)
        .head(10)
    )
    top_products = [
        {
            "name": row["product_name"],
            "category": row["category"],
            "units_sold": int(row["units_sold"]),
            "revenue": round(float(row["revenue"]), 2),
        }
        for _, row in prod_group.iterrows()
    ]

    recent_df = df.sort_values(by=["sale_date", "sale_id"], ascending=[False, False], na_position="last").head(12)
    recent_transactions = [
        {
            "reference": row["reference"],
            "date": row["sale_date"].isoformat() if pd.notna(row["sale_date"]) else None,
            "customer": row["customer"],
            "amount": round(float(row["total_amount"]), 2),
        }
        for _, row in recent_df.iterrows()
    ]

    return {
        "summary": {
            "total_revenue": total_revenue,
            "total_orders": distinct_orders,
            "total_customers": total_customers,
            "total_products": total_products,
            "total_sales_rows": int(len(df)),
            "average_order_value": aov,
            "active_datasets": active_datasets,
            "date_range_label": date_range_label,
        },
        "monthly_sales": monthly_sales,
        "category_performance": category_performance,
        "top_products": top_products,
        "recent_transactions": recent_transactions,
    }


def get_sales_analytics(
    db: Session,
    user_id: int,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    category: Optional[str] = None,
    granularity: str = "monthly",
) -> Dict[str, Any]:
    df = _load_sales_dataframe(db, user_id)
    if df.empty:
        return {
            "available_categories": [],
            "summary": {"total_revenue": 0.0, "total_orders": 0, "total_units": 0, "average_order_value": 0.0, "growth_pct": None},
            "trend": [],
            "categories": [],
            "top_products": [],
            "transactions": [],
        }

    available_categories = sorted(df["category"].dropna().unique().tolist())

    filtered = df.copy()
    if start_date:
        start_dt = pd.to_datetime(start_date, utc=True)
        filtered = filtered[filtered["sale_date"] >= start_dt]
    if end_date:
        end_dt = pd.to_datetime(end_date, utc=True) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
        filtered = filtered[filtered["sale_date"] <= end_dt]
    if category:
        filtered = filtered[filtered["category"] == category]

    if filtered.empty:
        return {
            "available_categories": available_categories,
            "summary": {"total_revenue": 0.0, "total_orders": 0, "total_units": 0, "average_order_value": 0.0, "growth_pct": None},
            "trend": [],
            "categories": [],
            "top_products": [],
            "transactions": [],
        }

    total_revenue = round(float(filtered["total_amount"].sum()), 2)
    total_orders = int(filtered["order_id"].nunique())
    total_units = int(filtered["quantity"].sum())
    aov = round(total_revenue / total_orders, 2) if total_orders > 0 else 0.0

    period_code = {"daily": "D", "weekly": "W", "monthly": "M"}.get(granularity, "M")
    dated = filtered[filtered["sale_date"].notna()].copy()
    trend: List[Dict[str, Any]] = []
    growth_pct: Optional[float] = None
    if not dated.empty:
        dated["period"] = dated["sale_date"].dt.tz_localize(None).dt.to_period(period_code).astype(str)
        t_df = (
            dated.groupby("period", as_index=False)
            .agg(revenue=("total_amount", "sum"), orders=("order_id", "nunique"), units=("quantity", "sum"))
            .sort_values("period")
        )
        trend = [
            {
                "period": r["period"],
                "revenue": round(float(r["revenue"]), 2),
                "orders": int(r["orders"]),
                "units": int(r["units"]),
            }
            for _, r in t_df.iterrows()
        ]
        if len(trend) >= 2 and trend[-2]["revenue"] > 0:
            growth_pct = round(((trend[-1]["revenue"] - trend[-2]["revenue"]) / trend[-2]["revenue"]) * 100, 1)

    cat_df = (
        filtered.groupby("category", as_index=False)
        .agg(revenue=("total_amount", "sum"), units=("quantity", "sum"))
        .sort_values("revenue", ascending=False)
    )
    categories = [
        {"category": r["category"], "revenue": round(float(r["revenue"]), 2), "units": int(r["units"])}
        for _, r in cat_df.iterrows()
    ]

    prod_df = (
        filtered.groupby(["product_name", "sku", "category"], as_index=False)
        .agg(revenue=("total_amount", "sum"), units_sold=("quantity", "sum"), avg_price=("unit_price", "mean"))
        .sort_values("revenue", ascending=False)
        .head(25)
    )
    top_products = [
        {
            "name": r["product_name"],
            "sku": r["sku"],
            "category": r["category"],
            "units_sold": int(r["units_sold"]),
            "avg_price": round(float(r["avg_price"]), 2),
            "revenue": round(float(r["revenue"]), 2),
        }
        for _, r in prod_df.iterrows()
    ]

    tx_df = filtered.sort_values(by=["sale_date", "sale_id"], ascending=[False, False], na_position="last").head(50)
    transactions = [
        {
            "reference": r["reference"],
            "date": r["sale_date"].isoformat() if pd.notna(r["sale_date"]) else None,
            "customer": r["customer"],
            "payment_method": r["payment_method"],
            "status": r["status"],
            "amount": round(float(r["total_amount"]), 2),
        }
        for _, r in tx_df.iterrows()
    ]

    return {
        "available_categories": available_categories,
        "summary": {
            "total_revenue": total_revenue,
            "total_orders": total_orders,
            "total_units": total_units,
            "average_order_value": aov,
            "growth_pct": growth_pct,
        },
        "trend": trend,
        "categories": categories,
        "top_products": top_products,
        "transactions": transactions,
    }
