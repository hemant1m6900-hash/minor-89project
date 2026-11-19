# AI E-Commerce Intelligence System

A complete, locally runnable enterprise e-commerce analytics and machine learning platform built with **HTML5 / CSS3 / Vanilla JavaScript / Chart.js**, **Python / FastAPI / Pandas / NumPy / Scikit-learn**, and **SQLite / SQLAlchemy**.

---

## Architecture & Project Structure

```text
├── .env.example
├── requirements.txt
├── ecommerce_intelligence.db          # Auto-created SQLite database on FastAPI startup
├── backend/
│   ├── main.py                        # FastAPI app, CORS, error handling, static frontend mount
│   ├── config.py                      # Environment & upload storage configuration
│   ├── database.py                    # SQLAlchemy 2.0 + SQLite engine (foreign_keys=ON, WAL mode)
│   ├── logger.py                      # Structured logging
│   ├── models.py                      # SQLite ORM models (users, datasets, uploaded_files, customers, products, orders, order_items, sales, analytics_metadata)
│   ├── schemas.py                     # Pydantic v2 request/response schemas
│   ├── security.py                    # PBKDF2-SHA256 password hashing & HS256 JWT auth
│   ├── routers/
│   │   ├── auth.py
│   │   ├── datasets.py
│   │   ├── analytics.py
│   │   ├── segmentation.py
│   │   ├── forecasting.py
│   │   ├── insights.py
│   │   ├── reports.py
│   │   └── settings.py
│   └── services/
│       ├── csv_processor.py           # Type detection, schema classification, missing/duplicate audit, cleaning
│       ├── ingestion_service.py       # Normalized SQLite ingestion & duplicate/re-import protection
│       ├── analytics_service.py       # Dashboard KPIs, filtered sales analytics, data capability checks
│       ├── rfm_service.py             # Scikit-learn StandardScaler + KMeans RFM segmentation
│       ├── forecast_service.py        # Moving Average baseline + Scikit-learn Ridge Regression forecasting
│       ├── insights_service.py        # Deterministic trend, anomaly (Z-score), churn & low-stock detectors
│       └── report_service.py          # Streaming CSV & ReportLab PDF exports
├── frontend/
│   ├── index.html                     # Login & Registration
│   ├── dashboard.html                 # Executive Dashboard
│   ├── csv-upload.html                # Multi-step CSV Upload, Profiling, Mapping & Cleaning
│   ├── data-management.html           # Dataset History, Capability Matrix, Re-Import & Deletion
│   ├── sales-analytics.html           # Filtered Sales Analytics
│   ├── customer-segmentation.html     # RFM K-Means Segmentation
│   ├── demand-forecasting.html        # Product Demand Forecasting
│   ├── smart-alerts.html              # Smart Insights & Alerts
│   ├── reports.html                   # CSV & PDF Reports Center
│   ├── settings.html                  # Thresholds, Account & Database Status
│   ├── css/styles.css                 # Navy (#0F1B3D), White (#FFFFFF), Hot Pink (#FF3D8B)
│   └── js/
│       ├── api.js
│       ├── auth.js
│       ├── layout.js
│       ├── charts.js
│       └── pages/*.js
├── storage/uploads/                   # Preserved original uploaded CSV files
└── tests/
    ├── conftest.py
    ├── test_auth.py
    ├── test_csv_ingestion.py
    ├── test_analytics_ml.py
    └── test_reports_api.py
```

---

## Local Setup & Installation

### 1. Prerequisites
- **Python 3.11+** (includes built-in `sqlite3`)

### 2. Configure Environment Variables (Optional)
```bash
cp .env.example .env
```
Default `.env.example` settings:
```env
DATABASE_URL=sqlite:///./ecommerce_intelligence.db
APP_SECRET_KEY=change-this-local-development-secret-key-at-least-32-chars
UPLOAD_DIR=storage/uploads
CORS_ORIGINS=http://localhost:8000,http://127.0.0.1:8000
LOG_LEVEL=INFO
```

### 3. Install Python Dependencies
```bash
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows PowerShell:
# .venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

### 4. Run the Application
```bash
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```
Open **`http://127.0.0.1:8000`** in your browser.
- FastAPI automatically creates **`ecommerce_intelligence.db`** and all database tables on startup (`Base.metadata.create_all`).
- Interactive OpenAPI Swagger documentation is available at `http://127.0.0.1:8000/docs`.

---

## Running Automated Tests
```bash
pytest -v
```
