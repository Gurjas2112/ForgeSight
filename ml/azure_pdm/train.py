"""
ml/azure_pdm — XGBoost 24h-ahead machine-failure prediction on the Microsoft Azure Predictive
Maintenance dataset (100 machines, hourly 2015 telemetry, 762 component failures).

This turns the former "schema template" placeholder into a REAL validated model. Multi-source
feature engineering (Microsoft's reference recipe, leakage-safe):
  - telemetry: 24h rolling mean + std of volt/rotate/pressure/vibration (+ current values)
  - errors:    24h rolling error count per machine
  - machines:  age + model one-hot
Label: any component fails within the next `predict_horizon_hours`. Split is TIME-BASED
(train < test_split_date, test after) so future telemetry never leaks into training.

Exports failure_azure_xgb_v1.json + feature_order.json, a Kaggle-style test/submission deliverable,
and appends metrics. Validation-only (not a serve path), like rul/failure_classifier.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, f1_score, recall_score
from xgboost import XGBClassifier

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shared.mlio import (  # noqa: E402
    DATA, append_metric, load_feature_config, publish, write_submission)

MODEL_DIR = Path(__file__).resolve().parent
EXPORT = MODEL_DIR / "export"
EXPORT.mkdir(exist_ok=True)
RAW = DATA / "raw" / "azure_pdm"


def main() -> int:
    cfg = load_feature_config()["azure_pdm"]
    sensors = cfg["sensors"]
    win = cfg["roll_window_hours"]
    horizon = pd.Timedelta(hours=cfg["predict_horizon_hours"])

    tel = pd.read_csv(RAW / "PdM_telemetry.csv", parse_dates=["datetime"])
    tel = tel.sort_values(["machineID", "datetime"]).reset_index(drop=True)

    # --- telemetry rolling features (per machine, leakage-safe: only past `win` hours) ---
    grp = tel.groupby("machineID")
    for s in sensors:
        tel[f"{s}_rm{win}"] = grp[s].transform(lambda x: x.rolling(win, min_periods=1).mean())
        tel[f"{s}_rs{win}"] = grp[s].transform(lambda x: x.rolling(win, min_periods=2).std()).fillna(0.0)

    # --- 24h rolling error count merged onto the hourly telemetry grid ---
    err = pd.read_csv(RAW / "PdM_errors.csv", parse_dates=["datetime"])
    err_cnt = (err.groupby(["machineID", "datetime"]).size().rename("err").reset_index())
    tel = tel.merge(err_cnt, on=["machineID", "datetime"], how="left")
    tel["err"] = tel["err"].fillna(0.0)
    tel["err_24h"] = tel.groupby("machineID")["err"].transform(
        lambda x: x.rolling(win, min_periods=1).sum())

    # --- machine metadata ---
    mach = pd.read_csv(RAW / "PdM_machines.csv")
    tel = tel.merge(mach, on="machineID", how="left")
    tel = pd.get_dummies(tel, columns=["model"], prefix="model")

    # --- label: any failure within the next `horizon` (forward as-of join) ---
    fail = pd.read_csv(RAW / "PdM_failures.csv", parse_dates=["datetime"])
    fail = fail[["machineID", "datetime"]].drop_duplicates().sort_values(["datetime", "machineID"])
    tel_sorted = tel.sort_values("datetime")
    nxt = pd.merge_asof(tel_sorted, fail.rename(columns={"datetime": "next_fail"}),
                        left_on="datetime", right_on="next_fail", by="machineID",
                        direction="forward")
    tel = nxt.sort_values(["machineID", "datetime"]).reset_index(drop=True)
    tel["y"] = ((tel["next_fail"] - tel["datetime"]).le(horizon)
                & tel["next_fail"].notna()).astype(int)

    # --- downsample the hourly grid to keep classes balanced + runtime sane ---
    ds = cfg["downsample_hours"]
    tel = tel[tel["datetime"].dt.hour % ds == 0].reset_index(drop=True)

    feat = ([f"{s}_rm{win}" for s in sensors] + [f"{s}_rs{win}" for s in sensors]
            + sensors + ["err_24h", "age"]
            + [c for c in tel.columns if c.startswith("model_")])
    split = pd.Timestamp(cfg["test_split_date"])
    tr = tel[tel["datetime"] < split]
    te = tel[tel["datetime"] >= split].reset_index(drop=True)

    spw = float((tr["y"] == 0).sum() / max((tr["y"] == 1).sum(), 1))
    clf = XGBClassifier(n_estimators=300, max_depth=5, learning_rate=0.08,
                        subsample=0.8, colsample_bytree=0.8, scale_pos_weight=spw,
                        eval_metric="aucpr", random_state=cfg["random_state"])
    clf.fit(tr[feat], tr["y"])

    proba = clf.predict_proba(te[feat])[:, 1]
    pred = (proba >= 0.5).astype(int)
    f1 = float(f1_score(te["y"], pred, zero_division=0))
    recall = float(recall_score(te["y"], pred, zero_division=0))
    pr_auc = float(average_precision_score(te["y"], proba))
    top = sorted(zip(feat, clf.feature_importances_), key=lambda t: -t[1])[:6]

    clf.save_model(EXPORT / "failure_azure_xgb_v1.json")
    (EXPORT / "azure_feature_order.json").write_text(json.dumps(feat), encoding="utf-8")
    publish(EXPORT, "failure_azure_xgb_v1.json", "azure_feature_order.json")

    # --- Kaggle-style test/submission (the held-out time window) ---
    te_id = te.reset_index(drop=True)
    test_df = pd.DataFrame({"id": te_id.index.astype(int),
                            "machineID": te_id["machineID"].to_numpy(),
                            "datetime": te_id["datetime"].astype(str)})
    test_df = pd.concat([test_df, te_id[feat].reset_index(drop=True)], axis=1)
    sub = pd.DataFrame({"id": te_id.index.astype(int),
                        "failure_prob": np.round(proba, 6),
                        "failure_pred": pred.astype(int)})
    write_submission(MODEL_DIR, test_df, sub, key_cols=["id"])

    append_metric("azure_pdm", {
        "algorithm": "XGBoost (24h-ahead)", "trained_on": "Azure PdM (100 machines, 2015)",
        "split": "time-based (<2015-10-01 train)", "positive_rate": round(float(tel["y"].mean()), 4),
        "failure_f1": round(f1, 3), "failure_recall": round(recall, 3), "pr_auc": round(pr_auc, 3),
        "n_features": len(feat), "top_features": [t[0] for t in top],
    })
    print(f"\nazure_pdm: F1={f1:.3f} recall={recall:.3f} PR-AUC={pr_auc:.3f} "
          f"(test rows={len(te)}, pos_rate={tel['y'].mean():.3f})")
    print(f"  top features: {[t[0] for t in top]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
