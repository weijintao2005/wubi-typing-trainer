# -*- coding: utf-8 -*-
"""文章解析：txt / docx → 统一文档模型。

只处理文章练习需要的结构级排版：
- txt：编码检测、按行切分，保留空行/行首空格/制表符；
- docx：段落、运行样式、对齐/缩进/间距、标题、列表、表格、图片、分页。
不执行宏，不访问外部资源。
"""
import io
import os
import re
import zipfile

MAX_CHARS = 20000
MAX_DOCX_ENTRIES = 2000
MAX_DOCX_UNCOMPRESSED = 60 * 1024 * 1024
MAX_IMAGE_BYTES = 10 * 1024 * 1024
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff"}


class ParseError(ValueError):
    """用户可读的解析错误。"""


# ------------------------------------------------------------------ txt
def _decode_text(data):
    """返回 (text, encoding)。"""
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8", "replace"), "utf-8"
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        return data.decode("utf-16", "replace"), "utf-16"
    for enc in ("utf-8", "gb18030"):
        try:
            return data.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", "replace"), "utf-8"


def _txt_blocks(text):
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    blocks = []
    for line in lines:
        blocks.append({
            "type": "p",
            "preserve": True,
            "runs": [{"text": line}],
        })
    return blocks


# ------------------------------------------------------------------ docx
def _pt(value):
    if value is None:
        return 0
    try:
        return round(float(value.pt), 2)
    except Exception:
        return 0


def _alignment(value):
    if value is None:
        return "left"
    name = getattr(value, "name", "") or ""
    if "CENTER" in name:
        return "center"
    if "RIGHT" in name:
        return "right"
    if "JUSTIFY" in name or "DISTRIBUTE" in name:
        return "justify"
    return "left"


def _safe_ext(part):
    ext = os.path.splitext(str(part.partname))[1].lower()
    if ext == ".jpeg":
        ext = ".jpg"
    if ext in IMAGE_EXT:
        return ext
    ctype = (getattr(part, "content_type", "") or "").lower()
    for key, out in (("png", ".png"), ("jpeg", ".jpg"), ("gif", ".gif"),
                     ("webp", ".webp"), ("bmp", ".bmp"), ("tiff", ".tif")):
        if key in ctype:
            return out
    return None


def _image_width(run):
    try:
        ext = run._element.xpath(".//wp:extent")
        if ext:
            cx = int(ext[0].get("cx") or 0)
            if cx > 0:
                return max(40, min(1200, round(cx / 9525)))
    except Exception:
        pass
    return None


def _run_style(run):
    style = {}
    if run.bold:
        style["bold"] = True
    if run.italic:
        style["italic"] = True
    if run.underline:
        style["underline"] = True
    try:
        if run.font.size:
            style["size"] = round(float(run.font.size.pt), 2)
    except Exception:
        pass
    try:
        if run.font.name:
            style["font"] = str(run.font.name)
    except Exception:
        pass
    try:
        rgb = run.font.color.rgb
        if rgb:
            style["color"] = "#" + str(rgb)
    except Exception:
        pass
    return style


def _paragraph_block(p, doc, article_id, media_dir, media_url, counter):
    fmt = p.paragraph_format
    style_name = ""
    try:
        style_name = p.style.name or ""
    except Exception:
        pass
    block = {
        "type": "p",
        "align": _alignment(p.alignment),
        "runs": [],
    }
    if style_name and style_name.lower() != "normal":
        block["style"] = style_name
    if "Heading" in style_name or "标题" in style_name:
        block["heading"] = 1
        m = re.search(r"(\d+)", style_name)
        if m:
            block["heading"] = max(1, min(6, int(m.group(1))))
    if _pt(fmt.left_indent):
        block["indentLeft"] = _pt(fmt.left_indent)
    if _pt(fmt.right_indent):
        block["indentRight"] = _pt(fmt.right_indent)
    if fmt.first_line_indent is not None:
        block["indentFirst"] = _pt(fmt.first_line_indent)
    if _pt(fmt.space_before):
        block["spaceBefore"] = _pt(fmt.space_before)
    if _pt(fmt.space_after):
        block["spaceAfter"] = _pt(fmt.space_after)
    try:
        ls = fmt.line_spacing
        if isinstance(ls, float):
            block["lineHeight"] = round(ls, 2)
        elif ls is not None:
            block["lineHeightPt"] = _pt(ls)
    except Exception:
        pass

    # 列表：只区分项目符号/编号，不还原复杂编号
    try:
        numpr = p._p.pPr.numPr if p._p.pPr is not None else None
        if numpr is not None:
            block["list"] = "number" if ("Number" in style_name or "编号" in style_name) else "bullet"
            try:
                ilvl = p._p.pPr.numPr.ilvl
                if ilvl is not None and ilvl.val is not None:
                    block["listLevel"] = max(0, min(5, int(ilvl.val)))
            except Exception:
                pass
        elif "List" in style_name or "列表" in style_name:
            block["list"] = "number" if ("Number" in style_name or "编号" in style_name) else "bullet"
    except Exception:
        pass

    for run in p.runs:
        text = run.text or ""
        if text:
            item = {"text": text}
            item.update(_run_style(run))
            block["runs"].append(item)
        try:
            blips = run._element.xpath(".//a:blip")
        except Exception:
            blips = []
        for blip in blips:
            try:
                rid = blip.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed")
                if not rid:
                    continue
                part = doc.part.related_parts.get(rid)
                if part is None:
                    continue
                blob = part.blob
                if not blob or len(blob) > MAX_IMAGE_BYTES:
                    continue
                counter[0] += 1
                ext = _safe_ext(part)
                if not ext:
                    counter[0] -= 1
                    continue
                name = "image%d%s" % (counter[0], ext)
                os.makedirs(media_dir, exist_ok=True)
                with open(os.path.join(media_dir, name), "wb") as f:
                    f.write(blob)
                item = {"type": "image", "src": media_url + name}
                width = _image_width(run)
                if width:
                    item["width"] = width
                block["runs"].append(item)
            except Exception:
                continue

    if block["runs"]:
        run_text = "".join(r.get("text", "") for r in block["runs"] if r.get("type") != "image")
        if not run_text:
            try:
                fallback = p.text or ""
            except Exception:
                fallback = ""
            if fallback:
                block["runs"].append({"text": fallback})
        return block
    try:
        fallback = p.text or ""
    except Exception:
        fallback = ""
    if fallback:
        block["runs"].append({"text": fallback})
    return block


def _table_block(table, doc, article_id, media_dir, media_url, counter):
    rows = []
    for row in table.rows:
        cells = []
        for cell in row.cells:
            blocks = []
            for p in cell.paragraphs:
                blocks.append(_paragraph_block(p, doc, article_id, media_dir, media_url, counter))
            for nested in cell.tables:
                blocks.append(_table_block(nested, doc, article_id, media_dir, media_url, counter))
            cells.append({"blocks": blocks})
        rows.append(cells)
    return {"type": "table", "rows": rows}


def _docx_blocks(doc, article_id, media_dir, media_url):
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    blocks = []
    counter = [0]
    for child in doc.element.body.iterchildren():
        if child.tag == qn("w:p"):
            p = Paragraph(child, doc)
            try:
                if p.paragraph_format.page_break_before:
                    blocks.append({"type": "pageBreak"})
            except Exception:
                pass
            blocks.append(_paragraph_block(p, doc, article_id, media_dir, media_url, counter))
        elif child.tag == qn("w:tbl"):
            blocks.append(_table_block(Table(child, doc), doc, article_id, media_dir, media_url, counter))
    return blocks, counter[0]


def _count_chars(blocks):
    n = 0
    for b in blocks:
        if b.get("type") == "p":
            for r in b.get("runs", []):
                text = r.get("text")
                if text:
                    n += sum(1 for ch in text if ch not in "\n\r\t")
        elif b.get("type") == "table":
            for row in b.get("rows", []):
                for cell in row:
                    n += _count_chars(cell.get("blocks", []))
    return n


def _docx_title(doc, filename, blocks):
    try:
        title = (doc.core_properties.title or "").strip()
        if title:
            return title[:120]
    except Exception:
        pass
    for b in blocks:
        if b.get("type") != "p":
            continue
        text = "".join(r.get("text", "") for r in b.get("runs", [])).strip()
        if not text:
            continue
        if b.get("heading") or b.get("style") in ("Title", "标题"):
            return text[:120]
        break
    return re.sub(r"\.(txt|docx)$", "", filename, flags=re.I) or "未命名文章"


# ------------------------------------------------------------------ API
def parse_article(data, filename, article_id, media_root):
    """解析文章，返回 {title, kind, encoding, blocks, char_count, media_count}。"""
    lower = filename.lower()
    if lower.endswith(".txt"):
        kind = "txt"
    elif lower.endswith(".docx"):
        kind = "docx"
    else:
        raise ParseError("只支持 .txt 或 .docx 文件")

    media_dir = os.path.join(media_root, article_id)
    media_url = "/media/articles/%s/" % article_id

    if kind == "txt":
        text, encoding = _decode_text(data)
        blocks = _txt_blocks(text)
        count = _count_chars(blocks)
        if count > MAX_CHARS:
            raise ParseError("文章过长：%d 字，最多 %d 字" % (count, MAX_CHARS))
        if count == 0:
            raise ParseError("txt 没有可练习的文字")
        return {
            "title": re.sub(r"\.txt$", "", filename, flags=re.I) or "未命名文章",
            "kind": "txt", "encoding": encoding, "blocks": blocks,
            "char_count": count, "media_count": 0,
        }

    if not data.startswith(b"PK"):
        raise ParseError("docx 文件格式不正确（缺少 ZIP 文件头）")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            infos = z.infolist()
            if len(infos) > MAX_DOCX_ENTRIES:
                raise ParseError("docx 内部文件过多，已拒绝解析")
            total = sum(i.file_size for i in infos)
            if total > MAX_DOCX_UNCOMPRESSED:
                raise ParseError("docx 解压后过大，已拒绝解析")
            names = {i.filename for i in infos}
            if "word/document.xml" not in names:
                raise ParseError("docx 缺少正文 document.xml")
    except zipfile.BadZipFile:
        raise ParseError("docx 文件损坏或不是有效的 ZIP")
    except ParseError:
        raise
    except Exception:
        raise ParseError("docx 文件读取失败")

    try:
        from docx import Document
    except Exception:
        raise ParseError("服务端缺少 python-docx，无法解析 docx")

    try:
        doc = Document(io.BytesIO(data))
    except Exception:
        raise ParseError("docx 解析失败，请确认文件未损坏")

    blocks, media_count = _docx_blocks(doc, article_id, media_dir, media_url)
    count = _count_chars(blocks)
    if count > MAX_CHARS:
        raise ParseError("文章过长：%d 字，最多 %d 字" % (count, MAX_CHARS))
    if count == 0:
        raise ParseError("docx 没有可练习的文字")
    return {
        "title": _docx_title(doc, filename, blocks),
        "kind": "docx", "encoding": "", "blocks": blocks,
        "char_count": count, "media_count": media_count,
    }
