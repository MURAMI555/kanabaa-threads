"""文の中から生年月日を拾って 8桁（YYYYMMDD）にする。出てきた順（本人→相手）。
19900503 / 1990/5/3 / 1990年5月3日 / 1990.5.3 / 平成2年5月3日 / H2.5.3 に対応。全角数字もOK。"""
import re
import unicodedata
from datetime import date

ERA = {"明治": 1867, "M": 1867, "大正": 1911, "T": 1911, "昭和": 1925, "S": 1925,
       "平成": 1988, "H": 1988, "令和": 2018, "R": 2018}
PATS = [
    re.compile(r"(?<!\d)((?:19|20)\d{2})(\d{2})(\d{2})(?!\d)"),
    re.compile(r"(?<!\d)((?:19|20)\d{2})\s*[/.\-年]\s*(\d{1,2})\s*[/.\-月]\s*(\d{1,2})"),
    re.compile(r"(明治|大正|昭和|平成|令和|[MTSHR])\s*(\d{1,2}|元)\s*[/.\-年]\s*(\d{1,2})\s*[/.\-月]\s*(\d{1,2})", re.I),
]


def find_dates(text: str) -> list:
    s = unicodedata.normalize("NFKC", text or "")
    found = []  # (位置, 8桁)
    for i, pat in enumerate(PATS):
        for m in pat.finditer(s):
            g = m.groups()
            try:
                if i < 2:
                    y, mo, d = int(g[0]), int(g[1]), int(g[2])
                else:
                    y = ERA[g[0].upper() if len(g[0]) == 1 else g[0]] + (1 if g[1] == "元" else int(g[1]))
                    mo, d = int(g[2]), int(g[3])
                dt = date(y, mo, d)
            except (ValueError, KeyError):
                continue
            if not (1920 <= dt.year <= date.today().year - 10):
                continue
            found.append((m.start(), dt.strftime("%Y%m%d")))
    out = []
    for _, v in sorted(found):
        if v not in out:
            out.append(v)
    return out
