# -*- coding: utf-8 -*-
"""端到端冒烟测试（可选，开发用）。

前置：
  1. 本地服务运行在 http://127.0.0.1:8765（可用环境变量 WUBI_BASE 覆盖）
  2. Chrome 以调试端口启动：
     chrome.exe --headless=new --remote-debugging-port=9222 --user-data-dir=%TEMP%\\wb-e2e

运行：
  python tools/e2e_test.py

覆盖：默认不显示提示、错键不泄露答案、空格看提示、Esc 重开本轮、连续输入一整轮、
结算与入库、跳过、全码模式、编码查询正查/反查、键位反应练习、词组练习、统计页。
"""
import json
import os
import time
import urllib.parse
import urllib.request

import websocket

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.environ.get("WUBI_BASE", "http://127.0.0.1:8765")
CDP = "http://127.0.0.1:9222"

CHARS = json.load(open(os.path.join(ROOT, "data", "chars.json"), encoding="utf-8"))["chars"]
WORDS = json.load(open(os.path.join(ROOT, "data", "words.json"), encoding="utf-8"))["words"]
KEYS = {k["key"]: k for k in json.load(open(os.path.join(ROOT, "data", "keys86.json"), encoding="utf-8"))}


def connect():
    targets = json.loads(urllib.request.urlopen(CDP + "/json/list", timeout=10).read())
    page = next(x for x in targets if x["type"] == "page")
    ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=30)
    state = {"n": 0}

    def call(method, **params):
        state["n"] += 1
        ws.send(json.dumps({"id": state["n"], "method": method, "params": params}))
        while True:
            msg = json.loads(ws.recv())
            if msg.get("id") == state["n"]:
                if "error" in msg:
                    raise RuntimeError(method + ": " + str(msg["error"]))
                return msg.get("result", {})

    def ev(expr):
        r = call("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
        if r.get("exceptionDetails"):
            raise RuntimeError("JS: " + json.dumps(r["exceptionDetails"])[:300])
        return r.get("result", {}).get("value")

    def press(key_name, code, vk, text=None):
        params = dict(type="keyDown", key=key_name, code=code,
                      windowsVirtualKeyCode=vk, nativeVirtualKeyCode=vk)
        if text is not None:
            params["text"] = text
        call("Input.dispatchKeyEvent", **params)
        call("Input.dispatchKeyEvent", type="keyUp", key=key_name, code=code,
             windowsVirtualKeyCode=vk, nativeVirtualKeyCode=vk)

    def key(letter):
        vk = ord(letter.upper())
        press(letter, "Key" + letter.upper(), vk, letter)

    def space():
        press(" ", "Space", 32, " ")

    def escape():
        press("Escape", "Escape", 27)

    def wait(expr, timeout=10, label=""):
        end = time.time() + timeout
        while time.time() < end:
            try:
                if ev(expr):
                    return True
            except RuntimeError:
                pass
            time.sleep(0.04)
        raise TimeoutError("超时: " + (label or expr))

    return ws, call, ev, key, wait, space, escape


def type_round(ev, key, wait, view, kind, count):
    tag = "#view-%s " % view
    prev = None
    for _ in range(count):
        if prev is not None:
            wait("document.querySelector('%s[data-role=char]').textContent!==%s"
                 % (tag, json.dumps(prev)), 4, "下一字")
        ch = ev("document.querySelector('%s[data-role=char]').textContent" % tag)
        code = CHARS[ch]["s"] if kind == "char" else WORDS[ch]
        for idx, letter in enumerate(code):
            key(letter)
            time.sleep(0.03)
            got = ev("document.querySelectorAll('%s[data-role=slots] .slot.filled').length" % tag)
            assert got == idx + 1, "%s 第 %d 键后格数 %s" % (ch, idx + 1, got)
        end = time.time() + 3
        ok = False
        while time.time() < end:
            if (ev("document.querySelector('%s[data-role=sub]').textContent" % tag)
                    or ev("document.querySelector('%s[data-role=char]').textContent" % tag) != ch):
                ok = True
                break
            time.sleep(0.04)
        assert ok, "字 %s 未完成" % ch
        prev = ch


def main():
    ws, call, ev, key, wait, space, escape = connect()
    call("Page.enable")
    call("Runtime.enable")
    call("Page.navigate", url=BASE + "/?t=%d#/five" % int(time.time()))
    wait("!!document.querySelector('#view-five .chip')", 20, "首页")
    ev("localStorage.setItem('wubi.prefs.v2', JSON.stringify({perRound:20,mode:'short',autoHint:false,sound:false}))")
    call("Page.reload")
    wait("!!document.querySelector('#view-five .chip')", 20, "重载")
    time.sleep(0.4)
    print("[ok] 页面加载，每轮 20 字")

    before = json.loads(urllib.request.urlopen(BASE + "/api/stats").read())["totalChars"]
    type_round(ev, key, wait, "five", "char", 20)
    print("[ok] 连续完成 20 字")

    wait("!document.querySelector('#modalMask').hidden", 5, "结算弹层")
    summary = ev("document.querySelector('#modalCard').innerText")
    assert "正确率" in summary
    print("[ok] 结算弹层:", summary.replace("\n", " | ")[:70])

    time.sleep(0.6)
    stats = json.loads(urllib.request.urlopen(BASE + "/api/stats").read())
    assert stats["totalChars"] - before == 20
    print("[ok] 记录入库: 累计 %d 字, 正确率 %.1f%%" % (stats["totalChars"], stats["accuracy"]))

    ev("document.querySelector('#modalCard [data-act=stats]').click()")
    wait("document.querySelector('#modalMask').hidden", 3)
    call("Page.navigate", url=BASE + "/#/five")
    wait("!!document.querySelector('#view-five [data-role=char]')", 6)
    time.sleep(0.5)

    ch = ev("document.querySelector('#view-five [data-role=char]').textContent")
    hint0 = ev("document.querySelector('#view-five [data-role=hint]').innerText")
    assert "输入五笔编码" in hint0, hint0
    assert ev("document.querySelectorAll('#view-five .key.active').length") == 0
    print("[ok] 默认不显示编码提示")

    right = CHARS[ch]["s"][0]
    key("q" if right != "q" else "w")
    time.sleep(0.2)
    toast_txt = ev("document.querySelector('#toast').textContent")
    assert "按错了" in toast_txt, toast_txt
    assert "空格" in ev("document.querySelector('#view-five [data-role=hint]').innerText")
    assert ev("document.querySelectorAll('#view-five .key.active').length") == 0
    print("[ok] 答错后不直接给答案")

    space()
    time.sleep(0.2)
    hint1 = ev("document.querySelector('#view-five [data-role=hint]').innerText")
    assert "键 ——" in hint1, hint1
    assert ev("document.querySelectorAll('#view-five .key.active').length") == 1
    assert ev("document.querySelectorAll('#view-five [data-role=slots] .slot.filled').length") == 0
    assert ev("document.querySelector('#view-five [data-role=hintBtn]').disabled") is True
    print("[ok] 空格显示提示:", hint1.split("·")[-1][:30])

    # 完整打一个字后按 Esc，验证本轮重置
    for letter in CHARS[ch]["s"]:
        key(letter)
        time.sleep(0.05)
    wait("document.querySelector('#view-five [data-role=count]').innerText.indexOf('1 /')===0", 3, "完成一字")
    escape()
    time.sleep(0.3)
    assert ev("document.querySelector('#view-five [data-role=count]').innerText") == "0 / 20"
    assert ev("document.querySelectorAll('#view-five [data-role=slots] .slot.filled').length") == 0
    assert "重新开始" in ev("document.querySelector('#toast').textContent")
    print("[ok] Esc 重新开始本轮")

    old = ev("document.querySelector('#view-five [data-role=char]').textContent")
    ev("document.querySelector('#view-five [data-role=skip]').click()")
    wait("document.querySelector('#view-five [data-role=char]').textContent!==%s" % json.dumps(old), 3)
    print("[ok] 跳过")

    ev("document.querySelector('#optMode [data-mode=\"full\"]').click()")
    time.sleep(0.4)
    ch = ev("document.querySelector('#view-five [data-role=char]').textContent")
    assert ev("document.querySelectorAll('#view-five [data-role=slots] .slot').length") == len(CHARS[ch]["f"])
    print("[ok] 全码模式:", ch, CHARS[ch]["f"])
    ev("document.querySelector('#optMode [data-mode=\"short\"]').click()")
    time.sleep(0.4)

    for query, expect in [("的", "RQYY"), ("中国", "KHLG"), ("rqyy", "的")]:
        call("Page.navigate", url=BASE + "/#/dict?q=" + urllib.parse.quote(query))
        wait("document.querySelectorAll('#view-dict .dict-row').length>0", 8, "查询 " + query)
        text = ev("document.querySelector('#view-dict .dict-row').innerText")
        assert expect.lower() in text.lower(), (query, text)
        print("[ok] 查询 %s" % query)

    call("Page.navigate", url=BASE + "/#/roots")
    wait("!!document.querySelector('#drillStart')", 8)
    ev("document.querySelector('#drillStart').click()")
    time.sleep(0.25)
    prompt = ev("document.querySelector('#drillPrompt').textContent")
    answer = next(k for k, v in KEYS.items() if v["rhyme"] == prompt)
    key(answer.lower())
    time.sleep(0.4)
    assert ev("document.querySelector('#drillOk').textContent") == "1"
    print("[ok] 键位练习:", prompt, "->", answer)

    call("Page.navigate", url=BASE + "/#/words")
    wait("!!document.querySelector('#view-words .chip')", 15, "词组页")
    time.sleep(0.4)
    type_round(ev, key, wait, "words", "word", 3)
    print("[ok] 词组练习 3 词")

    call("Page.navigate", url=BASE + "/#/stats")
    wait("document.querySelectorAll('#statCards .s-card').length===5", 8)
    wait("document.querySelectorAll('#learningCards .s-card').length===3", 8)
    print("[ok] 统计页")

    ws.close()
    print("\n全部通过")


if __name__ == "__main__":
    main()
