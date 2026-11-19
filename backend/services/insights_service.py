from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, List

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from backend.models import Customer, Order, Product, Sale
from backend.services.analytics_service import get_user_thresholds


def generate_smart_alerts(db: Session, user_id: int) -> Dict[str, Any]:
    thresholds = get_user_thresholds(db, user_id)
    low_stock_threshold = int(thresholds.get("low_stock_threshold", 10))
    at_risk_days = int(thresholds.get("at_risk_days", 60))
    anomaly_z = float(thresholds.get("anomaly_z_threshold", 2.0))

    alerts: List[Dict[str, Any]] = []
    skipped_detectors: List[str] = []

    # 1. Sales Trend & Anomaly Detection
    sales_rows = (
        db.query(Sale.sale_date, Sale.total_amount, Sale.quantity, Sale.product_id, Product.name, Product.category)
        .outerjoin(Product, Sale.product_id == Product.id)
        .filter(Sale.user_id == user_id)
        .all()
    )

    if not sales_rows:
        skipped_detectors.append("Sales Trend & Anomaly Detectors: No sales or orders data imported yet.")
        skipped_detectors.append("Top Product Performance Detector: No product sales transactions imported yet.")
    else:
        df = pd.DataFrame(
            [
                {
                    "dt": r.sale_date,
                    "amount": float(r.total_amount or 0.0),
                    "qty": int(r.quantity or 1),
                    "product_name": r.name or "Unmapped Product",
                    "category": r.category or "Uncategorized",
                }
                for r in sales_rows
            ]
        )
        df["dt"] = pd.to_datetime(df["dt"], errors="coerce", utc=True)
        dated = df[df["dt"].notna()].copy()

        # Monthly / Weekly Trend
        if not dated.empty:
            dated["month"] = dated["dt"].dt.tz_localize(None).dt.to_period("M")
            m_rev = dated.groupby("month")["amount"].sum().sort_index()
            if len(m_rev) >= 2:
                prev_val = float(m_rev.iloc[-2])
                curr_val = float(m_rev.iloc[-1])
                if prev_val > 0:
                    pct_change = round(((curr_val - prev_val) / prev_val) * 100, 1)
                    if pct_change <= -15.0:
                        alerts.append(
                            {
                                "id": "trend-decline",
                                "category": "sales_trend",
                                "category_label": "Sales Trend",
                                "severity": "critical" if pct_change <= -30 else "warning",
                                "title": f"Revenue declined {abs(pct_change)}% in {m_rev.index[-1]}",
                                "metric_value": f"{pct_change}%",
                                "description": f"Monthly revenue fell from ${prev_val:,.2f} ({m_rev.index[-2]}) to ${curr_val:,.2f} ({m_rev.index[-1]}).",
                                "recommendation": "Inspect declining SKU categories in Sales Analytics and target At-Risk customers with retention offers.",
                            }
                        )
                    elif pct_change >= 20.0:
                        alerts.append(
                            {
                                "id": "trend-growth",
                                "category": "sales_trend",
                                "category_label": "Sales Trend",
                                "severity": "opportunity",
                                "title": f"Revenue grew +{pct_change}% in {m_rev.index[-1]}",
                                "metric_value": f"+{pct_change}%",
                                "description": f"Monthly revenue expanded from ${prev_val:,.2f} ({m_rev.index[-2]}) to ${curr_val:,.2f} ({m_rev.index[-1]}).",
                                "recommendation": "Verify stock coverage for fastest-moving products in Demand Forecasting to prevent stockouts.",
                            }
                        )
            else:
                skipped_detectors.append("Period-over-Period Trend Detector: Requires at least 2 distinct months of dated sales.")

            # Daily Revenue Z-Score Anomaly Detection
            dated["day"] = dated["dt"].dt.tz_localize(None).dt.date
            daily_rev = dated.groupby("day")["amount"].sum().sort_index()
            if len(daily_rev) >= 7:
                vals = daily_rev.values.astype(float)
                mean_v = float(np.mean(vals))
                std_v = float(np.std(vals))
                if std_v > 0:
                    z_scores = (vals - mean_v) / std_v
                    for idx_day, z in zip(daily_rev.index, z_scores):
                        if abs(z) >= anomaly_z:
                            direction = "surge" if z > 0 else "drop"
                            alerts.append(
                                {
                                    "id": f"anomaly-{idx_day}",
                                    "category": "anomaly",
                                    "category_label": "Statistical Anomaly",
                                    "severity": "warning" if z < 0 else "info",
                                    "title": f"Unusual daily revenue {direction} on {idx_day}",
                                    "metric_value": f"z={z:+.2f}",
                                    "description": f"Revenue on {idx_day} was ${daily_rev[idx_day]:,.2f} vs daily mean ${mean_v:,.2f} (std ${std_v:,.2f}).",
                                    "recommendation": "Audit transaction logs for bulk orders, promotions, or data import anomalies on that date.",
                                }
                            )
            else:
                skipped_detectors.append("Daily Anomaly Detector: Requires at least 7 distinct days of sales history.")

        # Best-Performing Products
        total_rev = float(df["amount"].sum())
        if total_rev > 0:
            prod_rev = df.groupby("product_name", as_index=False).agg(rev=("amount", "sum"), qty=("qty", "sum")).sort_values("rev", ascending=False)
            top = prod_rev.iloc[0]
            share = round((float(top["rev"]) / total_rev) * 100, 1)
            alerts.append(
                {
                    "id": "top-product",
                    "category": "product_performance",
                    "category_label": "Product Performance",
                    "severity": "opportunity",
                    "title": f"Top revenue driver: {top['product_name']}",
                    "metric_value": f"${top['rev']:,.2f} ({share}%)",
                    "description": f"{top['product_name']} generated {share}% of total revenue across {int(top['qty'])} units sold.",
                    "recommendation": "Maintain safety stock levels and evaluate bundle promotions with complementary items.",
                }
            )

    # 2. At-Risk Customers Detector
    orders = (
        db.query(Order.customer_id, Order.order_date, Order.total_amount)
        .filter(Order.user_id == user_id, Order.customer_id.isnot(None), Order.order_date.isnot(None), Order.total_amount > 0)
        .all()
    )
    if not orders:
        skipped_detectors.append("At-Risk Customer Detector: Requires orders with Customer IDs and Order Dates.")
    else:
        odf = pd.DataFrame([{"cid": o.customer_id, "dt": o.order_date, "amt": float(o.total_amount)} for o in orders])
        odf["dt"] = pd.to_datetime(odf["dt"], utc=True)
        ref_dt = odf["dt"].max() + timedelta(days=1)
        cust_agg = odf.groupby("cid", as_index=False).agg(
            last_dt=("dt", "max"),
            monetary=("amt", "sum"),
            orders=("amt", "count"),
        )
        cust_agg["recency_days"] = (ref_dt - cust_agg["last_dt"]).dt.days
        median_spend = float(cust_agg["monetary"].median()) if len(cust_agg) > 0 else 0.0
        at_risk = cust_agg[(cust_agg["recency_days"] >= at_risk_days) & (cust_agg["monetary"] >= median_spend)]
        if not at_risk.empty:
            at_risk_rev = float(at_risk["monetary"].sum())
            alerts.append(
                {
                    "id": "at-risk-customers",
                    "category": "customer_churn",
                    "category_label": "Customer Retention",
                    "severity": "warning",
                    "title": f"{len(at_risk)} high-value customers inactive >= {at_risk_days} days",
                    "metric_value": f"${at_risk_rev:,.2f} historical",
                    "description": f"Customers at or above median spend (${median_spend:,.2f}) have not placed an order in {at_risk_days}+ days.",
                    "recommendation": "Open Customer Segmentation to filter At-Risk / Lost cohorts and export a win-back campaign CSV.",
                }
            )

    # 3. Low Inventory Detector
    tracked_products = (
        db.query(Product)
        .filter(Product.user_id == user_id, Product.stock_quantity.isnot(None))
        .all()
    )
    if not tracked_products:
        skipped_detectors.append("Low Inventory Detector: No products have 'stock_quantity' mapped from an inventory or products CSV.")
    else:
        low_items = []
        for p in tracked_products:
            limit = p.reorder_level if p.reorder_level is not None else low_stock_threshold
            if p.stock_quantity is not None and p.stock_quantity <= limit:
                low_items.append(p)
        if low_items:
            low_items.sort(key=lambda x: x.stock_quantity or 0)
            sample_names = ", ".join(p.name for p in low_items[:4])
            out_of_stock = sum(1 for p in low_items if (p.stock_quantity or 0) <= 0)
            alerts.append(
                {
                    "id": "low-inventory",
                    "category": "inventory",
                    "category_label": "Inventory Risk",
                    "severity": "critical" if out_of_stock > 0 else "warning",
                    "title": f"{len(low_items)} product(s) at or below reorder threshold",
                    "metric_value": f"{out_of_stock} out of stock",
                    "description": f"Affected SKUs include: {sample_names}{'...' if len(low_items) > 4 else ''}.",
                    "recommendation": "Prioritize replenishment orders aligned with Demand Forecasting projections.",
                }
            )

    # Sort alerts by severity
    sev_order = {"critical": 0, "warning": 1, "opportunity": 2, "info": 3}
    alerts.sort(key=lambda a: sev_order.get(a["severity"], 9))

    critical_and_warning = sum(1 for a in alerts if a["severity"] in ("critical", "warning"))
    opportunities = sum(1 for a in alerts if a["severity"] == "opportunity")

    return {
        "summary": {
            "total": len(alerts),
            "critical_and_warning": critical_and_warning,
            "opportunities": opportunities,
        },
        "alerts": alerts,
        "skipped_detectors": skipped_detectors,
    }
