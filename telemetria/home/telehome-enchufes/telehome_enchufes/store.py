"""Almacén SQLite de lecturas (telemetría)."""

from __future__ import annotations

import csv
import io
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, Iterator, List, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
    ts      INTEGER NOT NULL,
    plug    TEXT    NOT NULL,
    online  INTEGER NOT NULL,
    on_     INTEGER,
    power   REAL,
    voltage REAL,
    current REAL
);
CREATE INDEX IF NOT EXISTS idx_readings_plug_ts ON readings (plug, ts);
"""


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._conn() as c:
            c.executescript(SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(str(self.path), timeout=10)
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
        return c

    # ---- Escritura ----------------------------------------------------
    def add(self, plug: str, ts: float, online: bool, on: Optional[bool],
            power: Optional[float], voltage: Optional[float], current: Optional[float]) -> None:
        with self._lock, self._conn() as c:
            c.execute(
                "INSERT INTO readings (ts, plug, online, on_, power, voltage, current) VALUES (?,?,?,?,?,?,?)",
                (int(ts), plug, int(online), None if on is None else int(on), power, voltage, current))

    def prune(self, retention_days: int) -> int:
        cutoff = int(time.time()) - retention_days * 86400
        with self._lock, self._conn() as c:
            return c.execute("DELETE FROM readings WHERE ts < ?", (cutoff,)).rowcount

    def delete_plug(self, plug: str) -> None:
        with self._lock, self._conn() as c:
            c.execute("DELETE FROM readings WHERE plug = ?", (plug,))

    # ---- Lectura ------------------------------------------------------
    def history(self, plug: str, t0: float, t1: float, max_points: int = 400) -> List[Dict]:
        """Serie agregada en cubos de tiempo (media) con como máximo `max_points` puntos."""
        span = max(int(t1 - t0), 1)
        bucket = max(1, -(-span // max_points))
        with self._conn() as c:
            rows = c.execute(
                "SELECT (ts / ?) * ? AS t, AVG(power), AVG(voltage), AVG(current), MAX(on_), MAX(online) "
                "FROM readings WHERE plug = ? AND ts BETWEEN ? AND ? GROUP BY t ORDER BY t",
                (bucket, bucket, plug, int(t0), int(t1))).fetchall()
        return [{"t": r[0], "p": r[1], "v": r[2], "i": r[3], "on": r[4], "online": r[5]} for r in rows]

    def energy_kwh(self, plug: str, t0: float, t1: float, max_gap: float = 120.0) -> float:
        """Energía (kWh) integrando la potencia (trapecios); ignora huecos largos."""
        with self._conn() as c:
            rows = c.execute(
                "SELECT ts, power FROM readings WHERE plug = ? AND ts BETWEEN ? AND ? "
                "AND power IS NOT NULL ORDER BY ts", (plug, int(t0), int(t1))).fetchall()
        total = 0.0
        for (ta, pa), (tb, pb) in zip(rows, rows[1:]):
            dt = tb - ta
            if 0 < dt <= max_gap:
                total += (pa + pb) / 2.0 * dt
        return total / 3_600_000.0

    def summary(self, plug: str, t0: float, t1: float, max_gap: float = 120.0) -> Dict:
        with self._conn() as c:
            row = c.execute(
                "SELECT AVG(power), MAX(power), COUNT(*), SUM(online), MAX(voltage), MIN(voltage) "
                "FROM readings WHERE plug = ? AND ts BETWEEN ? AND ?", (plug, int(t0), int(t1))).fetchone()
        n = row[2] or 0
        return {
            "energy_kwh": round(self.energy_kwh(plug, t0, t1, max_gap), 4),
            "avg_w": None if row[0] is None else round(row[0], 1),
            "max_w": row[1],
            "samples": n,
            "availability": None if not n else round((row[3] or 0) / n, 4),
            "v_max": row[4], "v_min": row[5],
        }

    def export_csv(self, plug: str, t0: float, t1: float) -> Iterator[str]:
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["fecha_hora_utc", "epoch", "enchufe", "en_linea", "encendido", "potencia_w", "tension_v", "corriente_a"])
        yield buf.getvalue()
        with self._conn() as c:
            cur = c.execute(
                "SELECT ts, online, on_, power, voltage, current FROM readings "
                "WHERE plug = ? AND ts BETWEEN ? AND ? ORDER BY ts", (plug, int(t0), int(t1)))
            for ts, online, on, p, v, i in cur:
                buf = io.StringIO()
                csv.writer(buf).writerow([
                    time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)), ts, plug, online,
                    "" if on is None else on, "" if p is None else p, "" if v is None else v, "" if i is None else i])
                yield buf.getvalue()
