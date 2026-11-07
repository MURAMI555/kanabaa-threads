"""叶ばぁの初視（無料鑑定書）の本文から、表紙つき・章立てのPDFを作る（2026/11/07〜）。
本文の文章は変えない。章の見出しを足すだけで、目印が見つからない章は見出しを付けずに前の章へ続ける（文章を落とさない）。
書体は Noto Serif JP（SIL Open Font License 1.1。ライセンスはフォントの中に入っている）を wght400 に固定したもの。
PDFは保存しない。開かれた時に本文から作る。"""
import functools
import io
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Flowable, Frame, KeepTogether, NextPageTemplate, PageBreak, PageTemplate,
                                Paragraph, Spacer, Table, TableStyle)
from xml.sax.saxutils import escape

HERE = Path(__file__).resolve().parent
FONT_PATH = HERE / "hatsumi_assets" / "NotoSerifJP-Regular.ttf"
FACE_PATH = HERE / "docs" / "kanabaa.jpg"
BG_PATH = HERE / "hatsumi_assets" / "cover_bg.jpg"
BG_SIZE = (1083, 1453)
FONT = "KanabaaSerif"
W, H = 148 * mm, 210 * mm
PAPER = HexColor("#fcf5ea")
DATE_INK = HexColor("#4a2f2a")
INK = HexColor("#26354a")
NAVY = HexColor("#1f3350")
RED = HexColor("#9e2f24")
GOLD = HexColor("#b08d45")
GRAY = HexColor("#7a7265")
BOX = HexColor("#fbf7ee")
BOX_LINE = HexColor("#cdbf9f")

BODY = ParagraphStyle("body", fontName=FONT, fontSize=12.5, leading=24, textColor=INK, wordWrap="CJK", spaceAfter=11)
BULLET = ParagraphStyle("bullet", parent=BODY, leftIndent=12.5, firstLineIndent=-12.5, spaceAfter=5)
KEY = ParagraphStyle("key", parent=BODY, fontSize=14, textColor=RED, alignment=TA_CENTER, spaceBefore=8, spaceAfter=18)
HEAD = ParagraphStyle("head", parent=BODY, fontSize=16.5, leading=25, textColor=NAVY, spaceAfter=0)
PRICE = ParagraphStyle("price", parent=BODY, fontSize=13.5, leading=25, textColor=RED, spaceAfter=10)
END = ParagraphStyle("end", parent=BODY, fontSize=13.5, leading=26, textColor=NAVY, alignment=TA_CENTER, spaceBefore=20)
KANJI = "〇一二三四五六七八九"
ROTATE = "ー―—–-〜~…‥（）()「」『』【】"
URL = re.compile(r"https?://\S+")
# (本文の目印, 章の名前, 章の名前と同じなら本文から消す行)
MARKS = [(re.compile(r"生まれの|生まれた"), "生まれ持ったもの", None),
         (re.compile(r"^こんな感覚"), "こんな感覚、ないかい", "こんな感覚、ないかい"),
         (re.compile(r"^ここだけは"), "ここだけは、ごまかさないでおくれ", "ここだけは、ごまかさないでおくれ"),
         (re.compile(r"本当に視るべき"), "本当に視るべきこと", None),
         (re.compile(r"^初視を受け取った"), "本鑑定を受けるなら", None)]


@functools.lru_cache(maxsize=1)
def _font():
    f = TTFont(FONT, str(FONT_PATH))
    pdfmetrics.registerFont(f)
    return f


def _clean(text: str) -> str:
    """書体に無い字（絵文字など）は四角にせず落とす"""
    have = _font().face.charToGlyph
    return "".join(c for c in text if c == "\n" or ord(c) in have or unicodedata.category(c) == "Zs")


def _kansu(n: int) -> str:
    if n < 10:
        return KANJI[n]
    tens, ones = divmod(n, 10)
    return ("" if tens == 1 else KANJI[tens]) + "十" + (KANJI[ones] if ones else "")


def wareki(d: str) -> str:
    t = datetime.strptime(d, "%Y%m%d")
    return f"令和{_kansu(t.year - 2018)}年{_kansu(t.month)}月{_kansu(t.day)}日"


def chapters(draft: str) -> list:
    """本文を [(章の名前, [段落…])] に分ける"""
    paras = [p.strip() for p in re.split(r"\n\s*\n", draft.replace("\r\n", "\n").strip()) if p.strip()]
    if paras and paras[0].startswith("【初視】") and "\n" not in paras[0]:
        paras = paras[1:]
    elif paras and paras[0].startswith("【初視】"):
        paras[0] = paras[0].split("\n", 1)[1]
    out = [("今の流れ", [])]
    at = 0
    for p in paras:
        for i in range(at, len(MARKS)):
            mark, title, strip = MARKS[i]
            if mark.search(p):
                out.append((title, []))
                at = i + 1
                if strip:
                    first, _, rest = p.partition("\n")
                    if first.rstrip("。").strip() == strip:
                        p = rest.strip()
                break
        if p:
            out[-1][1].append(p)
    return [c for c in out if c[1]]


class Button(Flowable):
    """押せるリンクのボタン"""

    def __init__(self, label, url, color, width):
        super().__init__()
        self.label, self.url, self.color, self.width = label, url, color, width
        self.fs = 11.5
        while pdfmetrics.stringWidth(label, FONT, self.fs) > width - 16 and self.fs > 8:
            self.fs -= 0.5
        self.height = 11 * mm

    def wrap(self, aw, ah):
        return self.width, self.height + 7

    def draw(self):
        c = self.canv
        c.setFillColor(self.color)
        c.roundRect(0, 7, self.width, self.height, 2 * mm, stroke=0, fill=1)
        c.setFillColor(HexColor("#fff8ea"))
        c.setFont(FONT, self.fs)
        c.drawCentredString(self.width / 2, 7 + self.height / 2 - self.fs * 0.36, self.label)
        c.linkURL(self.url, (0, 7, self.width, 7 + self.height), relative=1, thickness=0)


class Head(Flowable):
    """章の見出し（赤い漢数字＋名前＋金の線）"""

    def __init__(self, num, title, width):
        super().__init__()
        self.num, self.title, self.width = num, title, width

    def wrap(self, aw, ah):
        return self.width, 50

    def draw(self):
        c = self.canv
        c.setFont(FONT, 16.5)
        c.setFillColor(RED)
        c.drawString(0, 30, self.num)
        c.setFillColor(NAVY)
        c.drawString(27, 30, self.title)
        c.setStrokeColor(GOLD)
        c.setLineWidth(.85)
        c.line(0, 20, self.width, 20)


def _p(text: str, style) -> Paragraph:
    return Paragraph("<br/>".join(escape(x) for x in text.split("\n")), style)


def _flow_para(p: str, width: float) -> list:
    """段落1つ → Flowable。「・」の行はぶら下げ、URLの行はボタンにする"""
    lines = p.split("\n")
    out, buf = [], []

    def flush():
        if buf:
            s = END if "決めるのはあんた" in buf[0] else KEY if len(buf) == 1 and "はっきり視える" in buf[0] else BODY
            out.append(_p("\n".join(buf), s))
            buf.clear()

    for ln in lines:
        m = URL.fullmatch(ln.strip())
        if m:
            label = buf.pop() if buf else "ここを開いておくれ"
            flush()
            out.append(Button(label, m.group(0), RED if "stores" in m.group(0) else NAVY, width))
        elif ln.startswith("・"):
            flush()
            out.append(_p(ln, BULLET))
        else:
            buf.append(ln)
    flush()
    if out and isinstance(out[-1], Paragraph) and out[-1].style is BULLET:
        out.append(Spacer(1, 7))
    return out


def _box(flow: list, width: float) -> Table:
    t = Table([[flow]], colWidths=[width])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), BOX), ("BOX", (0, 0), (-1, -1), .8, BOX_LINE),
                           ("LEFTPADDING", (0, 0), (-1, -1), 14), ("RIGHTPADDING", (0, 0), (-1, -1), 14),
                           ("TOPPADDING", (0, 0), (-1, -1), 12), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    return t


def _story(draft: str, width: float) -> list:
    story, chs = [], chapters(draft)
    for i, (title, paras) in enumerate(chs):
        if i:
            story.append(PageBreak())
        story.append(Head(_kansu(i + 1), title, width))
        if title == "こんな感覚、ないかい":
            items = [f for p in paras[:1] for f in _flow_para(p, width - 28)]
            story.append(_box(items, width))
            story.append(Spacer(1, 12))
            paras = paras[1:]
        elif title == "本鑑定を受けるなら":
            # 料金の段と申し込みボタンを箱に入れる（ボタンの段まで）
            n = next((k for k, p in enumerate(paras) if URL.search(p)), None)
            if n is not None:
                last = n
                while last + 1 < len(paras) and URL.search(paras[last + 1]):
                    last += 1
                inner = []
                for k, p in enumerate(paras[:last + 1]):
                    inner += [_p(p, PRICE)] if not URL.search(p) else _flow_para(p, width - 28)
                story.append(_box(inner, width))
                story.append(Spacer(1, 14))
                paras = paras[last + 1:]
        j = 0
        while j < len(paras):
            p = paras[j]
            nxt = paras[j + 1] if j + 1 < len(paras) else ""
            if nxt.startswith("・") and "\n" not in p:  # 「本鑑定では、」と続く箇条書きは離さない
                story.append(KeepTogether(_flow_para(p, width) + _flow_para(nxt, width)))
                j += 2
                continue
            story += _flow_para(p, width)
            j += 1
    return story


def _vertical(c, x, top, text, size, gap, color):
    """1字ずつ縦に置く（x は字の中心・top は1字目の上端）"""
    c.setFillColor(color)
    c.setFont(FONT, size)
    y = top
    for ch in text:
        y -= size
        if ch in ROTATE:
            c.saveState()
            c.translate(x, y + size / 2)
            c.rotate(-90)
            c.drawCentredString(0, -size * .36, ch)
            c.restoreState()
        else:
            c.drawCentredString(x, y + size * .12, ch)
        y -= gap


def _cover(name: str, d: str):
    """表紙はみかちゃんのデザイン画像（名前と日付を消したもの）に、名前・日付・写真を重ねる。
    位置は画像の上のピクセルで指定する。左右の余白を少し切って A5 に合わせる"""
    s = H / BG_SIZE[1]
    ox = (W - BG_SIZE[0] * s) / 2
    px = lambda x: ox + x * s  # noqa: E731
    py = lambda y: H - y * s   # noqa: E731

    def draw(c, doc):
        c.saveState()
        c.drawImage(str(BG_PATH), ox, 0, BG_SIZE[0] * s, H)
        who = name + "さん"
        size = max(7, min(19, 432 * s / (1.42 * len(who))))  # 写真の輪にかからない長さに収める
        _vertical(c, px(413), py(258), who, size, size * .42, NAVY)
        _vertical(c, px(160), py(184), wareki(d), 10, 1.4, DATE_INK)
        # 写真（画像の金の輪の内側に丸く切り抜く）
        r = 181 * s
        cx, cy = px(520), py(865)
        path = c.beginPath()
        path.circle(cx, cy, r)
        c.clipPath(path, stroke=0, fill=0)
        c.drawImage(str(FACE_PATH), cx - r, cy - r, 2 * r, 2 * r)
        c.restoreState()
    return draw


def _inner(c, doc):
    c.saveState()
    c.setFillColor(PAPER)
    c.rect(0, 0, W, H, stroke=0, fill=1)
    c.setFillColor(GRAY)
    c.setFont(FONT, 9)
    c.drawCentredString(W / 2, 9 * mm, str(doc.page))
    c.restoreState()


@functools.lru_cache(maxsize=8)
def render(draft: str, name: str, d: str) -> bytes:
    """本文・呼び名・初視を送る日（YYYYMMDD）→ PDF"""
    _font()
    draft, name = _clean(draft), _clean(name).strip() or "あんた"
    if not any(c.isalnum() for c in draft):
        raise ValueError("本文が空")
    buf = io.BytesIO()
    fw, fh = W - 28 * mm, H - 33 * mm
    doc = BaseDocTemplate(buf, pagesize=(W, H), title="初視", author="叶ばぁ", subject="", creator="", producer="")
    doc.addPageTemplates([
        PageTemplate(id="cover", frames=[Frame(14 * mm, 16 * mm, fw, fh, 0, 0, 0, 0)], onPage=_cover(name, d)),
        PageTemplate(id="inner", frames=[Frame(14 * mm, 16 * mm, fw, fh, 0, 0, 0, 0)], onPage=_inner)])
    doc.build([NextPageTemplate("inner"), PageBreak()] + _story(draft, fw))
    return buf.getvalue()
