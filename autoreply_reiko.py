"""麗子の「夜のカウンター」投稿へのコメントに、夜だけ自動で返す（2026/10/29 みかちゃん「いいね」）。

叶ばぁの autoreply.py と同じ回し方で、文面と時間帯だけ麗子用。
・対象：麗子の直近48時間の投稿のうち「0時で閉店」を含むもの（彼の星座か誕生日の月日、分からなければアナタの星座を置かせる）
・返すのは、投稿に直接ついたコメントで、まだ麗子が返していないものだけ
・返すのは21時〜深夜0時59分だけ。コメントから 8〜15分あける（11/06。鑑定の場所を聞いてきた2往復目は次の見回りで）
・0時の閉店後に来たコメント・返しきれなかった分は、次の夜21時からの開店で「ゆうべは閉店のあとに…」と添えて返す
・麗子の返信に返してくれた人（2往復目）にも1人1回だけ返す。続きを聞きたい人はLINEへ案内（11/06）
・1回（10分ごと）に4件まで、1件ごとに40〜120秒あける
・コメントごとに tarot_reiko で本当に1枚引いて返す（11/06）
・星座の名前・月日（3/14・3月14日）・数字4桁（0314・10/31〜）・生年月日を読む。「私」「自分」などがあればアナタの星座、
  数字だけなら投稿が聞いた側（「アナタの誕生日を」の夜はアナタ、ほかは彼）として返す
・文面は禁止語チェック（麗子は「のよ」「です・ます」OKなので語だけ）を通ったものだけ。読めないコメントは返さず /autoreply/reiko に残す
止めるときは Render の環境変数 REIKO_AUTOREPLY=0。"""
import os
import random
import re
import time
import unicodedata
from datetime import date, datetime, timedelta

from flask import Blueprint

import tarot_reiko
import threads_api
from autoreply import JST, SOTCHI_RE, THANKS_RE, ZOKU_RE, _ts, name_of, pick
from inbox_kit import hizuke, kinshi, seinen

ACCOUNT = "reiko"
MARK = "0時で閉店"
PER_RUN = 4  # 10分ごとの見回りで4件まで（11/06）
bp = Blueprint("autoreply_reiko", __name__)
_log: list = []
_done: set = set()
_fail: dict = {}
_skip: dict = {}


def _note(msg: str):
    _log.append(f"{datetime.now(JST).strftime('%m/%d %H:%M')} {msg}")
    del _log[:-200]
    print("[autoreply_reiko] " + msg, flush=True)


def enabled() -> bool:
    return os.environ.get("REIKO_AUTOREPLY", "1") != "0" and threads_api.configured(ACCOUNT)


def check(text: str) -> list:
    """麗子用：禁止語・絵文字・全角数字だけ見る（口調は叶ばぁ用なので見ない）"""
    hits = [f"禁止語「{w}」" for w in kinshi.KINSHI if w in text]
    if kinshi.EMOJI.search(text):
        hits.append("絵文字")
    if re.search(r"[０-９]", text):
        hits.append("全角数字")
    return hits


# ---------- 星座を読む ----------

SIGNS = ["牡羊座", "牡牛座", "双子座", "蟹座", "獅子座", "乙女座", "天秤座", "蠍座", "射手座", "山羊座", "水瓶座", "魚座"]
ALIAS = {  # 座が無くても読めるのは取り違えにくい漢字だけ。ひらがな・1字の漢字は「座」つきのみ
    "牡羊座": ["牡羊", "おひつじ座", "おひつじざ"], "牡牛座": ["牡牛", "おうし座", "おうしざ"],
    "双子座": ["双子", "ふたご座", "ふたござ"], "蟹座": ["蟹座", "かに座", "かにざ"],
    "獅子座": ["獅子", "しし座", "ししざ"], "乙女座": ["乙女", "おとめ座", "おとめざ"],
    "天秤座": ["天秤", "てんびん座", "てんびんざ"], "蠍座": ["蠍座", "さそり座", "さそりざ"],
    "射手座": ["射手", "いて座", "いてざ"], "山羊座": ["山羊", "やぎ座", "やぎざ"],
    "水瓶座": ["水瓶", "みずがめ座", "みずがめざ"], "魚座": ["魚座", "うお座", "うおざ"],
}
SELF = re.compile(r"私|わたし|ワタシ|あたし|アタシ|自分|じぶん|うち(?!の彼)|僕|ぼく")
HIM = re.compile(r"彼|かれ|相手|あいて|旦那|夫|好きな人|すきな人")


def sign_of(m: int, d: int) -> str:
    return seinen.zodiac(date(2000, m, d))[0]


def read_comment(comment: str, default_who: str = "him"):
    """(星座, 月日の言い直し or "", 誰の星座 'him'/'me') か None。default_who＝投稿が誰の誕生日を聞いたか"""
    s = unicodedata.normalize("NFKC", comment or "")
    who = "me" if SELF.search(s) and not HIM.search(s) else "him" if HIM.search(s) else default_who
    hits = [sg for sg, words in ALIAS.items() if any(w in s for w in words)]
    if len(hits) == 1:
        return hits[0], "", who
    if len(hits) > 1:  # 「彼は山羊座、私は蟹座」→ 彼のほうで返す
        for part in re.split(r"[、,。\n/／ ]", s):
            got = [sg for sg, words in ALIAS.items() if any(w in part for w in words)]
            if HIM.search(part) and len(got) == 1:
                return got[0], "", "him"
        return None
    full = hizuke.find_dates(s)
    if full:
        m, d = int(full[0][4:6]), int(full[0][6:8])
        return sign_of(m, d), f"{m}月{d}日", who
    md = re.findall(r"(?<!\d)(\d{1,2})\s*(?:/|月|\.)\s*(\d{1,2})(?!\d)", s)
    md = {(int(m), int(d)) for m, d in md}
    if len(md) == 1:
        m, d = md.pop()
        try:
            return sign_of(m, d), f"{m}月{d}日", who
        except ValueError:
            return None
    # 「1103」「0314」「314」＝数字4桁の置かせ（10/31〜）。3桁は 111（1/11 か 11/1）のように両方読めるものは読まない
    ok = set()
    for x in re.findall(r"(?<!\d)(\d{3,4})(?!\d)", s):
        cuts = [(x[:2], x[2:])] if len(x) == 4 else [(x[:1], x[1:]), (x[:2], x[2:])]
        for m, d in cuts:
            try:
                sign_of(int(m), int(d))
                ok.add((int(m), int(d)))
            except ValueError:
                pass
    if len(ok) == 1:
        m, d = ok.pop()
        return sign_of(m, d), f"{m}月{d}日", who
    return None


# ---------- 文面 ----------

HEAD = ["{n}ちゃん、いらっしゃい。", "{n}ちゃん、いらっしゃい。置いてってくれてありがと。", "あら{n}ちゃん、いらっしゃい。"]
# 全部、無料のタロット鑑定とLINEの案内にする（11/06 売れてるオネエ占い師の直球の案内に寄せた）
CLOSE = ["ここで引いたのは1枚だけ。無料のタロット鑑定では、彼とアナタの両方を読むわ。プロフィールのリンクからLINEしなさい。",
         "彼とのこと、もっとズバッと聞きたければ、プロフィールのリンクからLINEしてちょうだい。初回のタロット鑑定は無料よ。",
         "初回のタロット鑑定は無料。プロフィールのリンクからいらっしゃい。カードに出たことを、そのまま言うわ。",
         "遠慮はいらないわ。無料のタロット鑑定は、プロフィールのリンクからLINEでね。",
         "ひとりで抱えてる夜は、プロフィールのリンクからLINEしなさい。初回のタロット鑑定は無料よ。",
         "彼の今をカードで見たい子は、プロフィールのリンクからLINEしてちょうだい。初回は無料よ。"]

# 2往復目（麗子の返信に、さらに返してくれた人）。1人1回だけ（11/06）
Z_LINE = ["{n}ちゃん、プロフィールのリンクからLINEしなさい。届いた質問に4つ答えてくれたら、タロットを切るわ。初回は無料よ。",
          "{n}ちゃん、いらっしゃい。無料のタロット鑑定はLINEでやってるの。プロフィールのリンクから追加してちょうだい。",
          "聞きたいのね、{n}ちゃん。プロフィールのリンクからLINEして、4つの質問に答えてちょうだい。カードに出たことを、そのまま言うわ。"]
Z_SOTCHI = ["{n}ちゃん、LINEありがとう。届いた順に読むから、いい子で待ってなさい。",
            "{n}ちゃん、ちゃんと受け取ってるわよ。順番が来たら、カードを切るわね。"]
Z_THANKS = ["どういたしまして、{n}ちゃん。また夜に来なさいね。",
            "{n}ちゃん、ありがと。今夜は早く寝なさいね。",
            "{n}ちゃん、そう言ってもらえると嬉しいわ。また開店の夜にね。"]
Z_STORY = ["{n}ちゃん、話してくれてありがと。ここじゃ書ききれない話ね。プロフィールのリンクからLINEしなさい。初回のタロット鑑定は無料よ。",
           "{n}ちゃん、よく言えたわね。その話、ちゃんと聞かせてちょうだい。プロフィールのリンクからLINEで待ってるわ。初回は無料よ。"]
Z_SHORT = ["{n}ちゃん、来てくれてありがと。また夜にね。",
           "{n}ちゃん、思い当たるなら、それで十分よ。"]

LATE = ["ゆうべは閉店のあとに来てくれたのね。今夜いちばんに読むわ。",
        "閉めたあとに置いてってくれたのね。今夜の開店一番で読むわよ。"]


def post_who(post_text: str) -> str:
    """投稿が誰の誕生日を聞いたか（「アナタの誕生日を」の夜は数字だけのコメントをアナタの星座として読む）"""
    return "me" if re.search(r"アナタの誕生日[、,を]", post_text) and "彼の誕生日" not in post_text else "him"


def make_reply(username: str, comment: str, seed: str, used=(), late=False, who="him"):
    """(文面 or None, 読めなかった理由)"""
    rnd = random.Random(seed)
    if kinshi.needs_care(comment):
        return None, "気持ちが重い言葉あり（手で）"
    got = read_comment(comment, who)
    if not got:
        return None, "星座も月日も読めない"
    sign, md, who = got
    n = re.sub(r"[_.]?(chan|chang|tyan)$", "", name_of(username), flags=re.I) or name_of(username)
    lines = [pick(HEAD, used, rnd).format(n=n)]
    if late:
        lines.append(pick(LATE, used, rnd))
    sub = "アナタ" if who == "me" else "彼"
    lines.append(f"{md}生まれなら、{sign}ね。" if md else f"{sign}の{sub}ね。")
    card, pos, meaning = tarot_reiko.draw()  # 本当に1枚引く（11/06 みかちゃん「タロットで見た形に」）
    lines.append(f"{sub}に1枚引いたわ。出たのは{card}の{pos}。")
    lines.append(f"タロットで見ると、{sub}は今、{meaning}。")
    lines.append(pick(CLOSE, used, rnd))
    return "\n".join(lines), ""


def second_reply(username: str, comment: str, seed: str, used=()):
    """(文面 or None, 理由, すぐ返すか)。麗子の返信への返事"""
    rnd = random.Random("2" + seed)
    n = re.sub(r"[_.]?(chan|chang|tyan)$", "", name_of(username), flags=re.I) or name_of(username)
    if kinshi.needs_care(comment):
        return None, "気持ちが重い言葉あり（手で）", False
    s = re.sub(r"\s", "", unicodedata.normalize("NFKC", comment or ""))
    if not s:
        return None, "中身が無い（スタンプだけ等）", False
    if ZOKU_RE.search(s) and not re.search(r"送りました|送らせて|登録しました|追加しました", s):
        return pick(Z_LINE, used, rnd).format(n=n), "", True
    if SOTCHI_RE.search(s):
        return pick(Z_SOTCHI, used, rnd).format(n=n), "", False
    if len(s) <= 40 and THANKS_RE.search(s):
        return pick(Z_THANKS, used, rnd).format(n=n), "", False
    if len(s) >= 10:
        return pick(Z_STORY, used, rnd).format(n=n), "", False
    return pick(Z_SHORT, used, rnd).format(n=n), "", False


# ---------- 回す ----------

def _closing(post_ts: datetime) -> datetime:
    """その投稿の夜の閉店時刻（投稿した日の翌0時。0時台の投稿ならその日の朝1時まで）"""
    p = post_ts.astimezone(JST)
    if p.hour < 1:
        return p.replace(hour=1, minute=0, second=0, microsecond=0)
    return (p + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


def open_now(now: datetime) -> bool:
    return now.hour >= 21 or now.hour < 1


def candidates(now: datetime) -> list:
    out = []
    for p in threads_api.my_posts(limit=25, account=ACCOUNT):
        text = p.get("text") or ""
        if MARK not in text or now - _ts(p["timestamp"]) > timedelta(hours=48):
            continue
        close = _closing(_ts(p["timestamp"]))
        conv = threads_api.conversation(p["id"], account=ACCOUNT)
        mine = {c["id"]: c for c in conv if c.get("is_reply_owned_by_me")}
        byid = {c["id"]: c for c in conv}
        answered = {(c.get("replied_to") or {}).get("id") for c in mine.values()}
        used = [c.get("text") or "" for c in mine.values()]
        second_done = set()  # 2往復目にもう返した人
        for m in mine.values():
            to = byid.get((m.get("replied_to") or {}).get("id")) or {}
            if (to.get("replied_to") or {}).get("id") not in (None, p["id"]):
                second_done.add(to.get("username"))
        for c in conv:
            parent = (c.get("replied_to") or {}).get("id")
            if c.get("is_reply_owned_by_me"):
                continue
            second = parent in mine
            if parent != p["id"] and not second:
                continue
            if second and c.get("username") in second_done:
                continue
            if c["id"] in answered or c["id"] in _done or _fail.get(c["id"], 0) >= 2 or c.get("hide_status") in ("HIDDEN", "COVERED", "BLOCKED", "RESTRICTED"):
                continue
            out.append((c, used, _ts(c["timestamp"]) >= close or now >= close + timedelta(hours=1), post_who(text), second))  # 次の夜に回った分
    return sorted(out, key=lambda x: x[0]["timestamp"])


def _delay(cid: str, quick: bool = False) -> timedelta:
    if quick:  # 鑑定の場所を聞いてきた人は、次の見回りで返す
        return timedelta(0)
    return timedelta(minutes=random.Random("r" + cid).randint(8, 15))  # 11/06 15〜70分から短くした


def job(rush: bool = False):
    if not enabled():
        return
    now = datetime.now(JST)
    if not rush and not open_now(now):
        return
    try:
        cands = candidates(now)
    except Exception as e:
        _note(f"コメントの取得に失敗: {e}")
        return
    sent = 0
    for c, used, late, who, second in cands:
        if sent >= (20 if rush else PER_RUN):
            break
        quick = False
        if second:
            text, why, quick = second_reply(c.get("username", ""), c.get("text", ""), c["id"], used)
        if not rush and now < _ts(c["timestamp"]) + _delay(c["id"], quick):
            continue
        if not second:  # 札は返す時に引く（待っている間に引き直さない）
            text, why = make_reply(c.get("username", ""), c.get("text", ""), c["id"], used, late, who)
        if text and check(text):
            text, why = None, "チェックに引っかかった " + " / ".join(check(text))
        if not text:
            if c["id"] not in _skip:
                _note(f"@{c.get('username')}「{(c.get('text') or '')[:20]}」は返さない（{why}）")
            _skip[c["id"]] = why
            continue
        if sent:
            time.sleep(random.randint(40, 120))
        try:
            threads_api.post(text, reply_to_id=c["id"], account=ACCOUNT)
            _done.add(c["id"])
            used.append(text)
            sent += 1
            _note(f"@{c.get('username')} に返した\n{text}")
        except Exception as e:
            _fail[c["id"]] = _fail.get(c["id"], 0) + 1
            body = getattr(getattr(e, "response", None), "text", "")[:300]
            _note(f"@{c.get('username')} への返信に失敗（{_fail[c['id']]}回目）: {e} {body}")


@bp.get("/autoreply/reiko")
def page():
    from flask import request
    if request.args.get("rush") == "1019":
        import threading
        threading.Thread(target=job, kwargs={"rush": True}, daemon=True).start()
        _note("今いる分を全部返す（みかちゃん指示）")
        return "<pre>今いる分を順番に返しはじめた。数分後に /autoreply/reiko を見てね</pre>"
    rows = "\n".join(reversed(_log)) or "（まだ何もしていない）"
    state = "動いている" if enabled() else "止まっている（REIKO_AUTOREPLY=0 かトークン無し）"
    return f"<pre style='white-space:pre-wrap;font-size:13px'>麗子 自動返信：{state}\n夜21時〜0時台・コメントから8〜15分後・2往復目も1回・閉店後の分は次の夜・1回{PER_RUN}件まで\n\n{rows}</pre>"
