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
