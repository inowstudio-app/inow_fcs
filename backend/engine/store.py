"""Lightweight project/client store (SQLite). Saves feasibility/compliance studies."""
from __future__ import annotations
import json, os, sqlite3, datetime

# DB_PATH env lets the host point this at a persistent disk (e.g. Render disk at /var/data)
DB_PATH = os.environ.get("DB_PATH") or os.path.join(os.path.dirname(__file__), "..", "..", "data", "projects.db")


def _conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client TEXT, title TEXT, survey_no TEXT, village TEXT,
        kind TEXT, inputs_json TEXT, result_json TEXT, created_at TEXT)""")
    return c


def save_project(client, title, survey_no, village, kind, inputs, result) -> dict:
    now = datetime.datetime.now().isoformat(timespec="seconds")
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO projects (client,title,survey_no,village,kind,inputs_json,result_json,created_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (client, title, survey_no, village, kind, json.dumps(inputs), json.dumps(result), now))
        return {"id": cur.lastrowid, "created_at": now}


def list_projects() -> list[dict]:
    with _conn() as c:
        rows = c.execute("SELECT id,client,title,survey_no,village,kind,created_at"
                         " FROM projects ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]


def get_project(pid: int) -> dict | None:
    with _conn() as c:
        r = c.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
        if not r:
            return None
        d = dict(r)
        d["inputs"] = json.loads(d.pop("inputs_json"))
        d["result"] = json.loads(d.pop("result_json"))
        return d


def delete_project(pid: int) -> bool:
    with _conn() as c:
        cur = c.execute("DELETE FROM projects WHERE id=?", (pid,))
        return cur.rowcount > 0
