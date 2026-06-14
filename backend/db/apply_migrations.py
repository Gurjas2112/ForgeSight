"""
ForgeSight — apply DB schema + seeds + corpus to Supabase (idempotent).
Run AFTER Phase 1 (sensor_readings.csv, breakdown_history.json, corpus_ingest.sql exist)
and AFTER setting DATABASE_URL in .env.

Order:
  1. migrations.sql      — schema, RLS, analytics views, SELECT-only role
  2. seed_data.sql       — equipment + spares
  3. seed_accounts.sql   — demo engineer/admin (best-effort; auth.users may need admin API)
  4. corpus_ingest.sql   — doc_chunks (RAG corpus, embedded)
  5. breakdown_history.json → breakdown_history table
  6. sensor_readings.csv    → sensor_readings table (COPY, fast)

Run:  python backend/db/apply_migrations.py
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

# Make `backend` importable when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

try:                                      # Windows consoles default to cp1252
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except Exception:  # noqa: BLE001
    pass

from backend.db.connection import connect  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "backend" / "db"
DATA = ROOT / "data"


def _auth_users_exists(conn) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('auth.users')")
        return (cur.fetchone() or [None])[0] is not None


def _run_sql_file(conn, path: Path, *, optional: bool = False) -> None:
    if not path.exists():
        msg = f"  [skip] {path.name} not found"
        if optional:
            print(msg); return
        raise FileNotFoundError(path)
    print(f"  [sql ] {path.relative_to(ROOT)}")
    with conn.cursor() as cur:
        cur.execute(path.read_text(encoding="utf-8"))


def _load_breakdowns(conn) -> None:
    path = DATA / "synthetic" / "breakdown_history.json"
    if not path.exists():
        print("  [skip] breakdown_history.json not found"); return
    records = json.loads(path.read_text(encoding="utf-8"))
    sql = """
        INSERT INTO breakdown_history
          (id, equipment_id, occurred_at, fault_code, symptoms, root_cause,
           resolution, downtime_hrs, verified)
        VALUES (%(id)s, %(equipment_id)s, %(occurred_at)s, %(fault_code)s, %(symptoms)s,
                %(root_cause)s, %(resolution)s, %(downtime_hrs)s, %(verified)s)
        ON CONFLICT (id) DO UPDATE SET
          symptoms = EXCLUDED.symptoms, root_cause = EXCLUDED.root_cause,
          resolution = EXCLUDED.resolution, verified = EXCLUDED.verified
    """
    with conn.cursor() as cur:
        for r in records:
            cur.execute(sql, {**r, "verified": bool(r.get("verified"))})
    print(f"  [data] breakdown_history: {len(records)} records")


def _load_sensors(conn) -> None:
    path = DATA / "synthetic" / "sensor_readings.csv"
    if not path.exists():
        print("  [skip] sensor_readings.csv not found"); return
    cols = ["equipment_id", "ts", "vibration_de", "vibration_nde",
            "bearing_temp", "motor_current", "rpm", "load_pct"]
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM sensor_readings")
        if (cur.fetchone() or [0])[0] > 0:
            print("  [data] sensor_readings already populated — skipping COPY")
            return
        with path.open(newline="", encoding="utf-8") as f, \
                cur.copy(f"COPY sensor_readings ({', '.join(cols)}) FROM STDIN") as cp:
            reader = csv.DictReader(f)
            for row in reader:
                # text-format COPY: pass typed values so psycopg adapts ts + numerics correctly
                cp.write_row([
                    row["equipment_id"], row["ts"],
                    float(row["vibration_de"]), float(row["vibration_nde"]),
                    float(row["bearing_temp"]), float(row["motor_current"]),
                    float(row["rpm"]), float(row["load_pct"]),
                ])
    print("  [data] sensor_readings: COPY complete (~52k rows)")


def main() -> int:
    print("ForgeSight · apply_migrations → Supabase\n")
    try:
        conn = connect()
    except RuntimeError as e:
        print(f"  ERROR: {e}")
        return 1
    with conn:
        # Local-dev convenience: a plain pgvector container lacks Supabase's auth schema.
        if not _auth_users_exists(conn):
            print("  [shim] auth.users absent → applying local_auth_shim.sql (local dev only)")
            _run_sql_file(conn, DB / "local_auth_shim.sql")
        _run_sql_file(conn, DB / "migrations.sql")
        _run_sql_file(conn, DB / "seed_data.sql")
        try:
            _run_sql_file(conn, DB / "seed_accounts.sql")
        except Exception as e:  # noqa: BLE001
            print(f"  [warn] seed_accounts.sql failed ({e}). On hosted Supabase, create the "
                  "two demo users via the Auth admin API instead; profiles still seeded.")
        _run_sql_file(conn, DATA / "corpus" / "corpus_ingest.sql", optional=True)
        _load_breakdowns(conn)
        _load_sensors(conn)
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM doc_chunks")
            n_chunks = (cur.fetchone() or [0])[0]
            cur.execute("SELECT count(*) FROM equipment")
            n_eq = (cur.fetchone() or [0])[0]
    print(f"\nDone. doc_chunks={n_chunks} · equipment={n_eq}.")
    print("Next: python scripts/diagnose_f3.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
