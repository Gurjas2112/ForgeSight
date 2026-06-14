"""
ForgeSight — spares tool (SQL). Spares are deliberately NOT embedded (§1.7): availability and
lead time are volatile structured data, served straight from the spares table.
Used by the Planner pipeline (Scenario B/C). Pass 1 includes the read path.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SparesRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    part_no: str
    equipment_id: str | None
    description: str | None
    stock_qty: int
    lead_time_days: int
    supplier: str | None


def check_spares(conn, equipment_id: str) -> list[SparesRecord]:
    """Stock + lead time for an equipment's spares (live structured data)."""
    sql = ("SELECT part_no, equipment_id, description, stock_qty, lead_time_days, supplier "
           "FROM spares WHERE equipment_id = %s ORDER BY part_no")
    with conn.cursor() as cur:
        cur.execute(sql, (equipment_id,))
        rows = cur.fetchall()
    return [SparesRecord(part_no=r[0], equipment_id=r[1], description=r[2],
                         stock_qty=r[3], lead_time_days=r[4], supplier=r[5]) for r in rows]
