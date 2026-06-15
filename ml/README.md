# ml/ — Classical ML (Gate 2)

Each model is a self-contained directory with a runnable `train.py`, its `export/` artifacts, and a
**Kaggle-style `test.csv` → `submission.csv`** deliverable. The trained models:

- `anomaly/` — IsolationForest + EWMA control limits → `anomaly_iforest_v1.joblib`, `scaler_v1.joblib`
- `failure_classifier/` — XGBoost on AI4I 2020 → `failure_xgb_v1.json`, `feature_order.json`
- `rul/` — XGBoost on C-MAPSS FD001 (split by unit) → `rul_xgb_v1.joblib`
- `defect/` — LightGBM leakage-safe pipeline on UCI Steel Plates → `defect_pipeline_v1.joblib` + `threshold.json`
- `azure_pdm/` — XGBoost 24h-ahead failure prediction on Microsoft Azure PdM (100 machines, 2015;
  multi-source telemetry+errors+machines features, time-based split) → `failure_azure_xgb_v1.json`
- `bearing_features/` — CWRU/IMS RMS/kurtosis/crest/skew extraction (`extract_features.py`; runs on a
  committed deterministic sample if no Kaggle data) → `bearing_features.csv`
- `shared/feature_config.json` — train/serve parity (read by `train.py` AND `backend/tools/ml_tools.py`)
- `shared/mlio.py` — `publish()` (→ `backend/models/`), `append_metric()`, `write_submission()`

Run a model: `python ml/<model>/train.py`. Artifacts copy into `backend/models/` after Gate 2;
training never runs in the API. All scripts are deterministic (`random_state=42`) — re-running
reproduces byte-identical `submission.csv` files.

## Metrics (real benchmarks)
| Model | Dataset | Headline metric |
|---|---|---|
| anomaly | synthetic healthy 20d | recall 1.0 · precision 0.23 · **8.7 d lead time** |
| failure_classifier | AI4I 2020 | F1 0.678 · recall 0.909 · PR-AUC 0.799 |
| rul | C-MAPSS FD001 | holdout RMSE 16.39 · **official test RMSE 18.73** (100 units) |
| defect | UCI Steel Plates | PR-AUC 0.798 · threshold 0.9752 |
| azure_pdm | Azure PdM (100 machines) | PR-AUC 0.899 · recall 0.922 · F1 0.702 (24h-ahead) |

## test/submission CSV dimensions (the deliverable)
Each model dir holds `test.csv` (inputs, no label), `submission.csv` (predictions),
`sample_submission.csv` (expected shape) and `dimensions.json` (asserted at train time:
`test` rows == `submission` rows).

| Model | test.csv (rows × cols) | submission.csv (rows × cols) | submission columns |
|---|---|---|---|
| anomaly | 17280 × 13 | 17280 × 3 | `window_id, anomaly_score, is_anomalous` |
| failure_classifier | 2000 × 6 | 2000 × 3 | `id, failure_prob, failure_pred` |
| rul | 100 × 47 | 100 × 2 | `unit, rul_pred` |
| defect | 389 × 29 | 389 × 3 | `id, defect_prob, defect_pred` |
| azure_pdm | 73900 × 21 | 73900 × 3 | `id, failure_prob, failure_pred` |

`rul/submission.csv` is the canonical C-MAPSS FD001 test set (100 engine units), aligned to
`data/raw/cmapss/RUL_FD001.txt`.
