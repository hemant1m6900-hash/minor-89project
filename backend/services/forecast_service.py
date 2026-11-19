from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, root_mean_squared_error
from sqlalchemy.orm import Session

from backend.models import AnalyticsMetadata, Product, Sale


def _period_freq(granularity: str) -> str:
    return "M" if granularity == "monthly" else "W"


def _build_lag_features(values: np.ndarray, idx: int) -> List[float]:
    lag1 = float(values[idx - 1]) if idx - 1 >= 0 else float(values[0])
    lag2 = float(values[idx - 2]) if idx - 2 >= 0 else lag1
    roll3 = float(np.mean(values[max(0, idx - 3) : idx])) if idx > 0 else float(values[0])
    return [float(idx), lag1, lag2, roll3]


def _forecast_series(
    periods: List[pd.Period],
    quantities: np.ndarray,
    horizon: int,
    granularity: str,
) -> Dict[str, Any]:
    n = len(quantities)
    if n < 3:
        return {
            "sufficient_data": False,
            "ml_trained": False,
            "model_name": "Insufficient History",
            "history_periods": n,
            "message": f"Only {n} historical period(s) available. At least 3 periods are required for baseline forecasting, and 6+ for Scikit-learn regression.",
        }

    # Baseline Moving Average (window=3)
    window = min(3, n)
    baseline_in_sample: List[Optional[float]] = [None]
    for i in range(1, n):
        baseline_in_sample.append(round(float(np.mean(quantities[max(0, i - window) : i])), 2))

    # Case 1: 3-5 periods -> Honest Baseline Moving Average only
    if n < 6:
        mae = None
        rmse = None
        if n >= 4:
            actual_eval = quantities[2:]
            pred_eval = np.array([baseline_in_sample[i] for i in range(2, n)], dtype=float)
            mae = round(float(mean_absolute_error(actual_eval, pred_eval)), 2)
            rmse = round(float(root_mean_squared_error(actual_eval, pred_eval)), 2)

        series = [
            {
                "period": str(periods[i]),
                "actual": float(quantities[i]),
                "predicted": baseline_in_sample[i],
            }
            for i in range(n)
        ]
        future_forecasts: List[Dict[str, Any]] = []
        rolling_buf = list(quantities.astype(float))
        last_period = periods[-1]
        for step in range(1, horizon + 1):
            next_p = last_period + step
            pred = max(0.0, round(float(np.mean(rolling_buf[-window:])), 2))
            rolling_buf.append(pred)
            future_forecasts.append(
                {
                    "period": str(next_p),
                    "predicted": pred,
                    "method": "Baseline Moving Average",
                }
            )
            series.append({"period": str(next_p), "actual": None, "predicted": pred})

        return {
            "sufficient_data": True,
            "ml_trained": False,
            "model_name": "Moving Average Baseline",
            "history_periods": n,
            "metrics": {"mae": mae, "rmse": rmse},
            "next_period_forecast": future_forecasts[0]["predicted"] if future_forecasts else None,
            "series": series,
            "future_forecasts": future_forecasts,
            "explanation": f"Using 3-period Moving Average baseline ({n} periods available; Scikit-learn regression activates at >= 6 periods).",
        }

    # Case 2: >= 6 periods -> Scikit-learn Ridge Regression with lag & trend features + chronological holdout
    X_all = np.array([_build_lag_features(quantities, i) for i in range(2, n)], dtype=float)
    y_all = quantities[2:].astype(float)

    test_size = max(2, int(round(len(y_all) * 0.25)))
    if len(y_all) - test_size < 2:
        test_size = 1

    split_idx = len(y_all) - test_size
    X_train, X_test = X_all[:split_idx], X_all[split_idx:]
    y_train, y_test = y_all[:split_idx], y_all[split_idx:]

    eval_model = Ridge(alpha=1.0)
    eval_model.fit(X_train, y_train)
    y_test_pred = np.maximum(0.0, eval_model.predict(X_test))

    ml_mae = round(float(mean_absolute_error(y_test, y_test_pred)), 2)
    ml_rmse = round(float(root_mean_squared_error(y_test, y_test_pred)), 2)

    # Compare against baseline on exact same holdout window
    baseline_test_preds = np.array(
        [np.mean(quantities[max(0, (2 + split_idx + j) - window) : (2 + split_idx + j)]) for j in range(len(y_test))],
        dtype=float,
    )
    base_mae = round(float(mean_absolute_error(y_test, baseline_test_preds)), 2)

    # Refit final Ridge model on full historical window
    final_model = Ridge(alpha=1.0)
    final_model.fit(X_all, y_all)
    in_sample_preds = np.maximum(0.0, final_model.predict(X_all))

    series: List[Dict[str, Any]] = []
    for i in range(n):
        pred_val = None
        if i >= 2:
            pred_val = round(float(in_sample_preds[i - 2]), 2)
        series.append(
            {
                "period": str(periods[i]),
                "actual": float(quantities[i]),
                "predicted": pred_val,
            }
        )

    # Iterative multi-step horizon forecast
    extended_vals = list(quantities.astype(float))
    future_forecasts = []
    last_period = periods[-1]
    for step in range(1, horizon + 1):
        idx = len(extended_vals)
        feat = np.array([_build_lag_features(np.array(extended_vals), idx)], dtype=float)
        pred = max(0.0, round(float(final_model.predict(feat)[0]), 2))
        extended_vals.append(pred)
        next_p = last_period + step
        future_forecasts.append(
            {
                "period": str(next_p),
                "predicted": pred,
                "method": "Scikit-learn Ridge Regression",
            }
        )
        series.append({"period": str(next_p), "actual": None, "predicted": pred})

    return {
        "sufficient_data": True,
        "ml_trained": True,
        "model_name": "Scikit-learn Ridge Regression",
        "history_periods": n,
        "metrics": {"mae": ml_mae, "rmse": ml_rmse, "baseline_mae": base_mae},
        "next_period_forecast": future_forecasts[0]["predicted"] if future_forecasts else None,
        "series": series,
        "future_forecasts": future_forecasts,
        "explanation": f"Trained Scikit-learn Ridge Regression on {n} {granularity} periods (Holdout MAE {ml_mae} vs Baseline MAE {base_mae}).",
    }


def list_forecastable_products(db: Session, user_id: int, granularity: str = "weekly") -> List[Dict[str, Any]]:
    rows = (
        db.query(Sale.product_id, Sale.sale_date, Sale.quantity, Product.name)
        .join(Product, Sale.product_id == Product.id)
        .filter(Sale.user_id == user_id, Sale.sale_date.isnot(None))
        .all()
    )
    if not rows:
        return []
    df = pd.DataFrame(
        [{"product_id": r.product_id, "name": r.name, "dt": r.sale_date, "qty": int(r.quantity or 1)} for r in rows]
    )
    df["dt"] = pd.to_datetime(df["dt"], utc=True)
    freq = _period_freq(granularity)
    df["period"] = df["dt"].dt.tz_localize(None).dt.to_period(freq)
    grouped = (
        df.groupby(["product_id", "name"], as_index=False)
        .agg(periods_count=("period", "nunique"), total_units=("qty", "sum"))
        .sort_values(["periods_count", "total_units"], ascending=[False, False])
    )
    return [
        {
            "id": int(r["product_id"]),
            "name": str(r["name"]),
            "periods_count": int(r["periods_count"]),
            "total_units": int(r["total_units"]),
        }
        for _, r in grouped.iterrows()
    ]


def run_demand_forecast(
    db: Session,
    user_id: int,
    product_id: Optional[int] = None,
    granularity: str = "weekly",
    horizon: int = 4,
) -> Dict[str, Any]:
    freq = _period_freq(granularity)

    query = db.query(Sale.product_id, Sale.sale_date, Sale.quantity, Product.name).outerjoin(
        Product, Sale.product_id == Product.id
    ).filter(Sale.user_id == user_id, Sale.sale_date.isnot(None))

    if product_id is not None:
        query = query.filter(Sale.product_id == product_id)

    rows = query.all()
    if not rows:
        return {
            "sufficient_data": False,
            "message": "No dated sales records found in SQLite. Upload a sales or orders CSV with dates and quantities.",
        }

    df = pd.DataFrame(
        [
            {
                "product_id": r.product_id,
                "product_name": r.name or "All Products",
                "dt": r.sale_date,
                "qty": int(r.quantity or 1),
            }
            for r in rows
        ]
    )
    df["dt"] = pd.to_datetime(df["dt"], utc=True)
    df["period"] = df["dt"].dt.tz_localize(None).dt.to_period(freq)

    # Aggregate target series (fill continuous period gaps with 0 demand)
    target_agg = df.groupby("period")["qty"].sum().sort_index()
    full_range = pd.period_range(start=target_agg.index.min(), end=target_agg.index.max(), freq=freq)
    target_agg = target_agg.reindex(full_range, fill_value=0)

    target_label = (
        df["product_name"].iloc[0] if product_id is not None else "Aggregate Storewide Product Demand"
    )
    main_forecast = _forecast_series(list(target_agg.index), target_agg.values.astype(float), horizon, granularity)

    if not main_forecast.get("sufficient_data"):
        return main_forecast

    # Build per-product summary table for top products
    all_sales = (
        db.query(Sale.product_id, Sale.sale_date, Sale.quantity, Product.name)
        .join(Product, Sale.product_id == Product.id)
        .filter(Sale.user_id == user_id, Sale.sale_date.isnot(None))
        .all()
    )
    product_summaries: List[Dict[str, Any]] = []
    if all_sales:
        adf = pd.DataFrame(
            [{"product_id": r.product_id, "name": r.name, "dt": r.sale_date, "qty": int(r.quantity or 1)} for r in all_sales]
        )
        adf["dt"] = pd.to_datetime(adf["dt"], utc=True)
        adf["period"] = adf["dt"].dt.tz_localize(None).dt.to_period(freq)
        top_pids = (
            adf.groupby("product_id")["qty"].sum().sort_values(ascending=False).head(12).index.tolist()
        )
        for pid in top_pids:
            sub = adf[adf["product_id"] == pid]
            pname = str(sub["name"].iloc[0])
            p_agg = sub.groupby("period")["qty"].sum().sort_index()
            p_range = pd.period_range(start=p_agg.index.min(), end=p_agg.index.max(), freq=freq)
            p_agg = p_agg.reindex(p_range, fill_value=0)
            res = _forecast_series(list(p_agg.index), p_agg.values.astype(float), horizon, granularity)
            if res.get("sufficient_data"):
                product_summaries.append(
                    {
                        "product_id": int(pid),
                        "product_name": pname,
                        "history_periods": res["history_periods"],
                        "ml_trained": res["ml_trained"],
                        "model_name": res["model_name"],
                        "next_period_forecast": res["next_period_forecast"],
                        "mae": res["metrics"]["mae"],
                        "rmse": res["metrics"]["rmse"],
                    }
                )

    payload = {
        **main_forecast,
        "target_label": target_label,
        "granularity": granularity,
        "horizon": horizon,
        "product_summaries": product_summaries,
    }

    meta = (
        db.query(AnalyticsMetadata)
        .filter(AnalyticsMetadata.user_id == user_id, AnalyticsMetadata.meta_key == "forecast_latest")
        .first()
    )
    summary_meta = {
        "target_label": target_label,
        "model_name": main_forecast["model_name"],
        "ml_trained": main_forecast["ml_trained"],
        "next_period_forecast": main_forecast["next_period_forecast"],
        "metrics": main_forecast["metrics"],
    }
    if meta is None:
        db.add(AnalyticsMetadata(user_id=user_id, meta_key="forecast_latest", meta_value=summary_meta))
    else:
        meta.meta_value = summary_meta
    db.commit()

    return payload
