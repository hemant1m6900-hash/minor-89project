from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import register_and_login


def test_ml_insufficient_data_then_full_pipeline(client: TestClient) -> None:
    headers = register_and_login(client, "ml_tester@example.com")

    # Empty state must refuse to invent RFM or forecasts
    rfm_empty = client.get("/api/segmentation/rfm", headers=headers)
    assert rfm_empty.status_code == 200
    assert rfm_empty.json()["sufficient_data"] is False

    fc_empty = client.post("/api/forecasting/run", headers=headers, json={"granularity": "weekly", "horizon": 4})
    assert fc_empty.status_code == 200
    assert fc_empty.json()["sufficient_data"] is False

    # Upload 8 weeks of orders across 6 distinct customers + inventory CSV
    rows = ["order_id,order_date,customer_id,customer_name,product_id,product_name,category,quantity,unit_price,total_amount"]
    dates = [
        "2026-01-05", "2026-01-12", "2026-01-19", "2026-01-26",
        "2026-02-02", "2026-02-09", "2026-02-16", "2026-02-23",
    ]
    for idx, dt in enumerate(dates):
        cid = f"CUST-{(idx % 6) + 1}"
        qty = idx + 2
        total = qty * 40
        rows.append(f"ORD-{idx+1},{dt},{cid},Customer {cid},SKU-1,USB Hub,Accessories,{qty},40,{total}")

    orders_bytes = ("\n".join(rows) + "\n").encode("utf-8")
    up = client.post(
        "/api/datasets/upload",
        headers=headers,
        files={"file": ("multi_week_orders.csv", orders_bytes, "text/csv")},
    )
    assert up.status_code == 201
    prof = up.json()
    imp = client.post(
        f"/api/datasets/{prof['dataset_id']}/import",
        headers=headers,
        json={"dataset_type": "orders", "column_mapping": prof["suggested_mapping"]},
    )
    assert imp.status_code == 200

    # RFM segmentation with 6 customers must succeed via Scikit-learn KMeans
    rfm_ok = client.post("/api/segmentation/rfm", headers=headers, json={"n_clusters": 3})
    assert rfm_ok.status_code == 200
    rfm_data = rfm_ok.json()
    assert rfm_data["sufficient_data"] is True
    assert rfm_data["total_customers"] == 6
    assert len(rfm_data["segments"]) >= 2

    # Demand forecasting with 8 weekly periods must train Scikit-learn Ridge Regression
    fc_ok = client.post("/api/forecasting/run", headers=headers, json={"granularity": "weekly", "horizon": 3})
    assert fc_ok.status_code == 200
    fc_data = fc_ok.json()
    assert fc_data["sufficient_data"] is True
    assert fc_data["ml_trained"] is True
    assert fc_data["metrics"]["mae"] is not None
    assert len(fc_data["future_forecasts"]) == 3

    # Alerts endpoint returns structured insights + explicit note that inventory CSV is missing
    alerts = client.get("/api/insights/alerts", headers=headers)
    assert alerts.status_code == 200
    assert any("Low Inventory" in s for s in alerts.json()["skipped_detectors"])
