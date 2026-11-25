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
CREATE TABLE IF NOT EXISTS api_calls (
    day TEXT PRIMARY KEY,   -- fecha local AAAA-MM-DD
    n   INTEGER NOT NULL
);
"""


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._conn() as c:
            c.executescript(SCHEMA)
            # Bases de datos anteriores a las luces: se añade la columna del brillo sin tocar lo guardado.
            if "level" not in {r[1] for r in c.execute("PRAGMA table_info(readings)")}:
                c.execute("ALTER TABLE readings ADD COLUMN level REAL")

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(str(self.path), timeout=10)
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
        return c

    # ---- Escritura ----------------------------------------------------
    def add(self, plug: str, ts: float, online: bool, on: Optional[bool],
            power: Optional[float], voltage: Optional[float], current: Optional[float],
            level: Optional[float] = None) -> None:
        with self._lock, self._conn() as c:
            c.execute(
                "INSERT INTO readings (ts, plug, online, on_, power, voltage, current, level) VALUES (?,?,?,?,?,?,?,?)",
                (int(ts), plug, int(online), None if on is None else int(on), power, voltage, current, level))

    def prune(self, retention_days: int) -> int:
        cutoff = int(time.time()) - retention_days * 86400
        with self._lock, self._conn() as c:
            # las llamadas a la API pesan casi nada: se conservan al menos 400 días
            keep = time.strftime("%Y-%m-%d", time.localtime(time.time() - max(retention_days, 400) * 86400))
            c.execute("DELETE FROM api_calls WHERE day < ?", (keep,))
            return c.execute("DELETE FROM readings WHERE ts < ?", (cutoff,)).rowcount

    def add_api_calls(self, n: int, ts: Optional[float] = None) -> None:
        """Suma `n` llamadas a la API de la nube al contador del día (hora local)."""
        if n <= 0:
            return
        day = time.strftime("%Y-%m-%d", time.localtime(time.time() if ts is None else ts))
        with self._lock, self._conn() as c:
            c.execute("INSERT INTO api_calls (day, n) VALUES (?, ?) "
                      "ON CONFLICT(day) DO UPDATE SET n = n + excluded.n", (day, int(n)))

    def api_calls_by_day(self, days: int = 31, now: Optional[float] = None) -> List[Dict]:
        """Llamadas por día de los últimos `days` días (incluido hoy), con ceros en los días sin datos."""
        now = time.time() if now is None else now
        first = time.localtime(now - (days - 1) * 86400)
        with self._lock, self._conn() as c:
            rows = dict(c.execute("SELECT day, n FROM api_calls WHERE day >= ?",
                                  (time.strftime("%Y-%m-%d", first),)).fetchall())
        out = []
        for i in range(days - 1, -1, -1):
            d = time.strftime("%Y-%m-%d", time.localtime(now - i * 86400))
            out.append({"day": d, "n": int(rows.get(d, 0))})
        return out

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
                "SELECT (ts / ?) * ? AS t, AVG(power), AVG(voltage), AVG(current), MAX(on_), MAX(online), AVG(level) "
                "FROM readings WHERE plug = ? AND ts BETWEEN ? AND ? GROUP BY t ORDER BY t",
                (bucket, bucket, plug, int(t0), int(t1))).fetchall()
        return [{"t": r[0], "p": r[1], "v": r[2], "i": r[3], "on": r[4], "online": r[5], "br": r[6]} for r in rows]

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
                "SELECT AVG(power), MAX(power), COUNT(*), SUM(online), MAX(voltage), MIN(voltage), "
                "MIN(power), AVG(voltage), AVG(current), MIN(current), MAX(current), AVG(on_), "
                "AVG(level), MIN(level), MAX(level) "
                "FROM readings WHERE plug = ? AND ts BETWEEN ? AND ?", (plug, int(t0), int(t1))).fetchone()
        n = row[2] or 0
        rnd = lambda v, d: None if v is None else round(v, d)
        return {
            "energy_kwh": round(self.energy_kwh(plug, t0, t1, max_gap), 4),
            "avg_w": rnd(row[0], 1),
            "max_w": row[1],
            "samples": n,
            "availability": None if not n else round((row[3] or 0) / n, 4),
            "v_max": row[4], "v_min": row[5],
            # Bloque genérico de TeleHome: una entrada por magnitud medida.
            "m": {
                "p": {"avg": rnd(row[0], 1), "min": row[6], "max": row[1]},
                "v": {"avg": rnd(row[7], 1), "min": row[5], "max": row[4]},
                "i": {"avg": rnd(row[8], 3), "min": row[9], "max": row[10]},
                "br": {"avg": rnd(row[12], 1), "min": row[13], "max": row[14]},
            },
            "on_ratio": rnd(row[11], 4),
        }

    def export_csv(self, plug: str, t0: float, t1: float, luz: bool = False) -> Iterator[str]:
        """CSV de lecturas. Las luces llevan el brillo en lugar de potencia, tensión y corriente."""
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["fecha_hora_utc", "epoch", "dispositivo", "en_linea", "encendido", "brillo_pct"] if luz else
                   ["fecha_hora_utc", "epoch", "enchufe", "en_linea", "encendido", "potencia_w", "tension_v", "corriente_a"])
        yield buf.getvalue()
        with self._conn() as c:
            cur = c.execute(
                "SELECT ts, online, on_, power, voltage, current, level FROM readings "
                "WHERE plug = ? AND ts BETWEEN ? AND ? ORDER BY ts", (plug, int(t0), int(t1)))
            vacio = lambda x: "" if x is None else x
            for ts, online, on, p, v, i, lv in cur:
                buf = io.StringIO()
                fila = [time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)), ts, plug, online, vacio(on)]
                csv.writer(buf).writerow(fila + ([vacio(lv)] if luz else [vacio(p), vacio(v), vacio(i)]))
                yield buf.getvalue()
