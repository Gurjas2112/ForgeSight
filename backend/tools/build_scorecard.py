"""
ForgeSight — build the committed model scorecard (backend/models/scorecard.json).
=================================================================================
The served API runs inside backend/ only (ml/ + data/ are NOT in the image — see .dockerignore),
so the held-out test rows the model panel needs must be baked into backend/. This script reads
each model's committed Kaggle-style deliverable (ml/<m>/test.csv + submission.csv) plus
ml/shared/metrics.json and writes ONE small JSON holding, per model:

  - dataset / algorithm / metrics (verbatim from the training run)
  - feature_order (the exact serve-time column order)
  - one representative held-out sample: the input feature row + the model's RECORDED prediction

ml_tools re-runs the live model on that exact row at serve time and reproduces the recorded
number (provably real, no fabricated inputs). For the lean Railway image the recorded value is
also the fallback if a heavy estimator import is unavailable.

Run (locally, with ml/ present):  python -m backend.tools.build_scorecard
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
ML = ROOT / "ml"
MODELS = ROOT / "backend" / "models"
OUT = MODELS / "scorecard.json"


def _coerce(v):
    """JSON-safe scalar (numpy bool/int/float -> python)."""
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    if isinstance(v, (int, np.integer)):
        return int(v)
    if isinstance(v, (float, np.floating)):
        return float(v)
    return str(v)


def _row_dict(df: pd.DataFrame, drop: list[str]) -> dict:
    rec = df.drop(columns=[c for c in drop if c in df.columns], errors="ignore").iloc[0]
    return {k: _coerce(v) for k, v in rec.items()}


def _merge(model: str, key: str) -> pd.DataFrame:
    test = pd.read_csv(ML / model / "test.csv")
    sub = pd.read_csv(ML / model / "submission.csv")
    return test.merge(sub, on=key, how="inner")


def build() -> dict:
    metrics = json.loads((ML / "shared" / "metrics.json").read_text(encoding="utf-8"))
    feat_order = json.loads((MODELS / "feature_order.json").read_text(encoding="utf-8"))
    azure_order = json.loads((MODELS / "azure_feature_order.json").read_text(encoding="utf-8"))
    card: dict = {}

    # --- anomaly (IsolationForest, live on DB sensors) — panel shows a held-out window ---
    a = _merge("anomaly", "window_id").sort_values("anomaly_score").reset_index(drop=True)
    card["anomaly"] = {
        "title": "Vibration anomaly detector", "dataset": "Synthetic steel-plant sensors (healthy 20d)",
        "algorithm": metrics["anomaly"]["algorithm"], "serve_mode": "live_on_sensors",
        "metrics": metrics["anomaly"], "key": "window_id",
        "sample": {"label": "most-anomalous held-out window",
                   "features": _row_dict(a, ["window_id", "equipment_id", "ts", "anomaly_score", "is_anomalous"]),
                   "recorded": {"anomaly_score": float(a["anomaly_score"].iloc[0]),
                                "is_anomalous": bool(a["is_anomalous"].iloc[0])}}}

    # --- defect (LightGBM, LIVE at serve time) — most-confident positive held-out plate ---
    d = _merge("defect", "id").sort_values("defect_prob", ascending=False).reset_index(drop=True)
    card["defect"] = {
        "title": "Surface-defect classifier", "dataset": "UCI Steel Plates Faults",
        "algorithm": metrics["defect"]["algorithm"], "serve_mode": "live_lightgbm",
        "metrics": metrics["defect"], "key": "id",
        "sample": {"label": "highest-probability held-out plate",
                   "features": _row_dict(d, ["id", "defect_prob", "defect_pred"]),
                   "recorded": {"defect_probability": float(d["defect_prob"].iloc[0]),
                                "defect_pred": int(d["defect_pred"].iloc[0])}}}

    # --- failure (AI4I XGBoost) — most-confident positive held-out machine row ---
    f = _merge("failure_classifier", "id").sort_values("failure_prob", ascending=False).reset_index(drop=True)
    card["failure_classifier"] = {
        "title": "Machine-failure classifier (AI4I)", "dataset": "AI4I 2020",
        "algorithm": metrics["failure_classifier"]["algorithm"], "serve_mode": "live_xgboost",
        "metrics": metrics["failure_classifier"], "key": "id", "feature_order": feat_order,
        "sample": {"label": "highest-probability held-out machine",
                   "features": _row_dict(f, ["id", "failure_prob", "failure_pred"]),
                   "recorded": {"failure_probability": float(f["failure_prob"].iloc[0]),
                                "failure_pred": int(f["failure_pred"].iloc[0])}}}

    # --- azure pdm (24h-ahead XGBoost) — most-confident positive held-out hour ---
    z = _merge("azure_pdm", "id").sort_values("failure_prob", ascending=False).reset_index(drop=True)
    card["azure_pdm"] = {
        "title": "24h-ahead failure predictor (Azure PdM)", "dataset": "Azure PdM (100 machines, 2015)",
        "algorithm": metrics["azure_pdm"]["algorithm"], "serve_mode": "live_xgboost",
        "metrics": metrics["azure_pdm"], "key": "id", "feature_order": azure_order,
        "sample": {"label": "highest-probability held-out machine-hour",
                   "features": _row_dict(z, ["id", "machineID", "datetime", "failure_prob", "failure_pred"]),
                   "recorded": {"failure_probability": float(z["failure_prob"].iloc[0]),
                                "failure_pred": int(z["failure_pred"].iloc[0])}}}

    # --- rul (C-MAPSS XGBoost benchmark) — one held-out engine unit ---
    r = _merge("rul", "unit").sort_values("rul_pred").reset_index(drop=True)
    rul_bundle_order = None  # rul features live in the joblib bundle; sample carries them in-order
    card["rul"] = {
        "title": "RUL regressor (C-MAPSS benchmark)", "dataset": "NASA C-MAPSS FD001",
        "algorithm": metrics["rul"]["algorithm"], "serve_mode": "live_xgboost",
        "metrics": metrics["rul"], "key": "unit", "feature_order": rul_bundle_order,
        "sample": {"label": "shortest-RUL held-out engine unit",
                   "features": _row_dict(r, ["unit", "cycle", "rul_pred"]),
                   "recorded": {"rul_pred_cycles": float(r["rul_pred"].iloc[0]),
                                "unit": int(r["unit"].iloc[0])}}}

    return card


def main() -> int:
    card = build()
    OUT.write_text(json.dumps(card, indent=2), encoding="utf-8")
    print(f"wrote {OUT} ({len(card)} models)")
    for m, c in card.items():
        print(f"  {m}: {c['serve_mode']} · sample.recorded={c['sample']['recorded']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
