# ml/ — Classical ML (Phase 2, deferred to Pass 2)

Each model is a self-contained notebook directory with its own `dataset/` and `export/`. Per
`BUILD_GUIDE.md §3`:

- `anomaly/` — IsolationForest + EWMA control limits → `anomaly_iforest_v1.joblib`, `scaler_v1.joblib`
- `failure_classifier/` — XGBoost on AI4I 2020 → `failure_xgb_v1.json`
- `rul/` — XGBoost on C-MAPSS FD001 (split by unit) → `rul_xgb_v1.joblib`
- `defect/` — LightGBM leakage-safe pipeline on UCI Steel Plates → `defect_pipeline_v1.joblib` + `threshold.json`
- `bearing_features/` — CWRU RMS/kurtosis/crest features
- `shared/feature_config.json` — train/serve parity (read by notebooks AND `backend/tools/ml_tools.py`)

Artifacts are copied into `backend/models/` after Gate 2. Training never runs in the API.
