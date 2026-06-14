"""
ml/rul — XGBoost RUL regression on NASA C-MAPSS FD001 (§1.10). RUL = max_cycle − cycle, capped
at 125 (piecewise-linear). Split BY ENGINE UNIT (GroupShuffleSplit) — row split leaks → fraudulent
RMSE. Rolling mean/std features; drop near-constant sensors. Exports rul_xgb_v1.joblib.

NOTE: this validates the RUL *method* on a real run-to-failure benchmark. At serve time the
sinter-fan RUL is a Tier-1 trend extrapolation to the 7.1 mm/s alarm (ml_tools.estimate_rul).
"""
from __future__ import annotations

import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_squared_error
from sklearn.model_selection import GroupShuffleSplit
from xgboost import XGBRegressor

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shared.mlio import DATA, append_metric, load_feature_config, publish  # noqa: E402

EXPORT = Path(__file__).resolve().parent / "export"
EXPORT.mkdir(exist_ok=True)

COLS = ["unit", "cycle"] + [f"op{i}" for i in range(1, 4)] + [f"s{i}" for i in range(1, 22)]


def main() -> int:
    cfg = load_feature_config()["rul"]
    raw = pd.read_csv(DATA / "raw" / "cmapss" / "train_FD001.txt", sep=r"\s+",
                      header=None, names=COLS)
    # RUL label, capped
    maxc = raw.groupby("unit")["cycle"].transform("max")
    raw["RUL"] = (maxc - raw["cycle"]).clip(upper=cfg["rul_cap_cycles"])

    sensors = [f"s{i}" for i in range(1, 22)]
    keep = [s for s in sensors if raw[s].std() > 1e-6]          # drop near-constant
    for s in keep:
        for w in cfg["roll_windows"]:
            raw[f"{s}_rm{w}"] = raw.groupby("unit")[s].transform(lambda x: x.rolling(w, min_periods=1).mean())
    feat = keep + [f"{s}_rm{w}" for s in keep for w in cfg["roll_windows"]]

    gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
    tr, te = next(gss.split(raw, groups=raw["unit"]))
    model = XGBRegressor(n_estimators=400, max_depth=5, learning_rate=0.05,
                         subsample=0.8, colsample_bytree=0.8, random_state=42)
    model.fit(raw.iloc[tr][feat], raw.iloc[tr]["RUL"])
    pred = model.predict(raw.iloc[te][feat])
    rmse = float(np.sqrt(mean_squared_error(raw.iloc[te]["RUL"], pred)))

    joblib.dump({"model": model, "features": feat}, EXPORT / "rul_xgb_v1.joblib")
    publish(EXPORT, "rul_xgb_v1.joblib")
    append_metric("rul", {
        "algorithm": "XGBoost", "trained_on": "C-MAPSS FD001", "split": "GroupShuffleSplit by unit",
        "rul_cap": cfg["rul_cap_cycles"], "rmse_cycles": round(rmse, 2), "n_features": len(feat),
    })
    print(f"\nrul: RMSE={rmse:.2f} cycles (target ~16-18, by-unit split)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
