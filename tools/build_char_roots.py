# -*- coding: utf-8 -*-
"""从 search-wubi-main 生成常用字的逐字拆解数据。

用法：
  python tools/build_char_roots.py
  python tools/build_char_roots.py --source C:\\path\\to\\search-wubi-main

输入：
  search-wubi-main/data/data-wubi-v86.tsv
  search-wubi-main/data/data-chars.tsv
  search-wubi-main/docs/static/font/黑体字根.ttf

输出：
  data/char_roots.json
  web/fonts/wubi-roots.ttf
"""
import argparse
import csv
import json
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
DEFAULT_SOURCE = os.path.join(ROOT, "search-wubi-main")


def parse_segments(value):
    """'0-3/4-5/6-8' -> [[0,1,2,3],[4,5],[6,8]]"""
    out = []
    for part in (value or "").strip().strip("*").split("/"):
        part = part.strip()
        if not part:
            continue
        nums = []
        for token in part.split(","):
            token = token.strip()
            if not token:
                continue
            if "-" in token:
                a, b = token.split("-", 1)
                try:
                    nums.extend(range(int(a), int(b) + 1))
                except ValueError:
                    pass
            else:
                try:
                    nums.append(int(token))
                except ValueError:
                    pass
        out.append(sorted(set(nums)))
    return out


STROKE_ZONE = {"横": 1, "竖": 2, "丿": 3, "捺": 4, "折": 5}
STROKE_NAME = {"横": "横", "竖": "竖", "丿": "撇", "捺": "捺", "折": "折"}
STRUCT_POS = {"左右": 1, "上下": 2, "杂合": 3}
IDENT_KEYS = {
    (1, 1): "G", (1, 2): "F", (1, 3): "D",
    (2, 1): "H", (2, 2): "J", (2, 3): "K",
    (3, 1): "T", (3, 2): "R", (3, 3): "E",
    (4, 1): "Y", (4, 2): "U", (4, 3): "I",
    (5, 1): "N", (5, 2): "B", (5, 3): "V",
}


def parse_identify(flag):
    """'捺·杂合〔丶 ⿻〕' -> 识别码分类；无法解析返回 None。"""
    flag = (flag or "").strip()
    if "·" not in flag:
        return None
    stroke, rest = flag.split("·", 1)
    stroke = stroke.strip()
    structure = rest.split("〔", 1)[0].strip()
    zone = STROKE_ZONE.get(stroke)
    pos = STRUCT_POS.get(structure)
    if not zone or not pos:
        return None
    return {
        "stroke": stroke,
        "strokeName": STROKE_NAME[stroke],
        "zone": zone,
        "structure": structure,
        "position": pos,
        "key": IDENT_KEYS[(zone, pos)],
        "code": "%d%d" % (zone, pos),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=DEFAULT_SOURCE,
                    help="search-wubi-main directory")
    ap.add_argument("--pool", default="gb2312",
                    help="pool id used as common-char set (default: gb2312)")
    args = ap.parse_args()

    pools = json.load(open(os.path.join(DATA, "pools.json"), encoding="utf-8"))
    chars = json.load(open(os.path.join(DATA, "chars.json"), encoding="utf-8"))["chars"]
    common = set(pools.get(args.pool) or [])
    if not common:
        raise SystemExit("pool not found or empty: " + args.pool)

    wubi_path = os.path.join(args.source, "data", "data-wubi-v86.tsv")
    info_path = os.path.join(args.source, "data", "data-chars.tsv")
    font_path = os.path.join(args.source, "docs", "static", "font", "黑体字根.ttf")
    if not os.path.isfile(wubi_path):
        raise SystemExit("missing " + wubi_path)
    if not os.path.isfile(info_path):
        raise SystemExit("missing " + info_path)

    info = {}
    with open(info_path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            info[row["char"]] = row

    out = {}
    skipped = []
    with open(wubi_path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            ch = row["char"]
            if ch not in common:
                continue
            code = (row.get("code") or "").strip().lower()
            units = (row.get("units") or "").strip()
            units = units.strip("〖〗")
            units = [u for u in units.split("※") if u]
            if not code or not units:
                skipped.append({"char": ch, "reason": "empty code/units"})
                continue
            ours = chars.get(ch)
            if not ours or code not in (ours.get("f"), ours.get("s")):
                skipped.append({"char": ch, "reason": "code mismatch", "source": code,
                                "ours": (ours or {})})
                continue
            if len(units) > len(code):
                skipped.append({"char": ch, "reason": "units longer than code",
                                "units": len(units), "code": code})
                continue
            level = (info.get(ch, {}).get("level") or "")
            flag = (row.get("flag") or "").strip()
            identify = parse_identify(flag)
            out[ch] = {
                "code": code,
                "level": level,
                "units": units,
                "keys": list(code[:len(units)]),
                "identifyLast": bool(flag),
                "identify": identify,
                "flag": flag,
                "segments": parse_segments(row.get("segments") or ""),
            }

    result = {
        "version": 1,
        "pool": args.pool,
        "source": "search-wubi-main/data/data-wubi-v86.tsv + data-chars.tsv + 黑体字根.ttf",
        "count": len(out),
        "skipped": skipped,
        "chars": out,
    }
    out_path = os.path.join(DATA, "char_roots.json")
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(result, f, ensure_ascii=False, separators=(",", ":"))
    print("wrote", out_path, "chars", len(out), "skipped", len(skipped))
    for s in skipped:
        print("  skip", s["char"], s["reason"], s.get("source", ""), s.get("ours", ""))

    if os.path.isfile(font_path):
        font_out = os.path.join(ROOT, "web", "fonts")
        os.makedirs(font_out, exist_ok=True)
        shutil.copyfile(font_path, os.path.join(font_out, "wubi-roots.ttf"))
        print("copied font -> web/fonts/wubi-roots.ttf")

    for ch in ("照", "好", "弥", "春"):
        if ch in out:
            v = out[ch]
            print(ch, v["code"], v["keys"], "identifyLast", v["identifyLast"],
                  "units", [hex(ord(c)) for c in v["units"]])


if __name__ == "__main__":
    main()
