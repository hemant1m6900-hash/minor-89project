from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, List

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler
from sqlalchemy.orm import Session

from backend.models import AnalyticsMetadata, Customer, Order

SEGMENT_NAMES_BY_COUNT: Dict[int, List[str]] = {
    2: ["Champions", "At-Risk"],
    3: ["Champions", "Loyal", "At-Risk"],
    4: ["Champions", "Loyal", "At-Risk", "Lost"],
    5: ["Champions", "Loyal", "Potential Loyalists", "At-Risk", "Lost"],
}


def _assign_segment_labels(cluster_rank: int, total_clusters: int) -> str:
    if total_clusters in SEGMENT_NAMES_BY_COUNT:
        return SEGMENT_NAMES_BY_COUNT[total_clusters][cluster_rank]
    # For >5 clusters, map smoothly into the 5 supported tiers
    ratio = cluster_rank / max(1, total_clusters - 1)
    if ratio <= 0.2:
        return "Champions"
    if ratio <= 0.4:
        return "Loyal"
    if ratio <= 0.6:
        return "Potential Loyalists"
    if ratio <= 0.8:
        return "At-Risk"
    return "Lost"


def compute_rfm_segmentation(db: Session, user_id: int, requested_clusters: int = 5) -> Dict[str, Any]:
    orders = (
        db.query(Order)
        .filter(
            Order.user_id == user_id,
            Order.customer_id.isnot(None),
            Order.order_date.isnot(None),
            Order.total_amount > 0,
        )
        .all()
    )

    if not orders:
        return {
            "sufficient_data": False,
            "message": "No dated customer orders found. Upload an orders/sales CSV with Customer ID, Order Date, and Amount.",
        }

    df = pd.DataFrame(
        [
            {
                "customer_id": o.customer_id,
                "order_id": o.id,
                "order_date": o.order_date,
                "amount": float(o.total_amount),
            }
            for o in orders
        ]
    )
    df["order_date"] = pd.to_datetime(df["order_date"], utc=True)

    reference_date = df["order_date"].max() + timedelta(days=1)

    rfm = df.groupby("customer_id", as_index=False).agg(
        recency=("order_date", lambda s: int((reference_date - s.max()).days)),
        frequency=("order_id", "nunique"),
        monetary=("amount", "sum"),
    )

    n_customers = int(len(rfm))
    if n_customers < 5:
        return {
            "sufficient_data": False,
            "message": f"RFM K-Means clustering requires at least 5 distinct customers with dated orders. Currently found: {n_customers}.",
        }

    # Prepare scaled features (log1p on skewed frequency & monetary)
    features = pd.DataFrame(
        {
            "recency": rfm["recency"].astype(float),
            "frequency": np.log1p(rfm["frequency"].astype(float)),
            "monetary": np.log1p(rfm["monetary"].astype(float)),
        }
    )

    distinct_points = int(len(features.drop_duplicates()))
    if distinct_points < 2:
        return {
            "sufficient_data": False,
            "message": "All customers currently have identical Recency, Frequency, and Monetary values; clustering cannot separate cohorts.",
        }

    effective_k = min(requested_clusters, distinct_points, max(2, n_customers // 2 if n_customers >= 6 else 2))
    effective_k = max(2, min(effective_k, 8))

    scaler = StandardScaler()
    scaled = scaler.fit_transform(features.values)

    kmeans = KMeans(n_clusters=effective_k, random_state=42, n_init=10)
    cluster_labels = kmeans.fit_predict(scaled)
    rfm["cluster"] = cluster_labels

    # Silhouette score only valid when 2 <= unique_labels <= n_samples - 1
    unique_labels = len(set(cluster_labels))
    sil_score = None
    if 2 <= unique_labels < n_customers:
        sil_score = round(float(silhouette_score(scaled, cluster_labels)), 4)

    # Rank clusters deterministically from best RFM (-z_R + z_F + z_M) to worst
    scaled_df = pd.DataFrame(scaled, columns=["z_r", "z_f", "z_m"])
    scaled_df["cluster"] = cluster_labels
    cluster_scores = (
        scaled_df.groupby("cluster")
        .mean()
        .assign(score=lambda x: -x["z_r"] + x["z_f"] + x["z_m"])
        .sort_values("score", ascending=False)
    )

    cluster_to_segment: Dict[int, str] = {}
    for rank_idx, cluster_id in enumerate(cluster_scores.index.tolist()):
        cluster_to_segment[int(cluster_id)] = _assign_segment_labels(rank_idx, len(cluster_scores))

    rfm["segment"] = rfm["cluster"].map(cluster_to_segment)

    # Persist RFM assignments onto Customer rows in SQLite
    customers_map = {
        c.id: c for c in db.query(Customer).filter(Customer.user_id == user_id).all()
    }

    customer_rows: List[Dict[str, Any]] = []
    for _, row in rfm.iterrows():
        cid = int(row["customer_id"])
        cust = customers_map.get(cid)
        if cust:
            cust.rfm_recency = int(row["recency"])
            cust.rfm_frequency = int(row["frequency"])
            cust.rfm_monetary = round(float(row["monetary"]), 2)
            cust.rfm_segment = str(row["segment"])
            cust.rfm_cluster = int(row["cluster"])
            customer_rows.append(
                {
                    "customer_id": cid,
                    "external_id": cust.external_id,
                    "name": cust.name,
                    "email": cust.email,
                    "recency": cust.rfm_recency,
                    "frequency": cust.rfm_frequency,
                    "monetary": cust.rfm_monetary,
                    "segment": cust.rfm_segment,
                }
            )

    customer_rows.sort(key=lambda c: c["monetary"], reverse=True)
    total_revenue = round(float(rfm["monetary"].sum()), 2)

    seg_summary_df = (
        rfm.groupby("segment", as_index=False)
        .agg(
            customer_count=("customer_id", "count"),
            total_revenue=("monetary", "sum"),
            avg_recency=("recency", "mean"),
            avg_frequency=("frequency", "mean"),
            avg_monetary=("monetary", "mean"),
        )
        .sort_values("total_revenue", ascending=False)
    )

    segments = [
        {
            "segment": str(r["segment"]),
            "customer_count": int(r["customer_count"]),
            "total_revenue": round(float(r["total_revenue"]), 2),
            "revenue_share_pct": round((float(r["total_revenue"]) / total_revenue) * 100, 1) if total_revenue > 0 else 0.0,
            "avg_recency": round(float(r["avg_recency"]), 1),
            "avg_frequency": round(float(r["avg_frequency"]), 1),
            "avg_monetary": round(float(r["avg_monetary"]), 2),
        }
        for _, r in seg_summary_df.iterrows()
    ]

    result = {
        "sufficient_data": True,
        "n_clusters": effective_k,
        "total_customers": n_customers,
        "total_revenue": total_revenue,
        "reference_date": reference_date.isoformat(),
        "silhouette_score": sil_score,
        "segments": segments,
        "customers": customer_rows,
    }

    meta = (
        db.query(AnalyticsMetadata)
        .filter(AnalyticsMetadata.user_id == user_id, AnalyticsMetadata.meta_key == "rfm_latest")
        .first()
    )
    if meta is None:
        meta = AnalyticsMetadata(user_id=user_id, meta_key="rfm_latest", meta_value={"n_clusters": effective_k, "silhouette_score": sil_score, "total_customers": n_customers})
        db.add(meta)
    else:
        meta.meta_value = {"n_clusters": effective_k, "silhouette_score": sil_score, "total_customers": n_customers}
    db.commit()

    return result
