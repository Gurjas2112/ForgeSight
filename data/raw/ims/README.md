# NASA IMS Bearing Dataset (optional)

NSF I/UCR Center for Intelligent Maintenance Systems run-to-failure bearing test. **Optional** —
not required for Gate 1. The IMS degradation *shape* informs the synthetic sinter-fan trajectory
(see [`docs/assumptions_limitations.md`](../../../docs/assumptions_limitations.md)).

## How to populate
- Automatic: set `KAGGLE_USERNAME` / `KAGGLE_KEY` in `.env`, then
  `python data/fetch_data.py` (Kaggle slug `vinayak123tyagi/bearing-dataset`).
- Manual: drop the ASCII test-set files here (whitespace-separated columns, one per bearing channel).

## Expected layout
```
data/raw/ims/
  <test-set files>   # each row = one snapshot; columns = per-bearing vibration channels
```

If empty, `ml/bearing_features/extract_features.py` falls back to the committed sample signal.
