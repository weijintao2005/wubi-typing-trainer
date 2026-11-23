# -*- coding: utf-8 -*-
"""五笔练习 · 本地服务

除 docx 解析使用 python-docx 外，只依赖 Python 标准库；
双击 run.bat 或执行 `python app.py` 即可。
数据保存在 data/progress.db（SQLite），不上传任何地方。
"""
import argparse
import base64
import hashlib
import json
import mimetypes
import os
import re
import shutil
import sqlite3
import sys
import threading
import uuid
import webbrowser
from contextlib import closing
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from article_parser import ParseError, parse_article

BASE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(BASE, "web")
DATA = os.path.join(BASE, "data")
DB_PATH = os.path.join(DATA, "progress.db")
ARTICLE_MEDIA = os.path.join(DATA, "article_media")

ARTICLE_MAX_BYTES = 10 * 1024 * 1024
ARTICLE_MAX_BODY = 15 * 1024 * 1024
ARTICLE_MAX_CHARS = 20000

CHAR_POOLS = ["jm1", "jm2", "jm3", "jm4", "common", "common2",
              "gb2312", "keyname", "chengzi", "hard"]
WORD_POOLS = ["w2", "w3", "w4"]
ALL_POOLS = CHAR_POOLS + WORD_POOLS

POOLS = {}
POOL_SETS = {}

MASTER_STREAK = 3

MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
    ".ttf": "font/ttf",
    ".otf": "font/otf",
    ".woff2": "font/woff2",
}

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff"}


def load_pools():
    global POOLS, POOL_SETS
    if POOLS:
        return POOLS
    path = os.path.join(DATA, "pools.json")
    with open(path, encoding="utf-8") as f:
        POOLS = json.load(f)
    POOL_SETS = {k: set(v) for k, v in POOLS.items()}
    return POOLS


def pool_kind(pool):
    if pool in WORD_POOLS:
        return "word"
    if pool in CHAR_POOLS:
        return "char"
    return None


def connect():
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 3000")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    os.makedirs(DATA, exist_ok=True)
    load_pools()
    with closing(connect()) as conn, conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                mode TEXT NOT NULL,
                pool TEXT NOT NULL,
                total INTEGER NOT NULL,
                correct INTEGER NOT NULL,
                wrong INTEGER NOT NULL,
                duration REAL NOT NULL,
                speed REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS err_chars (
                char TEXT PRIMARY KEY,
                count INTEGER NOT NULL DEFAULT 0,
                last_ts TEXT,
                right_streak INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS item_state (
                pool_id       TEXT NOT NULL,
                item          TEXT NOT NULL,
                kind          TEXT NOT NULL,
                status        TEXT NOT NULL,
                right_streak  INTEGER NOT NULL DEFAULT 0,
                error_count   INTEGER NOT NULL DEFAULT 0,
                seen_count    INTEGER NOT NULL DEFAULT 0,
                perfect_count INTEGER NOT NULL DEFAULT 0,
                first_result  TEXT,
                first_ts      TEXT NOT NULL,
                last_ts       TEXT NOT NULL,
                mastered_ts   TEXT,
                PRIMARY KEY (pool_id, item)
            );
            CREATE INDEX IF NOT EXISTS idx_item_state_status
                ON item_state (pool_id, status);
            CREATE TABLE IF NOT EXISTS articles (
                id          TEXT PRIMARY KEY,
                title       TEXT NOT NULL,
                filename    TEXT NOT NULL,
                kind        TEXT NOT NULL,
                hash        TEXT,
                doc_json    TEXT NOT NULL,
                char_count  INTEGER NOT NULL,
                created_ts  TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_articles_hash ON articles (hash);
            CREATE TABLE IF NOT EXISTS article_progress (
                article_id   TEXT PRIMARY KEY REFERENCES articles(id) ON DELETE CASCADE,
                cursor       INTEGER NOT NULL DEFAULT 0,
                correct      INTEGER NOT NULL DEFAULT 0,
                wrong        INTEGER NOT NULL DEFAULT 0,
                elapsed      REAL NOT NULL DEFAULT 0,
                updated_ts   TEXT NOT NULL,
                completed_ts TEXT
            );
            CREATE TABLE IF NOT EXISTS article_chars (
                article_id TEXT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
                pos        INTEGER NOT NULL,
                status     TEXT NOT NULL,
                errors     INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (article_id, pos)
            );
            """
        )
        cols = {r[1] for r in conn.execute("PRAGMA table_info(err_chars)")}
        if "right_streak" not in cols:
            conn.execute(
                "ALTER TABLE err_chars ADD COLUMN right_streak INTEGER NOT NULL DEFAULT 0"
            )
        migrate_v2(conn)


def migrate_v2(conn):
    """把旧 err_chars（全局单字）迁移成各字库的 error 状态。"""
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version >= 2:
        return
    rows = conn.execute(
        "SELECT char, count, last_ts, right_streak FROM err_chars"
    ).fetchall()
    migrated = 0
    for row in rows:
        ch = row["char"]
        last_ts = row["last_ts"] or local_now()
        for pid in CHAR_POOLS:
            if ch not in POOL_SETS.get(pid, ()):
                continue
            cur = conn.execute(
                "INSERT OR IGNORE INTO item_state"
                " (pool_id, item, kind, status, right_streak, error_count,"
                "  seen_count, perfect_count, first_result, first_ts, last_ts, mastered_ts)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL)",
                (
                    pid, ch, "char", "error",
                    min(2, max(0, int(row["right_streak"] or 0))),
                    int(row["count"] or 0), int(row["count"] or 0), 0,
                    "error", last_ts, last_ts,
                ),
            )
            migrated += cur.rowcount
    conn.execute("PRAGMA user_version = 2")
    if migrated:
        print("学习状态迁移：%d 条旧错字 → %d 条科目状态" % (len(rows), migrated))


def local_now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def pool_counts(conn, pool):
    total = len(POOLS.get(pool, []))
    rows = conn.execute(
        "SELECT status, COUNT(*) n FROM item_state WHERE pool_id = ? GROUP BY status",
        (pool,),
    ).fetchall()
    low = error = mastered = 0
    for r in rows:
        if r["status"] == "low":
            low = r["n"]
        elif r["status"] == "error":
            error = r["n"]
        elif r["status"] == "mastered":
            mastered = r["n"]
    new = max(0, total - low - error - mastered)
    return {"total": total, "new": new, "low": low, "error": error, "mastered": mastered}


def learning_payload(conn, pool):
    rows = conn.execute(
        "SELECT item, status, right_streak, error_count FROM item_state WHERE pool_id = ?",
        (pool,),
    ).fetchall()
    items = {}
    for r in rows:
        items[r["item"]] = {
            "status": r["status"],
            "streak": r["right_streak"],
            "errorCount": r["error_count"],
        }
    return {"pool": pool, "counts": pool_counts(conn, pool), "items": items}


def errors_payload(conn, limit=None):
    rows = conn.execute(
        "SELECT item, kind, pool_id, error_count, right_streak"
        " FROM item_state WHERE status = 'error'"
    ).fetchall()
    groups = {}
    for r in rows:
        key = (r["item"], r["kind"])
        g = groups.get(key)
        if g is None:
            g = groups[key] = {
                "item": r["item"], "kind": r["kind"],
                "errorCount": 0, "sources": [],
            }
        g["errorCount"] += int(r["error_count"] or 0)
        g["sources"].append({
            "pool": r["pool_id"],
            "streak": int(r["right_streak"] or 0),
            "errorCount": int(r["error_count"] or 0),
        })
    out = list(groups.values())
    for g in out:
        g["sources"].sort(key=lambda x: ALL_POOLS.index(x["pool"])
                          if x["pool"] in ALL_POOLS else 99)
    out.sort(key=lambda g: (-g["errorCount"], g["item"]))
    if limit is not None:
        out = out[:limit]
    return out


def distinct_counts(conn):
    result = {}
    for status in ("low", "error", "mastered"):
        n = conn.execute(
            "SELECT COUNT(*) FROM (SELECT 1 FROM item_state"
            " WHERE status = ? GROUP BY item, kind)",
            (status,),
        ).fetchone()[0]
        result[status] = n
    return result


def article_row(conn, article_id):
    return conn.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()


def article_progress_values(conn, article_id):
    row = conn.execute(
        "SELECT * FROM article_progress WHERE article_id = ?", (article_id,)
    ).fetchone()
    if row is None:
        return {"cursor": 0, "correct": 0, "wrong": 0, "elapsed": 0,
                "updated": None, "completed": None}
    return {
        "cursor": int(row["cursor"] or 0),
        "correct": int(row["correct"] or 0),
        "wrong": int(row["wrong"] or 0),
        "elapsed": round(float(row["elapsed"] or 0), 1),
        "updated": row["updated_ts"],
        "completed": row["completed_ts"],
    }


def article_list(conn):
    rows = conn.execute(
        "SELECT a.id, a.title, a.filename, a.kind, a.char_count, a.created_ts,"
        " p.cursor, p.correct, p.wrong, p.elapsed, p.updated_ts, p.completed_ts"
        " FROM articles a LEFT JOIN article_progress p ON p.article_id = a.id"
        " ORDER BY a.created_ts DESC, a.rowid DESC"
    ).fetchall()
    out = []
    for r in rows:
        total = int(r["char_count"] or 0)
        cursor = int(r["cursor"] or 0)
        out.append({
            "id": r["id"], "title": r["title"], "filename": r["filename"],
            "kind": r["kind"], "charCount": total, "created": r["created_ts"],
            "cursor": cursor,
            "correct": int(r["correct"] or 0),
            "wrong": int(r["wrong"] or 0),
            "elapsed": round(float(r["elapsed"] or 0), 1),
            "percent": round(cursor / total * 100, 1) if total else 0,
            "updated": r["updated_ts"],
            "completed": r["completed_ts"],
        })
    return out


def article_detail(conn, article_id):
    row = article_row(conn, article_id)
    if row is None:
        return None
    try:
        doc = json.loads(row["doc_json"])
    except (ValueError, TypeError):
        raise ValueError("文章数据损坏")
    chars = [
        {"pos": int(r["pos"]), "status": r["status"], "errors": int(r["errors"] or 0)}
        for r in conn.execute(
            "SELECT pos, status, errors FROM article_chars"
            " WHERE article_id = ? ORDER BY pos", (article_id,)
        )
    ]
    return {
        "id": row["id"], "title": row["title"], "filename": row["filename"],
        "kind": row["kind"], "charCount": int(row["char_count"] or 0),
        "created": row["created_ts"], "doc": doc,
        "progress": article_progress_values(conn, article_id),
        "chars": chars,
    }


def save_article_progress(conn, article_id, payload):
    row = article_row(conn, article_id)
    if row is None:
        raise KeyError("article not found")
    total = int(row["char_count"] or 0)
    try:
        cursor = int(payload.get("cursor") or 0)
        correct = int(payload.get("correct") or 0)
        wrong = int(payload.get("wrong") or 0)
        elapsed = float(payload.get("elapsed") or 0)
    except (TypeError, ValueError):
        raise ValueError("进度参数不正确")
    if cursor < 0 or cursor > total:
        raise ValueError("光标位置超出文章范围")
    if correct < 0 or wrong < 0 or correct + wrong > total:
        raise ValueError("进度计数不正确")
    elapsed = max(0.0, min(86400.0 * 7, elapsed))
    chars = payload.get("chars") or []
    if not isinstance(chars, list) or len(chars) > 2000:
        raise ValueError("进度字符过多")
    clean = []
    for c in chars:
        if not isinstance(c, dict):
            raise ValueError("进度字符格式不正确")
        try:
            pos = int(c.get("pos"))
            errors = int(c.get("errors") or 0)
        except (TypeError, ValueError):
            raise ValueError("进度字符位置不正确")
        status = c.get("status")
        if status not in ("correct", "error"):
            raise ValueError("进度字符状态不正确")
        if pos < 0 or pos >= total or errors < 0 or errors > 1000:
            raise ValueError("进度字符超出范围")
        clean.append((article_id, pos, status, errors))

    now = local_now()
    conn.execute(
        "INSERT INTO article_progress"
        " (article_id, cursor, correct, wrong, elapsed, updated_ts, completed_ts)"
        " VALUES (?,?,?,?,?,?,NULL)"
        " ON CONFLICT(article_id) DO UPDATE SET"
        " cursor=excluded.cursor, correct=excluded.correct, wrong=excluded.wrong,"
        " elapsed=excluded.elapsed, updated_ts=excluded.updated_ts",
        (article_id, cursor, correct, wrong, elapsed, now),
    )
    if clean:
        conn.executemany(
            "INSERT INTO article_chars (article_id, pos, status, errors)"
            " VALUES (?,?,?,?) ON CONFLICT(article_id, pos) DO UPDATE SET"
            " status=excluded.status, errors=excluded.errors",
            clean,
        )
    return {"ok": True, "cursor": cursor}


def finish_article_session(conn, article_id, payload):
    row = article_row(conn, article_id)
    if row is None:
        raise KeyError("article not found")
    total = int(row["char_count"] or 0)
    try:
        used = max(0, min(total, int(payload.get("total") or total)))
        correct = max(0, min(100000, int(payload.get("correct") or 0)))
        wrong = max(0, min(100000, int(payload.get("wrong") or 0)))
        duration = max(1.0, min(86400.0, float(payload.get("duration") or 1)))
    except (TypeError, ValueError):
        raise ValueError("成绩参数不正确")
    speed = used / (duration / 60.0)
    now = local_now()
    conn.execute(
        "INSERT INTO sessions (ts, mode, pool, total, correct, wrong, duration, speed)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (now, "article", "article", used, correct, wrong, duration, round(speed, 2)),
    )
    conn.execute(
        "INSERT INTO article_progress"
        " (article_id, cursor, correct, wrong, elapsed, updated_ts, completed_ts)"
        " VALUES (?,?,?,?,?,?,?)"
        " ON CONFLICT(article_id) DO UPDATE SET"
        " cursor=excluded.cursor, correct=excluded.correct, wrong=excluded.wrong,"
        " elapsed=excluded.elapsed, updated_ts=excluded.updated_ts,"
        " completed_ts=excluded.completed_ts",
        (article_id, total, correct, wrong, duration, now, now),
    )
    return {"ok": True, "speed": round(speed, 2)}


def delete_article(conn, article_id):
    row = article_row(conn, article_id)
    if row is None:
        return False
    conn.execute("DELETE FROM article_chars WHERE article_id = ?", (article_id,))
    conn.execute("DELETE FROM article_progress WHERE article_id = ?", (article_id,))
    conn.execute("DELETE FROM articles WHERE id = ?", (article_id,))
    shutil.rmtree(os.path.join(ARTICLE_MEDIA, article_id), ignore_errors=True)
    return True


def apply_result(conn, pool, item, kind, result):
    """在指定科目上应用一次 perfect/error，返回更新后的状态。"""
    row = conn.execute(
        "SELECT * FROM item_state WHERE pool_id = ? AND item = ?", (pool, item)
    ).fetchone()
    now = local_now()
    if row is None:
        if result == "perfect":
            status, streak = "low", 1
            error_count = 0
        else:
            status, streak = "error", 0
            error_count = 1
        conn.execute(
            "INSERT INTO item_state"
            " (pool_id, item, kind, status, right_streak, error_count,"
            "  seen_count, perfect_count, first_result, first_ts, last_ts, mastered_ts)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL)",
            (
                pool, item, kind, status, streak, error_count,
                1, 1 if result == "perfect" else 0,
                status, now, now,
            ),
        )
        return {"pool": pool, "status": status, "streak": streak,
                "mastered": False, "errorCount": error_count}

    if row["status"] == "mastered":
        return {"pool": pool, "status": "mastered",
                "streak": int(row["right_streak"] or 0),
                "mastered": True, "errorCount": int(row["error_count"] or 0)}

    if result == "perfect":
        streak = int(row["right_streak"] or 0) + 1
        status = "mastered" if streak >= MASTER_STREAK else row["status"]
        mastered_ts = now if status == "mastered" else None
        conn.execute(
            "UPDATE item_state SET status = ?, right_streak = ?, seen_count = seen_count + 1,"
            " perfect_count = perfect_count + 1, last_ts = ?,"
            " mastered_ts = COALESCE(?, mastered_ts) WHERE pool_id = ? AND item = ?",
            (status, streak, now, mastered_ts, pool, item),
        )
        return {"pool": pool, "status": status, "streak": streak,
                "mastered": status == "mastered",
                "errorCount": int(row["error_count"] or 0)}

    error_count = int(row["error_count"] or 0) + 1
    conn.execute(
        "UPDATE item_state SET status = 'error', right_streak = 0,"
        " error_count = ?, seen_count = seen_count + 1, last_ts = ?"
        " WHERE pool_id = ? AND item = ?",
        (error_count, now, pool, item),
    )
    return {"pool": pool, "status": "error", "streak": 0,
            "mastered": False, "errorCount": error_count}


def stats_payload():
    with closing(connect()) as conn, conn:
        row = conn.execute(
            "SELECT COUNT(*) n, COALESCE(SUM(total),0) t, COALESCE(SUM(correct),0) c,"
            " COALESCE(SUM(wrong),0) w, COALESCE(MAX(speed),0) best FROM sessions"
        ).fetchone()
        today = datetime.now().strftime("%Y-%m-%d")
        today_chars = conn.execute(
            "SELECT COALESCE(SUM(total),0) FROM sessions WHERE substr(ts,1,10)=?", (today,)
        ).fetchone()[0]
        dates = [r[0] for r in conn.execute(
            "SELECT DISTINCT substr(ts,1,10) d FROM sessions ORDER BY d DESC LIMIT 400"
        )]
        recent = [dict(r) for r in conn.execute(
            "SELECT ts, mode, pool, total, correct, wrong, duration, speed"
            " FROM sessions ORDER BY id DESC LIMIT 12"
        )]
        errors = errors_payload(conn)
        learning = {
            "distinct": distinct_counts(conn),
            "pools": [],
        }
        for pid in ALL_POOLS:
            c = pool_counts(conn, pid)
            if c["total"]:
                learning["pools"].append({"id": pid, **c})

    accuracy = (row["c"] / (row["c"] + row["w"]) * 100) if (row["c"] + row["w"]) else 0.0
    streak = 0
    if dates:
        d = datetime.strptime(dates[0], "%Y-%m-%d").date()
        today_d = datetime.now().date()
        if d in (today_d, today_d - timedelta(days=1)):
            streak = 1
            cur = d
            for s in dates[1:]:
                nd = datetime.strptime(s, "%Y-%m-%d").date()
                if nd == cur - timedelta(days=1):
                    streak += 1
                    cur = nd
                else:
                    break

    return {
        "sessions": row["n"],
        "totalChars": row["t"],
        "totalCorrect": row["c"],
        "totalWrong": row["w"],
        "accuracy": round(accuracy, 2),
        "bestSpeed": round(row["best"], 1),
        "todayChars": today_chars,
        "streak": streak,
        "recent": recent,
        "errors": errors,
        "learning": learning,
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "WubiTrainer/2.0"

    # -------------------------------------------------- 工具
    def send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path):
        if not os.path.isfile(path):
            self.send_json({"error": "not found"}, 404)
            return
        ext = os.path.splitext(path)[1].lower()
        ctype = MIME.get(ext) or mimetypes.guess_type(path)[0] or "application/octet-stream"
        try:
            with open(path, "rb") as f:
                body = f.read()
        except OSError:
            self.send_json({"error": "read failed"}, 500)
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def resolve(self, url_path):
        if url_path in ("/", "/index.html"):
            return os.path.join(WEB, "index.html")
        if url_path.startswith("/static/"):
            return self.safe_join(WEB, url_path[len("/static/"):])
        if url_path.startswith("/data/"):
            return self.safe_join(DATA, url_path[len("/data/"):])
        return None

    @staticmethod
    def safe_join(root, rel):
        root_abs = os.path.abspath(root)
        target = os.path.abspath(os.path.join(root_abs, rel))
        if os.path.commonpath([root_abs, target]) != root_abs:
            return None
        return target

    def log_message(self, fmt, *args):
        if os.environ.get("WUBI_VERBOSE"):
            sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    # -------------------------------------------------- GET
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/stats":
            self.send_json(stats_payload())
            return
        if path == "/api/errors":
            with closing(connect()) as conn, conn:
                rows = errors_payload(conn)
            self.send_json({"errors": rows})
            return
        if path == "/api/learning":
            query = urlparse(self.path).query
            pool = ""
            for part in query.split("&"):
                if part.startswith("pool="):
                    pool = part[len("pool="):]
            if pool not in ALL_POOLS:
                self.send_json({"error": "bad pool"}, 400)
                return
            with closing(connect()) as conn, conn:
                data = learning_payload(conn, pool)
            self.send_json(data)
            return
        if path == "/api/health":
            self.send_json({"ok": True})
            return
        if path == "/api/articles":
            with closing(connect()) as conn, conn:
                self.send_json({"articles": article_list(conn)})
            return
        m = re.fullmatch(r"/api/articles/([0-9a-f]{32})", path)
        if m:
            with closing(connect()) as conn, conn:
                try:
                    detail = article_detail(conn, m.group(1))
                except ValueError as e:
                    self.send_json({"error": str(e)}, 500)
                    return
            if detail is None:
                self.send_json({"error": "not found"}, 404)
            else:
                self.send_json(detail)
            return
        if path.startswith("/media/articles/"):
            rest = path[len("/media/articles/"):]
            parts = rest.split("/")
            if len(parts) != 2:
                self.send_json({"error": "not found"}, 404)
                return
            article_id, name = parts
            if not re.fullmatch(r"[0-9a-f]{32}", article_id) or os.path.basename(name) != name:
                self.send_json({"error": "not found"}, 404)
                return
            if os.path.splitext(name)[1].lower() not in IMAGE_EXT:
                self.send_json({"error": "not found"}, 404)
                return
            target = self.safe_join(os.path.join(ARTICLE_MEDIA, article_id), name)
            if not target:
                self.send_json({"error": "not found"}, 404)
                return
            self.send_file(target)
            return

        target = self.resolve(path)
        if target is None:
            self.send_json({"error": "not found"}, 404)
            return
        self.send_file(target)

    # -------------------------------------------------- POST
    def read_payload(self, max_bytes=200_000):
        self._payload_error = None
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            self._payload_error = (400, "bad request")
            return None
        if length <= 0:
            self._payload_error = (400, "bad request")
            return None
        if length > max_bytes:
            self._payload_error = (413, "请求或文件过大")
            return None
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._payload_error = (400, "bad request")
            return None

    def payload_or_error(self, max_bytes=200_000):
        payload = self.read_payload(max_bytes)
        if payload is None:
            status, msg = self._payload_error or (400, "bad request")
            self.send_json({"error": msg}, status)
        return payload

    def handle_article_import(self):
        payload = self.payload_or_error(ARTICLE_MAX_BODY)
        if payload is None:
            return
        filename = os.path.basename(str(payload.get("filename") or ""))[:200]
        lower = filename.lower()
        if not (lower.endswith(".txt") or lower.endswith(".docx")):
            self.send_json({"error": "只支持 .txt 或 .docx 文件"}, 400)
            return
        raw = payload.get("data")
        if not isinstance(raw, str) or not raw:
            self.send_json({"error": "文件内容为空"}, 400)
            return
        if raw.startswith("data:"):
            raw = raw.split(",", 1)[-1]
        try:
            data = base64.b64decode(raw, validate=True)
        except Exception:
            self.send_json({"error": "文件编码不正确"}, 400)
            return
        if not data:
            self.send_json({"error": "文件内容为空"}, 400)
            return
        if len(data) > ARTICLE_MAX_BYTES:
            self.send_json({"error": "文件过大（最大 10MB）"}, 413)
            return
        digest = hashlib.sha256(data).hexdigest()
        force = bool(payload.get("force"))

        with closing(connect()) as conn, conn:
            duplicate = conn.execute(
                "SELECT id FROM articles WHERE hash = ? ORDER BY created_ts DESC LIMIT 1",
                (digest,),
            ).fetchone()
            if duplicate is not None and not force:
                detail = article_detail(conn, duplicate["id"])
                self.send_json({"ok": True, "duplicate": True, "article": detail})
                return

            article_id = uuid.uuid4().hex
            try:
                parsed = parse_article(data, filename, article_id, ARTICLE_MEDIA)
            except ParseError as e:
                shutil.rmtree(os.path.join(ARTICLE_MEDIA, article_id), ignore_errors=True)
                self.send_json({"error": str(e)}, 400)
                return
            except Exception:
                shutil.rmtree(os.path.join(ARTICLE_MEDIA, article_id), ignore_errors=True)
                self.send_json({"error": "文章解析失败，请确认文件未损坏"}, 500)
                return

            doc = {
                "version": 1,
                "title": parsed["title"],
                "kind": parsed["kind"],
                "encoding": parsed.get("encoding") or "",
                "blocks": parsed["blocks"],
            }
            now = local_now()
            try:
                conn.execute(
                    "INSERT INTO articles"
                    " (id, title, filename, kind, hash, doc_json, char_count, created_ts)"
                    " VALUES (?,?,?,?,?,?,?,?)",
                    (article_id, parsed["title"], filename, parsed["kind"], digest,
                     json.dumps(doc, ensure_ascii=False), parsed["char_count"], now),
                )
                conn.execute(
                    "INSERT INTO article_progress"
                    " (article_id, cursor, correct, wrong, elapsed, updated_ts, completed_ts)"
                    " VALUES (?,0,0,0,0,?,NULL)",
                    (article_id, now),
                )
                detail = article_detail(conn, article_id)
            except Exception:
                shutil.rmtree(os.path.join(ARTICLE_MEDIA, article_id), ignore_errors=True)
                raise

        self.send_json({"ok": True, "duplicate": False, "article": detail})

    def handle_article_progress(self, article_id):
        payload = self.payload_or_error(2_000_000)
        if payload is None:
            return
        with closing(connect()) as conn, conn:
            try:
                save_article_progress(conn, article_id, payload)
            except KeyError:
                self.send_json({"error": "文章不存在"}, 404)
                return
            except ValueError as e:
                self.send_json({"error": str(e)}, 400)
                return
        self.send_json({"ok": True})

    def handle_article_session(self, article_id):
        payload = self.payload_or_error(200_000)
        if payload is None:
            return
        with closing(connect()) as conn, conn:
            try:
                finish_article_session(conn, article_id, payload)
            except KeyError:
                self.send_json({"error": "文章不存在"}, 404)
                return
            except ValueError as e:
                self.send_json({"error": str(e)}, 400)
                return
        self.send_json({"ok": True, "stats": stats_payload()})

    def handle_article_reset(self, article_id):
        with closing(connect()) as conn, conn:
            if article_row(conn, article_id) is None:
                self.send_json({"error": "文章不存在"}, 404)
                return
            conn.execute("DELETE FROM article_chars WHERE article_id = ?", (article_id,))
            conn.execute("DELETE FROM article_progress WHERE article_id = ?", (article_id,))
        self.send_json({"ok": True})

    def handle_article_delete(self, article_id):
        with closing(connect()) as conn, conn:
            if not delete_article(conn, article_id):
                self.send_json({"error": "文章不存在"}, 404)
                return
        self.send_json({"ok": True})

    def handle_attempt(self, payload):
        pool = str(payload.get("pool") or "")
        item = str(payload.get("item") or "").strip()
        kind = payload.get("kind")
        result = payload.get("result")
        if result not in ("perfect", "error"):
            self.send_json({"error": "bad result"}, 400)
            return
        if not item or len(item) > 8 or kind not in ("char", "word"):
            self.send_json({"error": "bad item"}, 400)
            return

        if pool == "errors":
            with closing(connect()) as conn, conn:
                rows = conn.execute(
                    "SELECT pool_id FROM item_state"
                    " WHERE item = ? AND kind = ? AND status = 'error'",
                    (item, kind),
                ).fetchall()
                sources = []
                for r in rows:
                    out = apply_result(conn, r["pool_id"], item, kind, result)
                    sources.append({"pool": r["pool_id"], "status": out["status"],
                                    "streak": out["streak"],
                                    "errorCount": out["errorCount"]})
                still = conn.execute(
                    "SELECT COUNT(*) FROM item_state"
                    " WHERE item = ? AND kind = ? AND status = 'error'",
                    (item, kind),
                ).fetchone()[0]
                remaining = conn.execute(
                    "SELECT COUNT(*) FROM (SELECT 1 FROM item_state"
                    " WHERE status = 'error' GROUP BY item, kind)"
                ).fetchone()[0]
            self.send_json({
                "ok": True, "pool": "errors", "item": item, "kind": kind,
                "sources": sources, "stillError": still > 0,
                "remaining": remaining,
            })
            return

        if pool not in ALL_POOLS or pool_kind(pool) != kind:
            self.send_json({"error": "bad pool"}, 400)
            return
        if item not in POOL_SETS.get(pool, ()):
            self.send_json({"error": "item not in pool"}, 400)
            return
        with closing(connect()) as conn, conn:
            out = apply_result(conn, pool, item, kind, result)
            counts = pool_counts(conn, pool)
        self.send_json({
            "ok": True, "pool": pool, "item": item, "kind": kind,
            "status": out["status"], "streak": out["streak"],
            "mastered": out["mastered"], "errorCount": out["errorCount"],
            "counts": counts,
        })

    def handle_reset(self, payload):
        pool = payload.get("pool")
        with closing(connect()) as conn, conn:
            if pool in (None, "", "all"):
                cur = conn.execute("DELETE FROM item_state")
            elif pool in ALL_POOLS:
                cur = conn.execute("DELETE FROM item_state WHERE pool_id = ?", (pool,))
            else:
                self.send_json({"error": "bad pool"}, 400)
                return
            deleted = cur.rowcount
        self.send_json({"ok": True, "deleted": deleted})

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/articles":
            self.handle_article_import()
            return
        m = re.fullmatch(r"/api/articles/([0-9a-f]{32})/(session|reset)", path)
        if m:
            if m.group(2) == "session":
                self.handle_article_session(m.group(1))
            else:
                self.handle_article_reset(m.group(1))
            return
        if path not in ("/api/session", "/api/attempt", "/api/learning/reset"):
            self.send_json({"error": "not found"}, 404)
            return
        payload = self.payload_or_error()
        if payload is None:
            return
        if path == "/api/attempt":
            self.handle_attempt(payload)
            return
        if path == "/api/learning/reset":
            self.handle_reset(payload)
            return

        mode = payload.get("mode")
        if mode not in ("char", "word"):
            self.send_json({"error": "bad mode"}, 400)
            return
        total = max(0, min(5000, int(payload.get("total") or 0)))
        correct = max(0, min(100000, int(payload.get("correct") or 0)))
        wrong = max(0, min(100000, int(payload.get("wrong") or 0)))
        duration = max(1.0, min(86400.0, float(payload.get("duration") or 1)))
        pool = str(payload.get("pool") or "")[:32]
        speed = total / (duration / 60.0)

        with closing(connect()) as conn, conn:
            conn.execute(
                "INSERT INTO sessions (ts, mode, pool, total, correct, wrong, duration, speed)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (local_now(), mode, pool, total, correct, wrong, duration, round(speed, 2)),
            )

        stats = stats_payload()
        self.send_json({
            "ok": True,
            "todayChars": stats["todayChars"],
            "accuracy": stats["accuracy"],
            "stats": stats,
        })

    def do_PATCH(self):
        path = urlparse(self.path).path
        m = re.fullmatch(r"/api/articles/([0-9a-f]{32})/progress", path)
        if not m:
            self.send_json({"error": "not found"}, 404)
            return
        self.handle_article_progress(m.group(1))

    def do_DELETE(self):
        path = urlparse(self.path).path
        m = re.fullmatch(r"/api/articles/([0-9a-f]{32})", path)
        if not m:
            self.send_json({"error": "not found"}, 404)
            return
        self.handle_article_delete(m.group(1))


def pick_port(preferred):
    for port in range(preferred, preferred + 20):
        try:
            probe = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            probe.server_close()
            return port
        except OSError:
            continue
    raise SystemExit("端口被占用，试试 python app.py --port 9000")


def main():
    parser = argparse.ArgumentParser(description="五笔练习本地服务")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-open", action="store_true", help="启动后不自动打开浏览器")
    args = parser.parse_args()

    if not os.path.isfile(os.path.join(WEB, "index.html")):
        raise SystemExit("找不到 web/index.html，请确认目录完整")
    if not os.path.isfile(os.path.join(DATA, "chars.json")):
        raise SystemExit("找不到 data/chars.json，请先运行 python tools/build_data.py")

    init_db()
    port = pick_port(args.port)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = "http://127.0.0.1:%d/" % port

    print("五笔练习已启动：%s" % url)
    print("按 Ctrl+C 停止。练习记录保存在 %s" % DB_PATH)

    if not args.no_open:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
