"""Shared paths + metrics helper for the ml/ training scripts (train/serve parity lives in
feature_config.json). Each train.py exports to its export/ and copies to backend/models/."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
SHARED = ROOT / "ml" / "shared"
BACKEND_MODELS = ROOT / "backend" / "models"
METRICS = SHARED / "metrics.json"
FEATURE_CONFIG = SHARED / "feature_config.json"


def load_feature_config() -> dict:
    return json.loads(FEATURE_CONFIG.read_text(encoding="utf-8"))


def append_metric(model: str, payload: dict) -> None:
    """Append/overwrite this model's metrics block in ml/shared/metrics.json."""
    data = {}
    if METRICS.exists():
        try:
            data = json.loads(METRICS.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
    data[model] = payload
    METRICS.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"  metrics[{model}] = {json.dumps(payload)}")


def publish(export_dir: Path, *filenames: str) -> None:
    """Copy versioned artifacts from a model's export/ into backend/models/."""
    BACKEND_MODELS.mkdir(parents=True, exist_ok=True)
    for fn in filenames:
        src = export_dir / fn
        if src.exists():
            shutil.copy2(src, BACKEND_MODELS / fn)
            print(f"  published {fn} -> backend/models/")


def write_submission(model_dir: Path, test_df, submission_df, key_cols) -> dict:
    """Emit a Kaggle-style test/submission deliverable for one model, deterministically.

    Writes into model_dir:
      - test.csv            : held-out inputs (features + key columns, NO label)
      - submission.csv      : model predictions (key columns + prediction columns)
      - sample_submission.csv: key columns + zeroed predictions (the expected SHAPE)
      - dimensions.json     : rows x cols + column lists for each file

    Asserts test.csv and submission.csv have identical row counts so dimensions stay correct.
    Returns the dimensions dict (also appended to metrics by the caller if desired).
    """
    import json as _json

    model_dir.mkdir(parents=True, exist_ok=True)
    key_cols = list(key_cols)
    if test_df.shape[0] != submission_df.shape[0]:
        raise AssertionError(
            f"test rows ({test_df.shape[0]}) != submission rows ({submission_df.shape[0]})")

    test_df.to_csv(model_dir / "test.csv", index=False)
    submission_df.to_csv(model_dir / "submission.csv", index=False)

    pred_cols = [c for c in submission_df.columns if c not in key_cols]
    sample = submission_df[key_cols].copy()
    for c in pred_cols:
        sample[c] = 0
    sample.to_csv(model_dir / "sample_submission.csv", index=False)

    def _spec(df):
        return {"rows": int(df.shape[0]), "cols": int(df.shape[1]), "columns": list(df.columns)}

    dims = {
        "key_cols": key_cols,
        "test.csv": _spec(test_df),
        "submission.csv": _spec(submission_df),
        "sample_submission.csv": _spec(sample),
    }
    (model_dir / "dimensions.json").write_text(_json.dumps(dims, indent=2), encoding="utf-8")
    print(f"  submission: test={tuple(test_df.shape)} submission={tuple(submission_df.shape)}"
          f" -> {model_dir.name}/{{test,submission,sample_submission}}.csv")
    return dims
