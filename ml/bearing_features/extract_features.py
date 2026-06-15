"""
ml/bearing_features — time-domain vibration feature extraction for bearing health (§3.5).

Validates the *method* used by the synthetic sinter-fan degradation layer: windowed RMS,
kurtosis, crest factor, peak-to-peak, skew and std are the classic indicators that rise as a
rolling-element bearing develops a defect (CWRU / IMS run-to-failure literature).

Data source resolution (deterministic, always runnable):
  1. If data/raw/cwru/*.mat exist  -> load the Drive-End (DE) channel from each.
  2. Else if data/raw/ims/*        -> load IMS bearing test columns.
  3. Else                          -> synthesize a committed deterministic sample
                                      (ml/bearing_features/sample_de.csv): a healthy baseline that
                                      develops periodic bearing-fault impulses of growing amplitude,
                                      so the script runs with NO Kaggle download.

Output: ml/bearing_features/bearing_features.csv  (one row per window; feature columns).
Run:    python ml/bearing_features/extract_features.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import kurtosis, skew

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
CWRU = ROOT / "data" / "raw" / "cwru"
IMS = ROOT / "data" / "raw" / "ims"
SAMPLE = HERE / "sample_de.csv"

FS = 12_000          # CWRU DE sampling rate (Hz) — also used for the synthetic sample
WINDOW = 2_048       # samples per window (~0.17 s @ 12 kHz)
RANDOM_STATE = 42


def _synthesize_sample() -> np.ndarray:
    """Deterministic healthy->degrading bearing signal. Committed as sample_de.csv on first run."""
    rng = np.random.default_rng(RANDOM_STATE)
    n_windows = 40
    t = np.arange(WINDOW) / FS
    shaft = 2 * np.pi * 30                      # 30 Hz shaft rotation
    ring = 2 * np.pi * 3_000                    # bearing resonance excited by each impact
    sig = []
    for k in range(n_windows):
        sev = k / (n_windows - 1)               # 0 (healthy) -> 1 (failing)
        base = 0.4 * np.sin(shaft * t) + 0.03 * rng.standard_normal(WINDOW)
        # sparse, sharp impacts (outer-race defect): amplitude grows with severity ->
        # signal becomes impulsive -> kurtosis & crest factor climb (classic indicators).
        impulses = np.zeros(WINDOW)
        period = int(FS / 107)                  # ball-pass outer-race period
        decay = np.exp(-np.linspace(0, 25, period)) * np.sin(ring * t[:period])
        for start in range(0, WINDOW - period, period):
            impulses[start:start + period] += (4.0 * sev**1.5) * decay
        sig.append(base + impulses)
    return np.concatenate(sig)


def _load_signal() -> tuple[np.ndarray, str]:
    mats = list(CWRU.glob("*.mat")) if CWRU.exists() else []
    if mats:
        from scipy.io import loadmat
        chans = []
        for m in sorted(mats):
            d = loadmat(m)
            key = next((k for k in d if k.endswith("DE_time")), None)
            if key:
                chans.append(np.asarray(d[key]).ravel())
        if chans:
            return np.concatenate(chans), f"CWRU ({len(mats)} .mat files)"
    ims_files = list(IMS.glob("*")) if IMS.exists() else []
    ims_files = [f for f in ims_files if f.is_file() and not f.name.lower().endswith((".md", ".txt"))]
    if ims_files:
        arr = np.loadtxt(sorted(ims_files)[0])
        return (arr[:, 0] if arr.ndim > 1 else arr).ravel(), "IMS bearing test"
    if SAMPLE.exists():
        return pd.read_csv(SAMPLE)["amplitude"].to_numpy(), "committed sample_de.csv"
    sig = _synthesize_sample()
    pd.DataFrame({"amplitude": np.round(sig, 6)}).to_csv(SAMPLE, index=False)
    print(f"  wrote deterministic sample -> {SAMPLE.relative_to(ROOT)} ({len(sig)} samples)")
    # reload from the rounded CSV so the synth path and the cached-file path are byte-identical
    return pd.read_csv(SAMPLE)["amplitude"].to_numpy(), "synthesized sample (committed)"


def _features(window: np.ndarray) -> dict:
    rms = float(np.sqrt(np.mean(window**2)))
    peak = float(np.max(np.abs(window)))
    return {
        "rms": round(rms, 6),
        "kurtosis": round(float(kurtosis(window, fisher=True, bias=False)), 6),
        "crest_factor": round(peak / rms if rms else 0.0, 6),
        "peak_to_peak": round(float(np.ptp(window)), 6),
        "skew": round(float(skew(window, bias=False)), 6),
        "std": round(float(np.std(window)), 6),
    }


def main() -> int:
    signal, source = _load_signal()
    n = len(signal) // WINDOW
    if n == 0:
        print("ERROR: signal shorter than one window", file=sys.stderr)
        return 1
    rows = []
    for w in range(n):
        seg = signal[w * WINDOW:(w + 1) * WINDOW]
        rows.append({"window_id": w, **_features(seg)})
    out = pd.DataFrame(rows)
    out.to_csv(HERE / "bearing_features.csv", index=False)
    print(f"bearing_features: source={source} | windows={n} | "
          f"kurtosis {out['kurtosis'].iloc[0]:.2f}->{out['kurtosis'].iloc[-1]:.2f} "
          f"(rises as the defect develops)")
    print(f"  wrote {HERE.name}/bearing_features.csv  shape={out.shape}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
