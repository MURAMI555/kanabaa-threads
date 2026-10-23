"""叶ばぁの文面チェック（MIKA-AI の .claude/skills/kanabaa/scripts/check_kinshi.py と同じ決まり）。
下書きに引っかかった所を一覧で返す。空なら OK。"""
import re

KINSHI = ["必ず", "絶対", "100%", "１００％", "当たります", "的中", "不幸にな", "奇跡", "余命", "鑑定歴",
          "銀座", "歌舞伎町", "No.1", "NO1", "ナンバーワン", "#副業", "Twitter",
          "先祖", "因縁", "呪", "24時間限定", "今だけ", "期間限定", "戻ってきます", "治る", "治り"]
KUCHO = {"「のよ」": r"のよ[。」\n]",
         "「視えた」の言い切り": r"視えた[。、」\n]",
         "「俺」": r"俺",
         "「あなた」": r"あなた",
         "です・ます": r"(です|ます|ました|ません)[。」\n]",
         "コロン": r"[:：]",
         "区切り線": r"^[-ー—=＝]{3,}\s*$"}
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿⭐⬆⤴⤵〰〽㊗㊙️]")


def check(text: str) -> list:
    hits = [f"禁止語「{w}」" for w in KINSHI if w in text]
    hits += [name for name, pat in KUCHO.items() if re.search(pat, text, re.M)]
    if EMOJI.search(text):
        hits.append("絵文字")
    if re.search(r"[０-９]", text):
        hits.append("全角数字")
    n = text.count("だがね")
    if n > 1:
        hits.append(f"「だがね」{n}回（1回まで）")
    return hits


CARE = re.compile(r"死にたい|消えたい|自殺|死のう|しにたい|きえたい|生きてる意味")


def needs_care(text: str) -> bool:
    """占わずに窓口を案内する相手か"""
    return bool(CARE.search(text or ""))
