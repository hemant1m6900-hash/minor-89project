from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.orm import Session

from backend.models import Product
from backend.services.analytics_service import get_dashboard_analytics, get_sales_analytics, get_user_thresholds
from backend.services.forecast_service import run_demand_forecast
from backend.services.insights_service import generate_smart_alerts
from backend.services.rfm_service import compute_rfm_segmentation

NAVY_HEX = colors.HexColor("#0F1B3D")
PINK_HEX = colors.HexColor("#FF3D8B")
TINT_HEX = colors.HexColor("#F4F6FA")
BORDER_HEX = colors.HexColor("#D6DCE8")


def _build_report_data(db: Session, user_id: int, report_type: str) -> Tuple[str, List[str], List[List[Any]], List[Tuple[str, str]]]:
    """
    Returns (title, headers, rows, kpi_summary) for the requested report_type.
    Raises ValueError if required data is missing so empty/fake reports are never emitted.
    """
    thresholds = get_user_thresholds(db, user_id)

    if report_type == "sales":
        data = get_sales_analytics(db, user_id, granularity="monthly")
        s = data["summary"]
        if (s.get("total_orders") or 0) == 0:
            raise ValueError("Cannot generate Sales Report: no sales or order transactions have been imported yet.")
        kpis = [
            ("Total Revenue", f"${s['total_revenue']:,.2f}"),
            ("Total Orders", f"{s['total_orders']:,}"),
            ("Total Units", f"{s['total_units']:,}"),
            ("Average Order Value", f"${s['average_order_value']:,.2f}"),
        ]
        headers = ["Period", "Orders", "Units Sold", "Revenue ($)"]
        rows = [[t["period"], t["orders"], t["units"], f"{t['revenue']:,.2f}"] for t in data["trend"]]
        if not rows:
            rows = [[tx["reference"], tx["date"] or "—", tx["customer"], f"{tx['amount']:,.2f}"] for tx in data["transactions"]]
            headers = ["Reference", "Date", "Customer", "Amount ($)"]
        return "Sales Performance Report", headers, rows, kpis

    if report_type == "segmentation":
        rfm = compute_rfm_segmentation(db, user_id, requested_clusters=int(thresholds.get("rfm_clusters", 5)))
        if not rfm.get("sufficient_data"):
            raise ValueError(rfm.get("message") or "Insufficient data for Segmentation Report.")
        kpis = [
            ("Segmented Customers", f"{rfm['total_customers']:,}"),
            ("Cohort Revenue", f"${rfm['total_revenue']:,.2f}"),
            ("K-Means Clusters", str(rfm["n_clusters"])),
            ("Silhouette Score", str(rfm["silhouette_score"] if rfm["silhouette_score"] is not None else "N/A")),
        ]
        headers = ["Customer", "External ID", "Segment", "Recency (Days)", "Frequency", "Monetary ($)"]
        rows = [
            [c["name"] or c["external_id"], c["external_id"], c["segment"], c["recency"], c["frequency"], f"{c['monetary']:,.2f}"]
            for c in rfm["customers"]
        ]
        return "RFM Customer Segmentation Report", headers, rows, kpis

    if report_type == "product_performance":
        data = get_sales_analytics(db, user_id)
        prods = data.get("top_products") or []
        db_prods = db.query(Product).filter(Product.user_id == user_id).all()
        if not prods and not db_prods:
            raise ValueError("Cannot generate Product Performance Report: no products or sales imported yet.")
        stock_lookup = {p.name: p.stock_quantity for p in db_prods}
        if prods:
            headers = ["Product", "SKU", "Category", "Units Sold", "Avg Price ($)", "Revenue ($)", "Stock"]
            rows = [
                [
                    p["name"],
                    p["sku"] or "—",
                    p["category"] or "Uncategorized",
                    p["units_sold"],
                    f"{p['avg_price']:,.2f}",
                    f"{p['revenue']:,.2f}",
                    stock_lookup.get(p["name"]) if stock_lookup.get(p["name"]) is not None else "N/A",
                ]
                for p in prods
            ]
        else:
            headers = ["Product", "SKU", "Category", "Unit Price ($)", "Stock Quantity"]
            rows = [
                [
                    p.name,
                    p.sku or "—",
                    p.category or "Uncategorized",
                    f"{p.unit_price:,.2f}" if p.unit_price is not None else "N/A",
                    p.stock_quantity if p.stock_quantity is not None else "N/A",
                ]
                for p in db_prods
            ]
        dash = get_dashboard_analytics(db, user_id)["summary"]
        kpis = [
            ("Total Products", f"{dash['total_products']:,}"),
            ("Total Revenue", f"${dash['total_revenue']:,.2f}"),
            ("Total Orders", f"{dash['total_orders']:,}"),
        ]
        return "Product Performance Report", headers, rows, kpis

    if report_type == "forecasts":
        fc = run_demand_forecast(
            db,
            user_id,
            granularity="weekly",
            horizon=int(thresholds.get("forecast_horizon", 4)),
        )
        if not fc.get("sufficient_data"):
            raise ValueError(fc.get("message") or "Insufficient historical periods for Demand Forecast Report.")
        m = fc.get("metrics") or {}
        kpis = [
            ("Model", fc["model_name"]),
            ("Historical Periods", str(fc["history_periods"])),
            ("Validation MAE", str(m.get("mae") if m.get("mae") is not None else "N/A")),
            ("Next Period Forecast", f"{fc.get('next_period_forecast', 0):.1f} units"),
        ]
        headers = ["Product / Scope", "Periods", "Model Used", "Next Period Units", "MAE", "RMSE"]
        rows = [
            [
                p["product_name"],
                p["history_periods"],
                p["model_name"],
                f"{p['next_period_forecast']:.1f}" if p["next_period_forecast"] is not None else "N/A",
                f"{p['mae']:.2f}" if p["mae"] is not None else "N/A",
                f"{p['rmse']:.2f}" if p["rmse"] is not None else "N/A",
            ]
            for p in (fc.get("product_summaries") or [])
        ]
        if not rows:
            rows = [
                [fc["target_label"], fc["history_periods"], fc["model_name"], f"{fc.get('next_period_forecast', 0):.1f}", str(m.get("mae") or "N/A"), str(m.get("rmse") or "N/A")]
            ]
        return "Demand Forecasting Report", headers, rows, kpis

    if report_type == "recommendations":
        insights = generate_smart_alerts(db, user_id)
        alerts = insights.get("alerts") or []
        if not alerts and insights.get("skipped_detectors"):
            raise ValueError("Cannot generate Recommendations Report: no analytics data imported yet.")
        s = insights["summary"]
        kpis = [
            ("Active Alerts", str(s["total"])),
            ("Critical / Warnings", str(s["critical_and_warning"])),
            ("Opportunities", str(s["opportunities"])),
        ]
        headers = ["Severity", "Category", "Finding", "Metric", "Recommended Action"]
        rows = [
            [a["severity"].upper(), a["category_label"], a["title"], a.get("metric_value") or "—", a["recommendation"]]
            for a in alerts
        ]
        if not rows:
            rows = [["INFO", "Status", "No threshold breaches detected", "—", "Continue monitoring as new CSV datasets are imported."]]
        return "Smart Insights & Recommendations Report", headers, rows, kpis

    raise ValueError(f"Unsupported report type '{report_type}'.")


def generate_csv_report(db: Session, user_id: int, report_type: str) -> Tuple[str, bytes]:
    title, headers, rows, kpis = _build_report_data(db, user_id, report_type)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([title])
    writer.writerow(["Generated UTC", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")])
    for label, val in kpis:
        writer.writerow([label, val])
    writer.writerow([])
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    filename = f"commerceiq_{report_type}_{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv"
    return filename, buf.getvalue().encode("utf-8-sig")


def generate_pdf_report(db: Session, user_id: int, report_type: str) -> Tuple[str, bytes]:
    title, headers, rows, kpis = _build_report_data(db, user_id, report_type)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "CIQTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=18,
        textColor=NAVY_HEX,
        spaceAfter=4,
    )
    meta_style = ParagraphStyle(
        "CIQMeta",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        textColor=PINK_HEX,
        spaceAfter=12,
    )
    cell_style = ParagraphStyle(
        "CIQCell",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        textColor=NAVY_HEX,
        leading=11,
    )
    head_cell_style = ParagraphStyle(
        "CIQHeadCell",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        textColor=colors.white,
        leading=11,
    )

    elements: List[Any] = [
        Paragraph(f"CommerceIQ — {title}", title_style),
        Paragraph(
            f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} · AI E-Commerce Intelligence System",
            meta_style,
        ),
    ]

    if kpis:
        kpi_data = [[Paragraph(f"<b>{k}</b><br/>{v}", cell_style) for k, v in kpis]]
        kpi_table = Table(kpi_data, colWidths=[(178 * mm) / len(kpis)] * len(kpis))
        kpi_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), TINT_HEX),
                    ("BOX", (0, 0), (-1, -1), 0.75, BORDER_HEX),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER_HEX),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        elements.append(kpi_table)
        elements.append(Spacer(1, 14))

    table_rows = [[Paragraph(str(h), head_cell_style) for h in headers]]
    for r in rows[:200]:
        table_rows.append([Paragraph(str(c), cell_style) for c in r])

    col_w = (178 * mm) / max(1, len(headers))
    data_table = Table(table_rows, colWidths=[col_w] * len(headers), repeatRows=1)
    data_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY_HEX),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, TINT_HEX]),
                ("BOX", (0, 0), (-1, -1), 0.75, BORDER_HEX),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, BORDER_HEX),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    elements.append(data_table)

    doc.build(elements)
    filename = f"commerceiq_{report_type}_{datetime.now(timezone.utc).strftime('%Y%m%d')}.pdf"
    return filename, buf.getvalue()
