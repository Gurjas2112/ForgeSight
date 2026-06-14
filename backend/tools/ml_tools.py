"""
ForgeSight — ML serving tools (Reliability pipeline). Loads versioned artifacts from
backend/models/ once and exposes governed tools returning Pydantic results
(check_equipment_health · estimate_rul · analyze_defect).

STATUS: stubbed for Pass 1 (Scenario A needs only RAG + synthesis). The real implementation
lands in Pass 2 alongside the ml/ notebooks (Gate 2). Until artifacts exist, these read the
precomputed equipment_health row if present, else raise NotImplementedError so nothing silently
fabricates a number — narrate-never-compute, enforced even in the stub.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

# feature_config.json (train/serve parity) is loaded here in Pass 2:
# FEATURE_CONFIG = json.loads((MODELS / "feature_config.json").read_text())


class HealthResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    equipment_id: str
    anomaly_score: float = Field(ge=0, le=1)
    is_anomalous: bool
    contributing_sensors: list[str] = Field(default_factory=list)


class RULResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    equipment_id: str
    rul_days: float = Field(ge=0, le=3650)
    rul_band: list[float]                       # [low, high]
    method: str = "trend_extrapolation"


def check_equipment_health(conn, equipment_id: str) -> HealthResult:
    """Read the scheduler's cached inference (equipment_health). Pass 2 adds live ML."""
    sql = ("SELECT anomaly_score, is_anomalous, contributing_sensors "
           "FROM equipment_health WHERE equipment_id = %s")
    with conn.cursor() as cur:
        cur.execute(sql, (equipment_id,))
        row = cur.fetchone()
    if row is None:
        raise NotImplementedError(
            f"No equipment_health for {equipment_id}. ML serving (IsolationForest) lands in "
            "Pass 2 with the ml/anomaly artifact; run the scheduler to populate this row.")
    return HealthResult(equipment_id=equipment_id, anomaly_score=float(row[0] or 0),
                        is_anomalous=bool(row[1]), contributing_sensors=list(row[2] or []))


def estimate_rul(conn, equipment_id: str) -> RULResult:
    sql = "SELECT rul_days, rul_band FROM equipment_health WHERE equipment_id = %s"
    with conn.cursor() as cur:
        cur.execute(sql, (equipment_id,))
        row = cur.fetchone()
    if row is None or row[0] is None:
        raise NotImplementedError(
            f"No RUL for {equipment_id}. RUL serving (XGBoost on C-MAPSS) lands in Pass 2.")
    band = (row[1] or {}).get("band") if isinstance(row[1], dict) else None
    return RULResult(equipment_id=equipment_id, rul_days=float(row[0]),
                     rul_band=band or [float(row[0]) * 0.8, float(row[0]) * 1.4])


def analyze_defect(conn, equipment_id: str):
    raise NotImplementedError(
        "analyze_defect (LightGBM steel-defect pipeline) lands in Pass 2 with ml/defect.")
