"""
ml/anomaly — IsolationForest + per-sensor EWMA control limits (FR-5 · §1.10).
Fit on the healthy 20-day window; evaluate on the labelled window (is_anomaly), reporting
precision/recall + DETECTION LEAD TIME (days the model flags before the 7.1 mm/s crossing).
Exports anomaly_iforest_v1.joblib + scaler_v1.joblib → backend/models/.
"""
from __future__ import annotations

import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import precision_score, recall_score
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shared.mlio import (  # noqa: E402
    DATA, append_metric, load_feature_config, publish, write_submission)

MODEL_DIR = Path(__file__).resolve().parent
EXPORT = MODEL_DIR / "export"
EXPORT.mkdir(exist_ok=True)


def main() -> int:
    cfg = load_feature_config()["anomaly"]
    df = pd.read_csv(DATA / "synthetic" / "sensor_readings.csv", parse_dates=["ts"])
    feats = cfg["feature_cols"]

    # rolling features per equipment (parity with serve)
    df = df.sort_values(["equipment_id", "ts"]).reset_index(drop=True)
    w = cfg["roll_window"]
    for c in feats:
        df[f"{c}_rmean"] = df.groupby("equipment_id")[c].transform(lambda s: s.rolling(w, min_periods=1).mean())
    feat_cols = feats + [f"{c}_rmean" for c in feats]

    t0 = df["ts"].min()
    healthy_cut = t0 + pd.Timedelta(days=cfg["healthy_days"])
    train = df[df["ts"] < healthy_cut]
    test = df[df["ts"] >= healthy_cut]

    scaler = StandardScaler().fit(train[feat_cols])
    iforest = IsolationForest(contamination=cfg["contamination"],
                              random_state=cfg["random_state"], n_estimators=200)
    iforest.fit(scaler.transform(train[feat_cols]))

    # score test window: anomaly = iforest predicts -1
    pred = (iforest.predict(scaler.transform(test[feat_cols])) == -1).astype(int)
    y = test["is_anomaly"].to_numpy()
    precision = float(precision_score(y, pred, zero_division=0))
    recall = float(recall_score(y, pred, zero_division=0))

    # detection lead time on sinter-fan-2: first flag vs first 7.1 crossing
    fan = test[test.equipment_id == "sinter-fan-2"].copy()
    fan["flag"] = (iforest.predict(scaler.transform(fan[feat_cols])) == -1)
    crossing = fan[fan.vibration_de > 7.1]["ts"]
    flagged = fan[fan.flag]["ts"]
    lead_days = None
    if len(crossing) and len(flagged):
        lead_days = round((crossing.iloc[0] - flagged.iloc[0]).total_seconds() / 86400, 2)

    # --- Kaggle-style test/submission over the held-out (post-healthy) window, deterministic ---
    test_out = test.sort_values(["equipment_id", "ts"]).reset_index(drop=True).copy()
    Xte_scaled = scaler.transform(test_out[feat_cols])
    test_out["window_id"] = np.arange(len(test_out))
    score = iforest.decision_function(Xte_scaled)        # <0 => more anomalous
    is_anom = (iforest.predict(Xte_scaled) == -1).astype(int)
    test_df = test_out[["window_id", "equipment_id", "ts"] + feat_cols].copy()
    sub = pd.DataFrame({"window_id": test_out["window_id"].to_numpy(),
                        "anomaly_score": np.round(score, 6),
                        "is_anomalous": is_anom})
    write_submission(MODEL_DIR, test_df, sub, key_cols=["window_id"])

    joblib.dump(iforest, EXPORT / "anomaly_iforest_v1.joblib")
    joblib.dump(scaler, EXPORT / "scaler_v1.joblib")
    publish(EXPORT, "anomaly_iforest_v1.joblib", "scaler_v1.joblib")
    append_metric("anomaly", {
        "algorithm": "IsolationForest", "trained_on": "synthetic healthy 20d",
        "precision": round(precision, 3), "recall": round(recall, 3),
        "detection_lead_time_days": lead_days, "n_features": len(feat_cols),
    })
    print(f"\nanomaly: precision={precision:.3f} recall={recall:.3f} lead_time={lead_days}d")
    return 0


if __name__ == "__main__":
    sys.exit(main())
