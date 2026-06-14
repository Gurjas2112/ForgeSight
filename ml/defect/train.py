"""
ml/defect — LightGBM leakage-safe pipeline on UCI Steel Plates Faults (§1.10).
Binary target: a recognised named defect (Pastry/Z_Scratch/K_Scatch/Stains/Dirtiness/Bumps)
vs Other_Faults. The PCA-reconstruction-residual + kNN-distance-to-normal features are fit
INSIDE each CV fold (custom transformer inside a sklearn Pipeline) — refit per fold, never a
global fit, which is the leakage bug the design calls out. OOF threshold (precision-first →
F-beta=3). Exports defect_pipeline_v1.joblib + threshold.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.metrics import average_precision_score, fbeta_score, precision_recall_curve
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import Pipeline

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # repo root for backend import
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # ml/ for shared
from shared.mlio import DATA, append_metric, load_feature_config, publish  # noqa: E402
# AnomalyFeatures lives in backend so the pickled pipeline unpickles at serve time.
from backend.tools.defect_features import AnomalyFeatures  # noqa: E402

EXPORT = Path(__file__).resolve().parent / "export"
EXPORT.mkdir(exist_ok=True)

NAMED = ["Pastry", "Z_Scratch", "K_Scatch", "Stains", "Dirtiness", "Bumps"]


def main() -> int:
    cfg = load_feature_config()["defect"]
    df = pd.read_csv(DATA / "raw" / "steel_plates" / "steel_plates.csv")
    df.columns = [c.strip() for c in df.columns]
    named = [c for c in NAMED if c in df.columns]
    feat_cols = [c for c in df.columns if c not in named + ["Other_Faults"]]
    X = df[feat_cols].apply(pd.to_numeric, errors="coerce").fillna(df[feat_cols].median(numeric_only=True))
    y = (df[named].sum(axis=1) > 0).astype(int).to_numpy()

    spw = float((y == 0).sum() / max((y == 1).sum(), 1))
    pipe = Pipeline([
        ("anom", AnomalyFeatures(cfg["pca_components"], cfg["knn_neighbors"])),
        ("clf", LGBMClassifier(n_estimators=300, max_depth=-1, learning_rate=0.05,
                               scale_pos_weight=spw, random_state=cfg["random_state"], verbose=-1)),
    ])

    # StratifiedKFold = a single partition (required by cross_val_predict for OOF); the
    # per-fold AnomalyFeatures refit keeps it leakage-safe.
    cv = StratifiedKFold(n_splits=cfg["n_splits"], shuffle=True, random_state=cfg["random_state"])
    oof = cross_val_predict(pipe, X, y, cv=cv, method="predict_proba")[:, 1]
    pr_auc = float(average_precision_score(y, oof))

    # OOF threshold: highest-precision reaching recall>=0.7, else max F-beta=3
    prec, rec, thr = precision_recall_curve(y, oof)
    cutoff, basis = 0.5, "default"
    ok = [(p, t) for p, r, t in zip(prec[:-1], rec[:-1], thr) if r >= 0.7]
    if ok:
        cutoff = float(max(ok, key=lambda pt: pt[0])[1]); basis = "precision@recall>=0.7"
    else:
        fb = [(fbeta_score(y, (oof >= t).astype(int), beta=cfg["f_beta"], zero_division=0), t) for t in thr]
        cutoff = float(max(fb, key=lambda ft: ft[0])[1]); basis = "max F-beta=3"

    pipe.fit(X, y)
    joblib.dump({"pipeline": pipe, "features": feat_cols}, EXPORT / "defect_pipeline_v1.joblib")
    (EXPORT / "threshold.json").write_text(json.dumps(
        {"cutoff": round(cutoff, 4), "basis": basis, "pr_auc": round(pr_auc, 3),
         "positive_rate": round(float(y.mean()), 3)}, indent=2), encoding="utf-8")
    publish(EXPORT, "defect_pipeline_v1.joblib", "threshold.json")
    append_metric("defect", {
        "algorithm": "LightGBM + PCA-residual/kNN (leakage-safe per fold)",
        "trained_on": "UCI Steel Plates", "pr_auc": round(pr_auc, 3),
        "threshold": round(cutoff, 4), "threshold_basis": basis,
    })
    print(f"\ndefect: PR-AUC={pr_auc:.3f} threshold={cutoff:.4f} ({basis})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
