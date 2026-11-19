from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import register_and_login


def test_csv_upload_validation_duplicate_and_delete(client: TestClient) -> None:
    headers = register_and_login(client, "csv_tester@example.com")

    csv_content = (
        "Order ID,Order Date,Customer ID,Customer Name,Product ID,Product Name,Category,Quantity,Unit Price,Total Amount\n"
        "ORD-1001,2026-01-05,C-1,Alice,P-1,Wireless Mouse,Electronics,2,$25.00,$50.00\n"
        "ORD-1001,2026-01-05,C-1,Alice,P-1,Wireless Mouse,Electronics,2,$25.00,$50.00\n"
        "ORD-1002,2026-01-12,C-2,Bob,P-2,Keyboard,Electronics,1,$80.00,$80.00\n"
    ).encode("utf-8")

    up = client.post(
        "/api/datasets/upload",
        headers=headers,
        files={"file": ("orders_sample.csv", csv_content, "text/csv")},
        data={"name": "January Orders"},
    )
    assert up.status_code == 201, up.text
    profile = up.json()
    dataset_id = profile["dataset_id"]
    assert profile["duplicate_rows"] == 1
    assert profile["detected_type"] in ("orders", "sales")

    # Duplicate upload with identical SHA-256 must be blocked
    dup_up = client.post(
        "/api/datasets/upload",
        headers=headers,
        files={"file": ("orders_copy.csv", csv_content, "text/csv")},
    )
    assert dup_up.status_code == 409

    # Missing required amount mapping must fail cleanly with 422
    bad_import = client.post(
        f"/api/datasets/{dataset_id}/import",
        headers=headers,
        json={
            "dataset_type": "orders",
            "column_mapping": {"Order ID": "order_id", "Order Date": "order_date"},
            "cleaning_options": {"drop_duplicates": True, "trim_whitespace": True, "missing_numeric": "zero", "missing_text": "unknown"},
        },
    )
    assert bad_import.status_code == 422

    # Valid import commits deduplicated rows
    good_import = client.post(
        f"/api/datasets/{dataset_id}/import",
        headers=headers,
        json={
            "dataset_type": "orders",
            "column_mapping": profile["suggested_mapping"],
            "cleaning_options": {"drop_duplicates": True, "trim_whitespace": True, "missing_numeric": "zero", "missing_text": "unknown"},
        },
    )
    assert good_import.status_code == 200, good_import.text
    res = good_import.json()
    assert res["duplicates_removed"] == 1
    assert res["rows_imported"] == 2

    dash = client.get("/api/analytics/dashboard", headers=headers)
    assert dash.status_code == 200
    assert dash.json()["summary"]["total_revenue"] == 130.0

    # Deleting dataset purges imported records cleanly
    delete_resp = client.delete(f"/api/datasets/{dataset_id}", headers=headers)
    assert delete_resp.status_code == 200

    dash_after = client.get("/api/analytics/dashboard", headers=headers)
    assert dash_after.json()["summary"]["total_revenue"] == 0.0
