# -*- coding: utf-8 -*-
"""文章练习接口测试（使用临时库，不影响正式记录）。

运行：
  python tools/test_article_api.py
"""
import base64
import json
import os
import shutil
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import app

TMP = tempfile.mkdtemp(prefix="wubi_article_api_")
app.DB_PATH = os.path.join(TMP, "progress.db")
app.ARTICLE_MEDIA = os.path.join(TMP, "article_media")
app.init_db()
srv = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
PORT = srv.server_address[1]
BASE = "http://127.0.0.1:%d" % PORT
threading.Thread(target=srv.serve_forever, daemon=True).start()


def call(method, path, payload=None):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            return res.status, json.loads(res.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def make_docx():
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm
    from PIL import Image
    doc = Document()
    h = doc.add_heading("测试文章", level=1)
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p = doc.add_paragraph()
    r = p.add_run("第一段：")
    r.bold = True
    p.add_run("中文与 English 123，标点。")
    img = os.path.join(TMP, "dot.png")
    Image.new("RGB", (24, 16), "#336699").save(img)
    p.add_run().add_picture(img, width=Cm(1.5))
    t = doc.add_table(rows=1, cols=2)
    t.cell(0, 0).text = "甲"
    t.cell(0, 1).text = "乙"
    path = os.path.join(TMP, "sample.docx")
    doc.save(path)
    return path


def main():
    txt = "第一行\n  缩进行\n\n第二段，测试。".encode("utf-8")
    st, body = call("POST", "/api/articles", {
        "filename": "测试.txt", "data": base64.b64encode(txt).decode(),
    })
    assert st == 200, (st, body)
    a = body["article"]
    assert a["kind"] == "txt" and a["charCount"] > 0
    assert not body["duplicate"]
    aid = a["id"]
    print("[ok] 导入 txt:", a["charCount"], "字")

    st2, body2 = call("POST", "/api/articles", {
        "filename": "测试.txt", "data": base64.b64encode(txt).decode(),
    })
    assert st2 == 200 and body2["duplicate"] and body2["article"]["id"] == aid
    print("[ok] 重复导入返回原文章")

    st3, body3 = call("POST", "/api/articles", {
        "filename": "测试.txt", "data": base64.b64encode(txt).decode(), "force": True,
    })
    assert st3 == 200 and not body3["duplicate"] and body3["article"]["id"] != aid
    print("[ok] force 新建副本")

    st, body = call("GET", "/api/articles")
    assert st == 200 and len(body["articles"]) >= 2
    print("[ok] 文章列表", len(body["articles"]))

    st, body = call("GET", "/api/articles/" + aid)
    assert st == 200 and body["doc"]["blocks"][0]["type"] == "p"
    print("[ok] 文章详情")

    st, body = call("PATCH", "/api/articles/%s/progress" % aid, {
        "cursor": 3, "correct": 2, "wrong": 1, "elapsed": 12.5,
        "chars": [
            {"pos": 0, "status": "correct", "errors": 0},
            {"pos": 1, "status": "error", "errors": 2},
            {"pos": 2, "status": "correct", "errors": 0},
        ],
    })
    assert st == 200, (st, body)
    st, body = call("GET", "/api/articles/" + aid)
    assert body["progress"]["cursor"] == 3 and len(body["chars"]) == 3
    print("[ok] 保存/读取进度")

    st, body = call("POST", "/api/articles/%s/reset" % aid)
    assert st == 200
    st, body = call("GET", "/api/articles/" + aid)
    assert body["progress"]["cursor"] == 0 and body["chars"] == []
    print("[ok] 重置文章")

    st, body = call("POST", "/api/articles/%s/session" % aid, {
        "total": 10, "correct": 9, "wrong": 1, "duration": 60,
    })
    assert st == 200 and body["stats"]["recent"][0]["mode"] == "article"
    print("[ok] 文章成绩写入统计")

    dp = make_docx()
    raw = open(dp, "rb").read()
    st, body = call("POST", "/api/articles", {
        "filename": "sample.docx", "data": base64.b64encode(raw).decode(),
    })
    assert st == 200, (st, body)
    d = body["article"]
    assert d["kind"] == "docx" and d["charCount"] > 0
    assert any(b["type"] == "table" for b in d["doc"]["blocks"])
    images = [r for b in d["doc"]["blocks"] if b["type"] == "p"
              for r in b.get("runs", []) if r.get("type") == "image"]
    assert images, "docx 图片未解析"
    with urllib.request.urlopen(BASE + images[0]["src"], timeout=5) as res:
        assert res.status == 200 and res.headers.get("Content-Type", "").startswith("image/")
        assert len(res.read()) > 0
    print("[ok] 导入 docx:", d["charCount"], "字，含表格与图片")

    st, body = call("POST", "/api/articles", {
        "filename": "x.pdf", "data": base64.b64encode(b"x").decode(),
    })
    assert st == 400
    print("[ok] 拒绝不支持的扩展名")

    st, body = call("DELETE", "/api/articles/" + aid)
    assert st == 200
    st, body = call("GET", "/api/articles/" + aid)
    assert st == 404
    print("[ok] 删除文章")

    print("\n文章接口测试全部通过")
    srv.shutdown()
    shutil.rmtree(TMP, ignore_errors=True)


if __name__ == "__main__":
    main()
