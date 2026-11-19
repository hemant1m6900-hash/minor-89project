from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import register_and_login


def test_reports_csv_and_pdf_generation(client: TestClient) -> None:
    headers = register_and_login(client, "report_tester@example.com")

    # Empty state refuses to emit fake sales report
    empty_pdf = client.get("/api/reports/pdf/sales", headers=headers)
    assert empty_pdf.status_code == 422

    csv_data = (
        "order_id,order_date,customer_id,product_id,product_name,category,quantity,unit_price,total_amount\n"
        "R-1,2026-03-01,CU-1,PR-1,Desk Lamp,Lighting,2,35,70\n"
        "R-2,2026-03-08,CU-2,PR-1,Desk Lamp,Lighting,3,35,105\n"
    ).encode("utf-8")

    up = client.post(
        "/api/datasets/upload",
        headers=headers,
        files={"file": ("report_orders.csv", csv_data, "text/csv")},
    )
    assert up.status_code == 201
    prof = up.json()
    client.post(
        f"/api/datasets/{prof['dataset_id']}/import",
        headers=headers,
        json={"dataset_type": "orders", "column_mapping": prof["suggested_mapping"]},
    )

    csv_rep = client.get("/api/reports/csv/sales", headers=headers)
    assert csv_rep.status_code == 200
    assert "text/csv" in csv_rep.headers["content-type"]
    assert "Sales Performance Report" in csv_rep.text

    pdf_rep = client.get("/api/reports/pdf/sales", headers=headers)
    assert pdf_rep.status_code == 200
    assert pdf_rep.headers["content-type"] == "application/pdf"
    assert pdf_rep.content.startswith(b"%PDF")
