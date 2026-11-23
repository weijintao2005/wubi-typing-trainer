# -*- coding: utf-8 -*-
"""从 Rime wubi86 码表生成练习用的数据文件（data/*.json）。

用法：
    python tools/build_data.py

输入：
    _ref/wubi86.dict.yaml   （Rime 五笔86 码表，含单字/词组及字频）

输出：
    data/keys86.json   25 个键位：字根、口诀、分区、指法
    data/chars.json    单字 -> 编码信息
    data/words.json    词组 -> 编码
    data/pools.json    练习字库（一级简码/二级简码/常用字/...）
"""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "_ref", "wubi86.dict.yaml")
OUT = os.path.join(ROOT, "data")

# ---------------------------------------------------------------- 键位与字根
# 86 版五笔字根表（常见字根，按键位排列）。口诀为传统口诀。
KEYS = [
    # key, zone, 键名, roots, 口诀
    ("G", 1, "王", ["王", "龶", "一", "五", "戋"], "王旁青头戋（兼）五一"),
    ("F", 1, "土", ["土", "士", "二", "干", "十", "寸", "雨"], "土士二干十寸雨"),
    ("D", 1, "大", ["大", "犬", "三", "羊", "古", "石", "厂", "丆", "ナ"], "大犬三羊古石厂"),
    ("S", 1, "木", ["木", "丁", "西", "覀"], "木丁西"),
    ("A", 1, "工", ["工", "戈", "弋", "艹", "廾", "匚", "七"], "工戈草头右框七"),
    ("H", 2, "目", ["目", "具", "上", "止", "卜", "虍", "皮", "丨"], "目具上止卜虎皮"),
    ("J", 2, "日", ["日", "曰", "早", "虫", "刂"], "日早两竖与虫依"),
    ("K", 2, "口", ["口", "川", "丨"], "口与川，字根稀"),
    ("L", 2, "田", ["田", "甲", "囗", "四", "罒", "车", "力", "皿"], "田甲方框四车力"),
    ("M", 2, "山", ["山", "由", "贝", "冂", "几"], "山由贝，下框几"),
    ("T", 3, "禾", ["禾", "竹", "丿", "彳", "攵", "夂"], "禾竹一撇双人立，反文条头共三一"),
    ("R", 3, "白", ["白", "手", "扌", "斤", "龵"], "白手看头三二斤"),
    ("E", 3, "月", ["月", "彡", "乃", "用", "豕", "衣"], "月彡（衫）乃用家衣底"),
    ("W", 3, "人", ["人", "亻", "八", "癶", "祭"], "人和八，三四里"),
    ("Q", 3, "金", ["金", "钅", "勺", "鱼", "犬", "儿", "夕", "氏"], "金勺缺点无尾鱼，犬旁留儿一点夕，氏无七"),
    ("Y", 4, "言", ["言", "讠", "文", "方", "广", "亠", "丶"], "言文方广在四一，高头一捺谁人去"),
    ("U", 4, "立", ["立", "辛", "丬", "六", "门", "疒", "丷"], "立辛两点六门疒"),
    ("I", 4, "水", ["水", "氵", "小", "⺌"], "水旁兴头小倒立"),
    ("O", 4, "火", ["火", "灬", "业", "米"], "火业头，四点米"),
    ("P", 4, "之", ["之", "辶", "宀", "冖", "礻", "衤"], "之宝盖，摘礻（示）衤（衣）"),
    ("N", 5, "已", ["已", "己", "巳", "尸", "心", "忄", "羽", "乙"], "已半巳满不出己，左框折尸心和羽"),
    ("B", 5, "子", ["子", "孑", "耳", "阝", "了", "也", "凵"], "子耳了也框向上"),
    ("V", 5, "女", ["女", "刀", "九", "臼", "彐"], "女刀九臼山朝西"),
    ("C", 5, "又", ["又", "巴", "马", "厶"], "又巴马，丢矢矣"),
    ("X", 5, "纟", ["纟", "母", "弓", "匕", "幺"], "慈母无心弓和匕，幼无力"),
]

ZONE_NAMES = {1: "横区", 2: "竖区", 3: "撇区", 4: "捺区", 5: "折区"}

FINGER = {
    "Q": "左小指", "W": "左无名", "E": "左中指", "R": "左食指", "T": "左食指",
    "Y": "右食指", "U": "右食指", "I": "右中指", "O": "右无名", "P": "右小指",
    "A": "左小指", "S": "左无名", "D": "左中指", "F": "左食指", "G": "左食指",
    "H": "右食指", "J": "右食指", "K": "右中指", "L": "右无名",
    "Z": "左小指", "X": "左无名", "C": "左中指", "V": "左食指", "B": "左食指",
    "N": "右食指", "M": "右食指",
}

# 常被吐槽“难拆”的字，练的是拆根思路，不是生僻字。
HARD = list(
    "凹凸鼎舞乘爽曹遭燕微赢藏疆攀囊蠢鬻爨龟鼠鼻齿骨鹿麻馨麾磨鹰雁拜掰辨辩辫瓣瓜瓢"
    "肃隶尹弗弟弓弔廿甘世革齿鹿麾磨馨鼠鼻龠革垂重再冉曳尧夷戊戌戍戎戒戋"
    "藏曦疆攀囊囊囊"
)

# 一级简码（25 个）
JM1 = list("我人有的和主产不为这民了发以经工要在地一上是中国同")


def gb2312_ok(ch):
    try:
        ch.encode("gb2312")
        return True
    except UnicodeEncodeError:
        return False


def parse_dict():
    chars = {}   # char -> {(code, weight)}
    words = {}   # word -> (code, weight)
    lines = open(SRC, encoding="utf-8").read().splitlines()
    start = lines.index("...")
    for line in lines[start + 1:]:
        line = line.rstrip()
        if not line or line.startswith("#"):
            continue
        f = line.split("\t")
        if len(f) < 3:
            continue
        text, code, weight = f[0], f[1].strip().lower(), float(f[2])
        if not code or not re.fullmatch(r"[a-z]{1,4}", code):
            continue
        if len(text) == 1:
            chars.setdefault(text, set()).add((code, weight))
        else:
            old = words.get(text)
            if old is None or weight > old[1]:
                words[text] = (code, weight)
    return chars, words


def main():
    os.makedirs(OUT, exist_ok=True)
    chars, words = parse_dict()

    # 单字：取最短码作为练习码，最长码作为全码
    char_data = {}
    for ch, pairs in chars.items():
        codes = sorted({c for c, _ in pairs}, key=len)
        short = min(codes, key=len)
        full = max(codes, key=len)
        w = max(x for _, x in pairs)
        char_data[ch] = {"short": short, "full": full, "w": w, "codes": codes}

    # 字库
    pools = {}
    jm1 = [c for c in dict.fromkeys(JM1) if c in char_data]
    pools["jm1"] = jm1
    pools["jm2"] = [c for c, d in char_data.items() if len(d["short"]) == 2 and gb2312_ok(c)]
    pools["jm3"] = [c for c, d in char_data.items() if len(d["short"]) == 3 and gb2312_ok(c)]
    pools["jm4"] = [c for c, d in char_data.items() if len(d["short"]) == 4 and gb2312_ok(c)]

    gb1 = [c for c in char_data if gb2312_ok(c) and c.encode("gb2312")[0] >= 0xB0]
    pools["common"] = sorted(gb1, key=lambda c: -char_data[c]["w"])[:1000]
    pools["common2"] = sorted(gb1, key=lambda c: -char_data[c]["w"])[:2500]
    pools["gb2312"] = sorted(gb1, key=lambda c: -char_data[c]["w"])

    key_names = []
    for k, zone, name, roots, rhyme in KEYS:
        if name in char_data:
            key_names.append(name)
    pools["keyname"] = key_names

    root_chars = []
    seen = set()
    for k, zone, name, roots, rhyme in KEYS:
        for r in roots:
            if len(r) == 1 and r in char_data and r not in seen:
                seen.add(r)
                if r not in key_names:
                    root_chars.append(r)
    pools["chengzi"] = root_chars

    hard = []
    for c in dict.fromkeys(HARD):
        if c in char_data and c not in hard:
            hard.append(c)
    pools["hard"] = hard

    # 词库：只保留全部字在 GB2312 内、码长 3-4 的词
    word_data = {}
    for word, (code, w) in words.items():
        if not (2 <= len(word) <= 4):
            continue
        if len(code) < 3:
            continue
        if not all(gb2312_ok(ch) for ch in word):
            continue
        word_data[word] = {"code": code, "w": w}

    # 词组练习库：按字频取较常用的一部分，避免生僻组合
    def top_words(limit, length):
        items = [(w, d["w"]) for w, d in word_data.items() if len(w) == length]
        items.sort(key=lambda x: -x[1])
        return [w for w, _ in items[:limit]]

    pools["w2"] = top_words(12000, 2)
    pools["w3"] = top_words(10000, 3)
    pools["w4"] = top_words(6000, 4)

    keys_out = []
    for key, zone, name, roots, rhyme in KEYS:
        keys_out.append({
            "key": key, "zone": zone, "zoneName": ZONE_NAMES[zone], "name": name,
            "roots": roots, "rhyme": rhyme, "finger": FINGER[key],
        })

    def dump(name, obj):
        path = os.path.join(OUT, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
        print("%-14s %8.1f KB" % (name, os.path.getsize(path) / 1024))

    dump("keys86.json", keys_out)
    dump("chars.json", {
        "chars": {c: {"s": d["short"], "f": d["full"]} for c, d in char_data.items()},
    })
    dump("words.json", {
        "words": {w: d["code"] for w, d in word_data.items()},
    })
    dump("pools.json", pools)

    print("\n单字 %d，词组 %d" % (len(char_data), len(word_data)))
    print("一级简码 %d：%s" % (len(jm1), " ".join("%s=%s" % (c, char_data[c]["short"]) for c in jm1)))
    for k in ("jm2", "jm3", "jm4", "common", "common2", "gb2312", "keyname", "chengzi", "hard"):
        print("%-8s %d" % (k, len(pools[k])))

    # 校验：一级简码应都是一码
    bad = [c for c in jm1 if len(char_data[c]["short"]) != 1]
    if bad:
        print("!! 一级简码不是一码：", bad)
    missing = [c for c in JM1 if c not in char_data]
    if missing:
        print("!! 码表缺少一级简码字：", missing)


if __name__ == "__main__":
    main()
