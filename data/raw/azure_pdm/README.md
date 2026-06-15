# Azure Predictive Maintenance (schema template only)

The Azure PdM telemetry/errors/maintenance/failures schema is referenced in `BUILD_GUIDE.md §1` as
a **design template** for the multi-stream maintenance data model. It is **not fetched or used by
any code path** — ForgeSight's sensor layer is the physics-informed synthetic stream in
[`data/synthetic/`](../../synthetic/), and the ML methods are validated on C-MAPSS / AI4I / Steel
Plates / CWRU.

This directory is intentionally a placeholder; no download is required.
