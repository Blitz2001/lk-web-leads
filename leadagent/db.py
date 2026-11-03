"""SQLite store so re-runs don't re-pitch the same business."""
from __future__ import annotations

import datetime as dt
import json
import sqlite3

STATUSES = ("new", "reviewed", "sent", "followed_up", "replied", "won", "lost", "skip")

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
  id TEXT PRIMARY KEY,
  lead TEXT NOT NULL,
  audit TEXT,
  pitch TEXT,
  status TEXT NOT NULL DEFAULT 'new',
  note TEXT DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  sent_at TEXT
);
"""


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str):
        self.con = sqlite3.connect(path)
        self.con.row_factory = sqlite3.Row
        self.con.executescript(SCHEMA)

    def upsert_lead(self, lead: dict) -> bool:
        """Insert or refresh contact data. Returns True if the lead is new."""
        row = self.con.execute("SELECT lead FROM leads WHERE id=?", (lead["id"],)).fetchone()
        if row:
            old = json.loads(row["lead"])
            merged = {**old, **{k: v for k, v in lead.items() if v not in (None, "")}}
            self.con.execute("UPDATE leads SET lead=?, updated_at=? WHERE id=?", (json.dumps(merged), _now(), lead["id"]))
            self.con.commit()
            return False
        self.con.execute(
            "INSERT INTO leads (id, lead, created_at, updated_at) VALUES (?,?,?,?)",
            (lead["id"], json.dumps(lead), _now(), _now()),
        )
        self.con.commit()
        return True

    def set_audit(self, lid: str, audit: dict) -> None:
        self.con.execute("UPDATE leads SET audit=?, updated_at=? WHERE id=?", (json.dumps(audit), _now(), lid))
        self.con.commit()

    def set_pitch(self, lid: str, pitch: dict) -> None:
        self.con.execute("UPDATE leads SET pitch=?, updated_at=? WHERE id=?", (json.dumps(pitch), _now(), lid))
        self.con.commit()

    def set_status(self, lid: str, status: str, note: str | None = None) -> bool:
        if status not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}")
        sent_at = _now() if status in ("sent", "followed_up") else None
        cur = self.con.execute(
            "UPDATE leads SET status=?, note=COALESCE(?, note), sent_at=COALESCE(?, sent_at), updated_at=? WHERE id LIKE ?",
            (status, note, sent_at, _now(), lid + "%"),
        )
        self.con.commit()
        return cur.rowcount > 0

    def all(self) -> list[dict]:
        rows = self.con.execute("SELECT * FROM leads ORDER BY created_at").fetchall()
        out = []
        for r in rows:
            out.append({
                "id": r["id"],
                "lead": json.loads(r["lead"]),
                "audit": json.loads(r["audit"]) if r["audit"] else None,
                "pitch": json.loads(r["pitch"]) if r["pitch"] else None,
                "status": r["status"],
                "note": r["note"] or "",
                "sent_at": r["sent_at"],
            })
        return out
