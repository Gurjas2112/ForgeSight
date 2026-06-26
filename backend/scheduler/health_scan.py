"""
ForgeSight — proactive health scan (FR-5/FR-7 · §1.6). For each equipment: ML health +
RUL → UPSERT equipment_health → deterministic severity rule → INSERT alert (Realtime fires
the toast). Runs every 30s under APScheduler; `--once` runs a single pass for the demo/Gate 4.

Run once:  python backend/scheduler/health_scan.py --once   (DATABASE_URL set)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

try:                                      # Windows consoles default to cp1252
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except Exception:  # noqa: BLE001
    pass

from backend.db.connection import get_pool  # noqa: E402
from backend.tools.deterministic import severity_rule  # noqa: E402
from backend.tools.ml_tools import check_equipment_health, estimate_rul  # noqa: E402
from backend.tools.spares import check_spares  # noqa: E402

ALARM = 7.1


def scan_once() -> int:
    pool = get_pool()
    n_alerts = 0
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM equipment")
            eqs = [r[0] for r in cur.fetchall()]
        for eq in eqs:
            try:
                health = check_equipment_health(conn, eq)
                rul = estimate_rul(conn, eq)
            except Exception as e:  # noqa: BLE001
                print(f"  [skip] {eq}: {e}"); continue
            spares = check_spares(conn, eq)
            lead = min((s.lead_time_days for s in spares), default=999)

            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO equipment_health (equipment_id, anomaly_score, is_anomalous, "
                    "rul_days, rul_band, contributing_sensors, computed_at) "
                    "VALUES (%s,%s,%s,%s,%s::jsonb,%s::jsonb, now()) "
                    "ON CONFLICT (equipment_id) DO UPDATE SET anomaly_score=EXCLUDED.anomaly_score, "
                    "is_anomalous=EXCLUDED.is_anomalous, rul_days=EXCLUDED.rul_days, "
                    "rul_band=EXCLUDED.rul_band, contributing_sensors=EXCLUDED.contributing_sensors, "
                    "computed_at=now()",
                    (eq, health.anomaly_score, health.is_anomalous, rul.rul_days,
                     json.dumps({"band": rul.rul_band}), json.dumps(health.contributing_sensors)))

            sev = severity_rule(
                anomaly_score=health.anomaly_score, sustained_windows=3 if health.is_anomalous else 0,
                projected_crossing_days=rul.rul_days if rul.current_vibration_mm_s < ALARM else None,
                rul_days=rul.rul_days, lead_time_days=lead,
                limit_breached_now=rul.current_vibration_mm_s >= ALARM)
            if sev in ("warning", "high", "critical"):
                title = (f"{sev.upper()} — {eq}: anomaly {health.anomaly_score}, "
                         f"RUL ≈ {rul.rul_days}d (lead {lead}d)")
                with conn.cursor() as cur:
                    # Only raise a new alert when an identical one isn't already open — otherwise
                    # a perpetually-anomalous asset floods the feed with duplicate rows each scan.
                    cur.execute(
                        "INSERT INTO alerts (equipment_id, severity, title, detail, target_role) "
                        "SELECT %s,%s,%s,%s::jsonb,'engineer' "
                        "WHERE NOT EXISTS (SELECT 1 FROM alerts "
                        "WHERE equipment_id=%s AND severity=%s AND acked_at IS NULL)",
                        (eq, sev, title, json.dumps({
                            "anomaly_score": health.anomaly_score, "rul_days": rul.rul_days,
                            "current_mm_s": rul.current_vibration_mm_s, "lead_time_days": lead}),
                         eq, sev))
                    if cur.rowcount:
                        n_alerts += 1
                        print(f"  [alert:{sev}] {title}")
    print(f"scan complete · {n_alerts} alert(s) raised")
    return n_alerts


def main() -> int:
    if "--once" in sys.argv:
        scan_once()
        return 0
    from apscheduler.schedulers.blocking import BlockingScheduler
    sched = BlockingScheduler()
    sched.add_job(scan_once, "interval", seconds=30, next_run_time=None)
    print("APScheduler: health scan every 30s (Ctrl-C to stop)")
    scan_once()
    sched.start()
    return 0


if __name__ == "__main__":
    sys.exit(main())
