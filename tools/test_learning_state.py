# -*- coding: utf-8 -*-
"""学习状态与出题接口测试（开发用，使用临时库）。

运行：
  python tools/test_learning_state.py

覆盖：首次全对→low、连对 3 次→mastered、错题连对 3 次→mastered、
错误清零、错题本多来源回写、状态查询、统计、重置、参数校验、
旧 err_chars 迁移。
"""
import json
import os
import sqlite3
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import app


def http(method, url, payload=None):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8") or "{}")


def attempt(base, pool, item, kind, result):
    return http("POST", base + "/api/attempt", {
        "pool": pool, "item": item, "kind": kind, "result": result,
    })[1]


def main():
    app.load_pools()
    app.DB_PATH = os.path.join(tempfile.gettempdir(), "wubi_learning_api.db")
    for suffix in ("", "-wal", "-shm"):
        try:
            os.remove(app.DB_PATH + suffix)
        except OSError:
            pass
    app.init_db()

    srv = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % port

    # 首次全对 -> low 1/3
    r = attempt(base, "common", "的", "char", "perfect")
    assert (r["status"], r["streak"], r["mastered"]) == ("low", 1, False), r
    assert r["counts"]["low"] == 1 and r["counts"]["new"] == 999, r["counts"]
    print("[ok] 首次全对 -> low 1/3")

    # 连续 3 次 -> mastered
    attempt(base, "common", "的", "char", "perfect")
    r = attempt(base, "common", "的", "char", "perfect")
    assert (r["status"], r["streak"], r["mastered"]) == ("mastered", 3, True), r
    assert r["counts"]["mastered"] == 1
    print("[ok] low 连对 3 次 -> mastered")

    # 首次错误 -> error
    r = attempt(base, "common", "是", "char", "error")
    assert (r["status"], r["streak"], r["errorCount"]) == ("error", 0, 1), r
    # 错误清零后再连对 3 次 -> mastered
    attempt(base, "common", "是", "char", "perfect")
    attempt(base, "common", "是", "char", "perfect")
    r = attempt(base, "common", "是", "char", "perfect")
    assert r["mastered"] is True, r
    print("[ok] 错题连对 3 次 -> mastered")

    # 错误清零
    attempt(base, "common", "不", "char", "perfect")
    r = attempt(base, "common", "不", "char", "error")
    assert r["streak"] == 0, r
    print("[ok] 错误清零")

    # 在 common / jm2 同时是错题，错题本回写两个来源
    attempt(base, "common", "面", "char", "error")
    attempt(base, "jm2", "面", "char", "error")
    errs = http("GET", base + "/api/errors")[1]["errors"]
    row = next(e for e in errs if e["item"] == "面")
    assert {s["pool"] for s in row["sources"]} == {"common", "jm2"}, row
    for _ in range(3):
        r = attempt(base, "errors", "面", "char", "perfect")
    assert r["stillError"] is False, r
    assert len(r["sources"]) == 2 and all(s["status"] == "mastered" for s in r["sources"]), r
    print("[ok] 错题本回写多来源并全部掌握")

    # 状态查询
    learn = http("GET", base + "/api/learning?pool=common")[1]
    assert "的" in learn["items"] and learn["items"]["的"]["status"] == "mastered"
    assert learn["counts"]["total"] == 1000
    print("[ok] /api/learning")

    # 统计
    stats = http("GET", base + "/api/stats")[1]
    assert stats["learning"]["distinct"]["mastered"] >= 2
    assert any(p["id"] == "common" for p in stats["learning"]["pools"])
    print("[ok] /api/stats learning")

    # 重置
    r = http("POST", base + "/api/learning/reset", {"pool": "common"})[1]
    assert r["deleted"] > 0
    learn = http("GET", base + "/api/learning?pool=common")[1]
    assert learn["counts"]["mastered"] == 0 and learn["counts"]["new"] == 1000
    print("[ok] 重置科目")

    # 参数校验
    status, _ = http("POST", base + "/api/attempt", {"pool": "nope", "item": "的", "kind": "char", "result": "perfect"})
    assert status == 400
    status, _ = http("POST", base + "/api/attempt", {"pool": "common", "item": "的", "kind": "word", "result": "perfect"})
    assert status == 400
    print("[ok] 参数校验")

    srv.shutdown()

    # 迁移旧库
    old = os.path.join(tempfile.gettempdir(), "wubi_learning_migrate.db")
    for suffix in ("", "-wal", "-shm"):
        try:
            os.remove(old + suffix)
        except OSError:
            pass
    c = sqlite3.connect(old)
    c.execute("CREATE TABLE err_chars (char TEXT PRIMARY KEY, count INTEGER NOT NULL DEFAULT 0, last_ts TEXT)")
    c.execute("INSERT INTO err_chars (char,count,last_ts) VALUES ('不', 3, '2020-01-01 00:00:00')")
    c.commit()
    c.close()
    app.DB_PATH = old
    app.init_db()
    c = sqlite3.connect(old)
    rows = c.execute("SELECT pool_id,status,right_streak,error_count FROM item_state WHERE item='不'").fetchall()
    version = c.execute("PRAGMA user_version").fetchone()[0]
    c.close()
    assert version == 2, version
    assert rows and all(r[1] == "error" for r in rows), rows
    assert any(r[0] == "common" for r in rows), rows
    print("[ok] 旧库迁移:", rows)

    for path in (app.DB_PATH,):
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(path + suffix)
            except OSError:
                pass
    print("\n服务端学习状态测试全部通过")


if __name__ == "__main__":
    main()
