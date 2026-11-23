# -*- coding: utf-8 -*-
"""校验常用字逐字拆解数据（不启动服务）。"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")


def main():
    roots = json.load(open(os.path.join(DATA, "char_roots.json"), encoding="utf-8"))
    chars = json.load(open(os.path.join(DATA, "chars.json"), encoding="utf-8"))["chars"]
    pools = json.load(open(os.path.join(DATA, "pools.json"), encoding="utf-8"))
    common = set(pools["gb2312"])
    assert roots["count"] == len(roots["chars"])
    assert len(roots["skipped"]) == 7
    assert roots["count"] >= 6700
    for ch, item in roots["chars"].items():
        assert ch in common
        assert ch in chars
        assert item["code"] in (chars[ch]["f"], chars[ch]["s"])
        assert 3 <= len(item["units"]) <= 4
        assert len(item["units"]) == len(item["keys"])
        for unit in item["units"]:
            assert 0xE000 <= ord(unit) <= 0xF8FF, (ch, hex(ord(unit)))
        for key in item["keys"]:
            assert key.lower() in "abcdefghijklmnopqrstuvwxy"
    assert roots["chars"]["照"]["units"]
    assert roots["chars"]["照"]["keys"] == ["j", "v", "k", "o"]
    assert roots["chars"]["照"]["identify"] is None
    assert roots["chars"]["好"]["identifyLast"] is True
    assert roots["chars"]["好"]["identify"]["key"] == "G"
    assert roots["chars"]["好"]["identify"]["structure"] == "左右"
    assert roots["chars"]["汉"]["identify"]["key"] == "Y"
    assert roots["chars"]["天"]["identify"]["key"] == "I"
    assert roots["chars"]["春"]["identify"]["key"] == "F"
    assert sum(1 for x in roots["chars"].values() if x.get("identify")) == 3012
    font = os.path.join(ROOT, "web", "fonts", "wubi-roots.ttf")
    assert os.path.getsize(font) > 10000
    print("char roots ok:", roots["count"], "skipped", len(roots["skipped"]),
          "identify", 3012, "font", os.path.getsize(font))


if __name__ == "__main__":
    main()
