# -*- coding: utf-8 -*-
"""把 docs/design.md 渲染成 Word 详细设计文档。

用法（使用带 python-docx 的 Python）：
    python tools/build_design_docx.py

输出：
    docs/五笔练习详细设计文档.docx
"""
import os
import re

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "docs", "design.md")
OUT = os.path.join(ROOT, "docs", "五笔练习详细设计文档.docx")

BODY_FONT = "宋体"
HEAD_FONT = "微软雅黑"
CODE_FONT = "Consolas"
INK = RGBColor(0x23, 0x20, 0x1C)
MUTED = RGBColor(0x5C, 0x55, 0x4C)
ACCENT = RGBColor(0x8F, 0x2F, 0x26)
LINE = "D8CEBD"
HEAD_FILL = "EFE8DC"
CODE_FILL = "F6F2EA"
ZEBRA_FILL = "FBF7EF"


# ------------------------------------------------------------------ 样式工具
def set_run_font(run, name, size=None, bold=None, color=None, italic=None):
    run.font.name = name
    if size:
        run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic
    if color is not None:
        run.font.color.rgb = color
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:eastAsia"), name)


def set_style_font(style, name, size=None, bold=None, color=None):
    style.font.name = name
    if size:
        style.font.size = Pt(size)
    if bold is not None:
        style.font.bold = bold
    if color is not None:
        style.font.color.rgb = color
    rpr = style.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:eastAsia"), name)


def shade(paragraph, fill):
    ppr = paragraph._p.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    ppr.append(shd)


def shade_cell(cell, fill):
    tcpr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tcpr.append(shd)


def set_table_borders(table, color=LINE, size=4):
    tbl = table._tbl
    tblpr = tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement("w:" + edge)
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), str(size))
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), color)
        borders.append(el)
    tblpr.append(borders)


def set_cell_margins(table, top=40, bottom=40, left=90, right=90):
    tblpr = table._tbl.tblPr
    mar = OxmlElement("w:tblCellMar")
    for side, val in (("top", top), ("left", left), ("bottom", bottom), ("right", right)):
        el = OxmlElement("w:" + side)
        el.set(qn("w:w"), str(val))
        el.set(qn("w:type"), "dxa")
        mar.append(el)
    tblpr.append(mar)


def repeat_header(row):
    trpr = row._tr.get_or_add_trPr()
    el = OxmlElement("w:tblHeader")
    el.set(qn("w:val"), "true")
    trpr.append(el)


def add_page_field(paragraph):
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.append(begin)
    run._r.append(instr)
    run._r.append(end)


def add_hr(doc, color=LINE):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(6)
    ppr = p._p.get_or_add_pPr()
    pborder = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "4")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), color)
    pborder.append(bottom)
    ppr.append(pborder)


# ------------------------------------------------------------------ Markdown 解析
def is_table_sep(line):
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", c) for c in cells)


def split_row(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse_blocks(text):
    lines = text.splitlines()
    blocks = []
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        if stripped.startswith("```"):
            i += 1
            code = []
            while i < n and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            i += 1
            blocks.append(("code", code))
            continue

        m = re.match(r"^(#{1,4})\s+(.*)$", line)
        if m:
            blocks.append(("heading", len(m.group(1)), m.group(2).strip()))
            i += 1
            continue

        if stripped.startswith("|") and i + 1 < n and is_table_sep(lines[i + 1]):
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                if not is_table_sep(lines[i]):
                    rows.append(split_row(lines[i]))
                i += 1
            blocks.append(("table", rows))
            continue

        m = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)\s*$", stripped)
        if m:
            blocks.append(("image", m.group(1), m.group(2)))
            i += 1
            continue

        if re.fullmatch(r"-{3,}|\*{3,}", stripped):
            blocks.append(("hr",))
            i += 1
            continue

        if stripped.startswith(">"):
            quote = []
            while i < n and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip()[1:].strip())
                i += 1
            blocks.append(("quote", "".join(quote)))
            continue

        m = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", line)
        if m:
            indent = len(m.group(1))
            marker = m.group(2)
            content = [m.group(3)]
            i += 1
            while i < n:
                nxt = lines[i]
                if not nxt.strip():
                    break
                if re.match(r"^\s*([-*]|\d+\.)\s+", nxt) or nxt.lstrip().startswith(("|", "```", "#")):
                    break
                if len(nxt) - len(nxt.lstrip()) > indent:
                    content.append(nxt.strip())
                    i += 1
                else:
                    break
            ordered = marker[0].isdigit()
            blocks.append(("list", indent // 2, ordered, marker, "".join(content)))
            continue

        para = [stripped]
        i += 1
        while i < n:
            nxt = lines[i]
            if not nxt.strip():
                break
            ns = nxt.strip()
            if (ns.startswith(("```", "|", ">", "#")) or re.match(r"^([-*]|\d+\.)\s+", ns)
                    or re.fullmatch(r"-{3,}", ns)):
                break
            para.append(ns)
            i += 1
        blocks.append(("para", "".join(para)))

    return blocks


# ------------------------------------------------------------------ 行内格式
BOLD = re.compile(r"\*\*(.+?)\*\*")
CODE = re.compile(r"`([^`]+)`|\[([^\]]+)\]\(([^)]+)\)")


def add_segments(paragraph, text, size, color, bold, font=BODY_FONT):
    pos = 0
    for m in CODE.finditer(text):
        if m.start() > pos:
            r = paragraph.add_run(text[pos:m.start()])
            set_run_font(r, font, size, bold, color)
        if m.group(1) is not None:
            r = paragraph.add_run(m.group(1))
            set_run_font(r, CODE_FONT, max(size - 1, 7.5), bold, ACCENT)
        else:
            r = paragraph.add_run(m.group(2))
            set_run_font(r, font, size, bold, RGBColor(0x2F, 0x6F, 0x9F))
            r.underline = True
        pos = m.end()
    if pos < len(text):
        r = paragraph.add_run(text[pos:])
        set_run_font(r, font, size, bold, color)


def add_inline(paragraph, text, size=10.5, color=INK, bold=False, font=BODY_FONT):
    pos = 0
    for m in BOLD.finditer(text):
        if m.start() > pos:
            add_segments(paragraph, text[pos:m.start()], size, color, bold, font)
        add_segments(paragraph, m.group(1), size, color, True, font)
        pos = m.end()
    if pos < len(text):
        add_segments(paragraph, text[pos:], size, color, bold, font)
    return paragraph


# ------------------------------------------------------------------ 渲染
def build():
    text = open(SRC, encoding="utf-8").read()
    blocks = parse_blocks(text)

    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21), Cm(29.7)
    sec.left_margin = sec.right_margin = Cm(2.4)
    sec.top_margin = Cm(2.2)
    sec.bottom_margin = Cm(2.0)
    sec.header_distance = Cm(1.2)
    sec.footer_distance = Cm(1.2)
    sec.different_first_page_header_footer = True

    normal = doc.styles["Normal"]
    set_style_font(normal, BODY_FONT, 10.5, False, INK)
    normal.paragraph_format.line_spacing = 1.3
    normal.paragraph_format.space_after = Pt(4)

    for name, size, color, before, after in [
        ("Heading 1", 18, INK, 0, 12),
        ("Heading 2", 14, INK, 12, 6),
        ("Heading 3", 12, MUTED, 10, 4),
    ]:
        st = doc.styles[name]
        set_style_font(st, HEAD_FONT, size, True, color)
        st.paragraph_format.space_before = Pt(before)
        st.paragraph_format.space_after = Pt(after)
        st.paragraph_format.keep_with_next = True

    # 页眉页脚
    header = sec.header.paragraphs[0]
    header.paragraph_format.tab_stops.clear_all()
    header.paragraph_format.tab_stops.add_tab_stop(Cm(16.2), WD_TAB_ALIGNMENT.RIGHT)
    r = header.add_run("五笔练习（本地版）详细设计文档\t\tv1.3")
    set_run_font(r, HEAD_FONT, 8.5, False, RGBColor(0x8A, 0x80, 0x73))

    footer = sec.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = footer.add_run("第 ")
    set_run_font(r, BODY_FONT, 9, False, MUTED)
    add_page_field(footer)
    r = footer.add_run(" 页")
    set_run_font(r, BODY_FONT, 9, False, MUTED)

    # 封面
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(150)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("五笔练习 · 本地版")
    set_run_font(r, HEAD_FONT, 16, False, MUTED)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(10)
    r = p.add_run("详细设计文档")
    set_run_font(r, HEAD_FONT, 34, True, INK)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("86 版看图拆字 · 离线单页应用 · Python + SQLite + 原生前端")
    set_run_font(r, BODY_FONT, 11, False, MUTED)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(40)
    r = p.add_run("版本 1.3    2026-11-21")
    set_run_font(r, BODY_FONT, 10.5, False, MUTED)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("依据当前工作区代码与测试结果生成")
    set_run_font(r, BODY_FONT, 9.5, False, MUTED)

    doc.add_page_break()

    # 先收集目录项（章级）
    toc = [b[2] for b in blocks if b[0] == "heading" and b[1] == 2]
    body_started = False
    first_chapter = True

    for idx, block in enumerate(blocks):
        kind = block[0]

        if kind == "heading":
            level, title = block[1], block[2]
            if level == 1 and not body_started:
                continue  # 封面已用
            if level == 2:
                if not body_started:
                    # 文档信息之后插入目录
                    doc.add_page_break()
                    p = doc.add_paragraph()
                    p.paragraph_format.space_before = Pt(0)
                    p.paragraph_format.space_after = Pt(12)
                    r = p.add_run("目 录")
                    set_run_font(r, HEAD_FONT, 20, True, INK)

                    for t in toc:
                        tp = doc.add_paragraph()
                        tp.paragraph_format.space_after = Pt(5)
                        tp.paragraph_format.line_spacing = 1.15
                        add_inline(tp, t.replace("`", ""), 11, INK, True, HEAD_FONT)
                    doc.add_page_break()
                    body_started = True
                hp = doc.add_paragraph(style="Heading 1")
                if not first_chapter:
                    hp.paragraph_format.page_break_before = True
                add_inline(hp, title, 18, INK, True, HEAD_FONT)
                first_chapter = False
                continue
            if level == 3:
                hp = doc.add_paragraph(style="Heading 2")
                add_inline(hp, title, 14, INK, True, HEAD_FONT)
                continue
            if level == 4:
                hp = doc.add_paragraph(style="Heading 3")
                add_inline(hp, title, 12, MUTED, True, HEAD_FONT)
                continue
            continue

        if kind == "table":
            rows = block[1]
            if not rows:
                continue
            cols = max(len(r) for r in rows)
            table = doc.add_table(rows=0, cols=cols)
            table.alignment = WD_TABLE_ALIGNMENT.CENTER
            table.autofit = True
            set_table_borders(table)
            set_cell_margins(table)
            for ri, row in enumerate(rows):
                cells = table.add_row().cells
                trpr = table.rows[-1]._tr.get_or_add_trPr()
                nosplit = OxmlElement("w:cantSplit")
                trpr.append(nosplit)
                for ci in range(cols):
                    cell = cells[ci]
                    val = row[ci] if ci < len(row) else ""
                    cp = cell.paragraphs[0]
                    cp.paragraph_format.space_after = Pt(0)
                    cp.paragraph_format.line_spacing = 1.1
                    if ri == 0:
                        add_inline(cp, val, 9, INK, True)
                        shade_cell(cell, HEAD_FILL)
                    else:
                        add_inline(cp, val, 8.8, INK, False)
                        if ri % 2 == 0 and len(rows) > 6:
                            shade_cell(cell, ZEBRA_FILL)
            repeat_header(table.rows[0])
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(2)
            continue

        if kind == "code":
            lines = block[1]
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Cm(0.2)
            p.paragraph_format.right_indent = Cm(0.1)
            p.paragraph_format.space_before = Pt(3)
            p.paragraph_format.space_after = Pt(7)
            p.paragraph_format.line_spacing = 1.0
            if len(lines) <= 22:
                p.paragraph_format.keep_together = True
            shade(p, CODE_FILL)
            r = p.add_run("\n".join(lines))
            set_run_font(r, CODE_FONT, 8, False, RGBColor(0x2B, 0x26, 0x20))
            continue

        if kind == "list":
            _, level, ordered, marker, content = block
            p = doc.add_paragraph()
            indent = 0.7 + level * 0.6
            p.paragraph_format.left_indent = Cm(indent)
            p.paragraph_format.first_line_indent = Cm(-0.55)
            p.paragraph_format.space_after = Pt(3)
            p.paragraph_format.line_spacing = 1.3
            p.paragraph_format.tab_stops.add_tab_stop(Cm(indent))
            task = re.match(r"^\[([ xX])\]\s+(.*)$", content)
            if task:
                prefix = ("■" if task.group(1).lower() == "x" else "□") + "\t"
                content = task.group(2)
            else:
                prefix = (marker + "\t") if ordered else "•\t"
            r = p.add_run(prefix)
            set_run_font(r, BODY_FONT, 10.5, False, MUTED)
            add_inline(p, content, 10.5, INK)
            continue

        if kind == "quote":
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Cm(0.6)
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(6)
            shade(p, CODE_FILL)
            add_inline(p, block[1], 10, MUTED)
            continue

        if kind == "image":
            alt, rel = block[1], block[2]
            path = rel if os.path.isabs(rel) else os.path.join(os.path.dirname(SRC), rel)
            if os.path.isfile(path):
                doc.add_picture(path, width=Cm(16.0))
                cap = doc.add_paragraph()
                cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
                cap.paragraph_format.space_before = Pt(2)
                cap.paragraph_format.space_after = Pt(8)
                r = cap.add_run("图 1  " + (alt or "界面示例"))
                set_run_font(r, BODY_FONT, 9, False, MUTED)
            continue

        if kind == "hr":
            add_hr(doc)
            continue

        if kind == "para":
            p = doc.add_paragraph()
            p.paragraph_format.line_spacing = 1.3
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            add_inline(p, block[1], 10.5, INK)
            continue

    doc.core_properties.title = "五笔练习（本地版）详细设计文档"
    doc.core_properties.subject = "86 版五笔看图拆字本地练习工具"
    doc.core_properties.author = "五笔练习项目"
    doc.core_properties.comments = "依据当前代码生成，版本 1.3"
    doc.save(OUT)
    print("saved", OUT)
    print("paragraphs", len(doc.paragraphs), "tables", len(doc.tables),
          "images", len(doc.inline_shapes))


if __name__ == "__main__":
    build()
