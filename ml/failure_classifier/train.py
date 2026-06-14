"""
ml/failure_classifier — XGBoost on AI4I 2020 (§1.10). Binary machine-failure classification
(any of TWF/HDF/PWF/OSF). Drop UDI/Product ID (leakage) + RNF (unlearnable). scale_pos_weight
for the ~3.4% positive rate; report failure-class F1/recall + PR-AUC (never accuracy).
Exports failure_xgb_v1.json → backend/models/.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, f1_score, recall_score
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shared.mlio import DATA, append_metric, load_feature_config, publish  # noqa: E402

EXPORT = Path(__file__).resolve().parent / "export"
EXPORT.mkdir(exist_ok=True)


def main() -> int:
    cfg = load_feature_config()["failure_classifier"]
    df = pd.read_csv(DATA / "raw" / "ai4i" / "ai4i.csv")
    df.columns = [c.strip() for c in df.columns]

    # binary target: machine failure (exclude RNF random failures)
    target_cols = [c for c in cfg["target_cols"] if c in df.columns]
    y = (df[target_cols].sum(axis=1) > 0).astype(int)

    drop = set(cfg["drop_cols"]) | {"Machine failure", "RNF"} | set(target_cols)
    X = df.drop(columns=[c for c in df.columns if c in drop], errors="ignore")
    # one-hot the 'Type' categorical (L/M/H)
    X = pd.get_dummies(X, columns=[c for c in ["Type"] if c in X.columns], drop_first=True)
    X = X.select_dtypes(include=[np.number])

    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, stratify=y,
                                          random_state=cfg["random_state"])
    spw = float((ytr == 0).sum() / max((ytr == 1).sum(), 1))
    clf = XGBClassifier(n_estimators=300, max_depth=4, learning_rate=0.08,
                        scale_pos_weight=spw, eval_metric="aucpr",
                        random_state=cfg["random_state"])
    clf.fit(Xtr, ytr)

    proba = clf.predict_proba(Xte)[:, 1]
    pred = (proba >= 0.5).astype(int)
    f1 = float(f1_score(yte, pred, zero_division=0))
    recall = float(recall_score(yte, pred, zero_division=0))
    pr_auc = float(average_precision_score(yte, proba))

    top = sorted(zip(X.columns, clf.feature_importances_), key=lambda t: -t[1])[:6]
    clf.save_model(EXPORT / "failure_xgb_v1.json")
    (EXPORT / "feature_order.json").write_text(
        __import__("json").dumps(list(X.columns)), encoding="utf-8")
    publish(EXPORT, "failure_xgb_v1.json", "feature_order.json")
    append_metric("failure_classifier", {
        "algorithm": "XGBoost", "trained_on": "AI4I 2020", "positive_rate": round(float(y.mean()), 4),
        "failure_f1": round(f1, 3), "failure_recall": round(recall, 3), "pr_auc": round(pr_auc, 3),
        "top_features": [t[0] for t in top],
    })
    print(f"\nfailure_clf: F1={f1:.3f} recall={recall:.3f} PR-AUC={pr_auc:.3f}")
    print(f"  top features: {[t[0] for t in top]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
