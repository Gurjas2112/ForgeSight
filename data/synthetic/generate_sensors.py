"""
ForgeSight — Phase 1 synthetic steel sensor layer.
===================================================
6 equipment × 30 days × 1 reading / 5 min = 51,840 rows. Healthy baseline = daily
load-cycle + noise. Two injected faults (BUILD_GUIDE.md §2.2):

  (a) Sinter ID Fan #2  — gradual DE-bearing vibration ramp (accelerating, IMS-shaped)
                          crossing the 7.1 mm/s ISO-10816 alarm near the end of the window.
  (b) HSM F3 Stand      — a discrete VFD overvoltage trip event (current spike → coast-down).

A separate `is_anomaly` column labels the injected windows (evaluation only — the models
never see it at train time except as held-out validation). Dates/codes align with
breakdown_history.json (BR-2024-0312 etc.) and the demo narrative.

Run:  python data/synthetic/generate_sensors.py
Gate 1 assert: ~52k rows · 6 equipment · is_anomaly present · max vibration_de(sinter-fan-2) > 7.1
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
OUT_CSV = HERE / "sensor_readings.csv"

# Pull the canonical 6-equipment registry from the corpus module (single source of truth).
sys.path.insert(0, str(HERE.parent / "corpus"))
try:
    from seed_corpus import EQUIPMENT  # type: ignore
except Exception:  # pragma: no cover - fallback keeps the generator standalone
    EQUIPMENT = [
        {"id": "hsm-f3-stand"}, {"id": "sinter-fan-2"}, {"id": "caster-1"},
        {"id": "bf-stove-a"}, {"id": "ladle-crane-4"}, {"id": "sinter-fan-1"},
    ]

RNG = np.random.default_rng(42)

DAYS = 30
STEP_MIN = 5
PER_DAY = (24 * 60) // STEP_MIN              # 288 readings/day
N = DAYS * PER_DAY                           # 8640 rows / equipment
# 30-day window ending "now" in demo terms (today = 2026-06-15).
END = datetime(2026, 6, 15, 6, 40, tzinfo=timezone.utc)
START = END - timedelta(days=DAYS)

# Per-equipment healthy operating point: vib (mm/s), temp (°C), current (A), rpm, load (%).
BASELINE = {
    "hsm-f3-stand":  dict(vib=2.2, temp=58, cur=240, rpm=0,    load=72),   # rpm 0: stand, not rotating
    "sinter-fan-2":  dict(vib=2.6, temp=62, cur=185, rpm=990,  load=80),
    "sinter-fan-1":  dict(vib=2.4, temp=60, cur=180, rpm=990,  load=78),
    "caster-1":      dict(vib=1.8, temp=54, cur=310, rpm=120,  load=85),
    "bf-stove-a":    dict(vib=1.5, temp=70, cur=95,  rpm=0,    load=68),
    "ladle-crane-4": dict(vib=2.0, temp=52, cur=140, rpm=60,   load=45),
}


def _daily_cycle(t_frac: np.ndarray) -> np.ndarray:
    """Smooth diurnal load factor in [~0.9, ~1.1] (two production peaks/day)."""
    return 1.0 + 0.06 * np.sin(2 * np.pi * t_frac) + 0.03 * np.sin(4 * np.pi * t_frac)


def _healthy(eq_id: str, ts: pd.DatetimeIndex) -> pd.DataFrame:
    b = BASELINE[eq_id]
    day_frac = (ts.hour * 60 + ts.minute) / (24 * 60)
    cyc = _daily_cycle(day_frac.to_numpy())
    n = len(ts)
    return pd.DataFrame({
        "vibration_de":  b["vib"] + 0.15 * RNG.standard_normal(n),
        "vibration_nde": b["vib"] * 0.85 + 0.12 * RNG.standard_normal(n),
        "bearing_temp":  b["temp"] * (0.5 + 0.5 * cyc) + 0.4 * RNG.standard_normal(n),
        "motor_current": b["cur"] * cyc + 2.0 * RNG.standard_normal(n),
        "rpm":           b["rpm"] * (cyc if b["rpm"] else 1.0) + (3.0 * RNG.standard_normal(n) if b["rpm"] else 0.0),
        "load_pct":      np.clip(b["load"] * cyc + 1.5 * RNG.standard_normal(n), 0, 100),
    })


def _inject_fan_ramp(df: pd.DataFrame, ts: pd.DatetimeIndex) -> np.ndarray:
    """Accelerating DE-bearing degradation on sinter-fan-2. IMS-like convex ramp:
    deviation = A * progress**p, beginning at day ~18, crossing 7.1 mm/s near day ~29-30.
    Bearing temp creeps up in sympathy. Returns the is_anomaly mask (the labelled window)."""
    t = np.arange(len(df))
    start = int(18 * PER_DAY)                       # onset ~ day 18
    progress = np.clip((t - start) / (len(df) - start), 0, None)
    ramp = 5.4 * (progress ** 2.4)                  # peak deviation ~5.4 → ~2.6 + 5.4 ≈ 8.0 final
    df["vibration_de"] = df["vibration_de"].to_numpy() + ramp
    df["vibration_nde"] = df["vibration_nde"].to_numpy() + 0.55 * ramp
    df["bearing_temp"] = df["bearing_temp"].to_numpy() + 9.0 * (progress ** 2.0)
    # Label the injected degradation window: once deviation is meaningfully above noise.
    return (ramp > 0.8).astype(int)


def _inject_f3_trip(df: pd.DataFrame, ts: pd.DatetimeIndex) -> np.ndarray:
    """Discrete VFD overvoltage trip near the window end: current spikes on a hard
    deceleration, the drive trips (current → ~0), ~12 min downtime, then restart."""
    mask = np.zeros(len(df), dtype=int)
    trip_idx = len(df) - 3                           # ~10 min before the window end (06:40)
    pre = slice(max(0, trip_idx - 2), trip_idx)      # ~10 min of regen overvoltage build-up
    down = slice(trip_idx, min(len(df), trip_idx + 3))  # ~12 min tripped/down
    cur = df["motor_current"].to_numpy(copy=True)
    vib = df["vibration_de"].to_numpy(copy=True)
    cur[pre] = cur[pre] * 1.9 + 120                  # regen current spike
    vib[pre] = vib[pre] + 1.2
    cur[down] = RNG.uniform(0, 4, size=len(range(*down.indices(len(df)))))  # tripped
    vib[down] = RNG.uniform(0.1, 0.4, size=len(range(*down.indices(len(df)))))
    df["motor_current"] = cur
    df["vibration_de"] = vib
    mask[pre] = 1
    mask[down] = 1
    return mask


def generate() -> pd.DataFrame:
    ts = pd.date_range(START, periods=N, freq=f"{STEP_MIN}min", tz=timezone.utc)
    frames: list[pd.DataFrame] = []
    for eq in EQUIPMENT:
        eq_id = eq["id"]
        df = _healthy(eq_id, ts)
        anomaly = np.zeros(len(df), dtype=int)
        if eq_id == "sinter-fan-2":
            anomaly = _inject_fan_ramp(df, ts)
        elif eq_id == "hsm-f3-stand":
            anomaly = _inject_f3_trip(df, ts)
        df.insert(0, "equipment_id", eq_id)
        df.insert(1, "ts", ts)
        df["is_anomaly"] = anomaly
        # round to plausible instrument precision
        for c in ("vibration_de", "vibration_nde", "bearing_temp", "motor_current", "rpm", "load_pct"):
            df[c] = df[c].round(3)
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def main() -> int:
    df = generate()
    df.to_csv(OUT_CSV, index=False)

    n_rows = len(df)
    n_equip = df["equipment_id"].nunique()
    fan_max = df.loc[df.equipment_id == "sinter-fan-2", "vibration_de"].max()
    n_anom = int(df["is_anomaly"].sum())
    print(f"wrote {OUT_CSV}")
    print(f"  rows={n_rows}  equipment={n_equip}  anomaly_labels={n_anom}")
    print(f"  max vibration_de(sinter-fan-2) = {fan_max:.2f} mm/s  (alarm 7.1)")

    ok = True
    if not (50_000 <= n_rows <= 54_000):
        print(f"  ASSERT FAIL: expected ~51840 rows, got {n_rows}"); ok = False
    if n_equip != 6:
        print(f"  ASSERT FAIL: expected 6 equipment, got {n_equip}"); ok = False
    if "is_anomaly" not in df.columns:
        print("  ASSERT FAIL: is_anomaly column missing"); ok = False
    if not fan_max > 7.1:
        print(f"  ASSERT FAIL: fan vibration must cross 7.1, got {fan_max:.2f}"); ok = False
    if not ok:
        print("\nGATE 1 (sensors) NOT met.")
        return 1
    print("\nGATE 1 (sensors): all asserts passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
