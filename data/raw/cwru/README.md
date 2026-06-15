# CWRU Bearing Dataset (optional)

Case Western Reserve University bearing run-to-failure vibration data. **Optional** — not required
for Gate 1; it feeds the bearing-degradation feature method validated in
[`ml/bearing_features/extract_features.py`](../../../ml/bearing_features/extract_features.py).

## How to populate
- Automatic: set `KAGGLE_USERNAME` / `KAGGLE_KEY` in `.env`, then
  `python data/fetch_data.py` (Kaggle slug `brjapon/cwru-bearing-datasets`).
- Manual: drop the `.mat` files here. Each MATLAB file holds a Drive-End channel under a key ending
  in `DE_time` (e.g. `X097_DE_time`).

## Expected layout
```
data/raw/cwru/
  *.mat          # 12 kHz Drive-End vibration records (healthy + IR/OR/ball faults)
```

If this directory is empty, `extract_features.py` falls back to a committed deterministic sample
(`ml/bearing_features/sample_de.csv`) so the feature method is always runnable offline.
