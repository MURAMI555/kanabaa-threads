"""叶ばぁの「置かせる」投稿へのコメントに、自然な間をあけて自動で返す（2026/10/28 みかちゃん指示・本部OK）。

受付箱（inbox_kit）と違って AI もデータ置き場も使わない。返信は型から組み立てる（同じ文の使い回しにならないよう、言い回しを人ごとに選ぶ）。
・対象：叶ばぁの直近48時間の投稿のうち「置いていきな」を含むもの（生年月日 / 出会った月）
・返すのは、投稿に直接ついたコメントで、まだ叶ばぁが返していないものだけ（手で返した分も API で見えるので二重にならない）
・自然な間：コメントから 15〜70分（人ごとにばらす）たってから。朝8時〜夜0時だけ。夜中のコメントは朝に返す
・1回（10分ごと）に2件まで、1件ごとに40〜120秒あける。コメントから48時間を過ぎたものは返さない
・文面は kinshi.check を通ったものだけ。読めないコメント（数字が無い等）は返さず、/autoreply に残す
止めるときは Render の環境変数 KANABAA_AUTOREPLY=0。"""
import os
import random
import re
import time
import unicodedata
from datetime import date, datetime, timedelta

import pytz
from flask import Blueprint

import threads_api
from inbox_kit import hizuke, kinshi, seinen

JST = pytz.timezone("Asia/Tokyo")
ACCOUNT = "kanabaa"
PER_RUN = 2
HOURS = (8, 24)  # 返してよい時間帯（JST の時）
bp = Blueprint("autoreply", __name__)
_log: list = []
_done: set = set()      # このプロセスで返したコメントID（API の反映待ちの間の二重防止）
_fail: dict = {}        # コメントID → 失敗回数（2回でやめる）
_skip: dict = {}        # コメントID → 返さなかった理由（/autoreply で見る）


def _note(msg: str):
    _log.append(f"{datetime.now(JST).strftime('%m/%d %H:%M')} {msg}")
    del _log[:-200]
    print("[autoreply] " + msg, flush=True)


def enabled() -> bool:
    return os.environ.get("KANABAA_AUTOREPLY", "1") != "0" and threads_api.configured(ACCOUNT)


# ---------- 文面 ----------

HEAD = ["{n}さん、置いてくれてありがとね。", "{n}さん、置いてくれてありがとね。ちゃんと視たよ。"]
TEASE = [
    "……それとね、ひとつ視えたものがある。悪い話じゃないよ。ただ、人の目がある所で書くことじゃないね。",
    "……それとね、もうひとつ視えたものがある。責める話じゃないよ。ただ、ここで書くには少し込み入ってるね。",
    "……それとね、ひとつ視えたものがある。悪い話じゃないよ。ただ、表で書くことじゃないね。",
    "……それとね、あんたの相手のことで、ひとつ視えたものがある。責める話じゃないよ。ただ、人の目がある所で言うことじゃないね。",
    "……それとね、もうひとつ視えたものがある。悪い話じゃないよ。ただ、ここで書くには少し深いね。",
    "……それとね、あんたの周りのことで、ひとつ視えたものがある。悪い話じゃないよ。ただ、ここで書くことじゃないね。",
]

HITO = {1: "自分で道を切り開く人", 2: "相手の気持ちを先に汲む人", 3: "明るさで人を惹きつける人",
        4: "約束を大事に積み上げる人", 5: "縛られると息が詰まる人", 6: "情が深くて、つい人の世話を先に焼く人",
        7: "じっくり考えて、本音をなかなか見せない人", 8: "物事を現実的に回せる人", 9: "尽くすほど自分を後回しにする人",
        11: "勘が鋭いのに、確かめてからじゃないと動けない人", 22: "責任を一人で背負いやすい人",
        33: "人を包むのが上手なぶん、自分が甘えるのは下手な人"}
HI = {1: ("始める日", ["迷ってた一通は、その日に送ってみな。", "考えすぎる前に、小さく一つ動きな。",
                     "誰かのためじゃなく、自分の用事から始めな。", "言いそびれてたことを、一つだけ口にしてみな。"]),
      8: ("決める日", ["決めかねてたことに、その日で答えを出しな。", "それまでは胸の内を整えておきな。",
                     "先延ばしにしてたことを、一つだけ片づけな。"]),
      11: ("勘の日", ["最初に浮かんだほうを選びな。", "頭より先に動いた気持ちを信じてみな。"]),
      5: ("変える日", ["続けてきたことを一つ、やり方だけ変えてみな。", "いつもと違う道を一本選んでみな。"])}
GOBI = ["だよ。", "だがね。"]


def _pday(s: str, d: date) -> int:
    n = sum(int(c) for c in f"{seinen.personal(s, d.year, d.month)}{d.day}")
    while n > 9 and n != 11:
        n = sum(int(c) for c in str(n))
    return n


def ugoku(s: str, today: date):
    """明日から7日のうちの動いていい日。1→8→11→5 の順で探す。(日付, 種類)"""
    days = [today + timedelta(days=i) for i in range(1, 8)]
    for want in (1, 8, 11, 5):
        for d in days:
            if _pday(s, d) == want:
                return d, want
    return days[0], 5


def name_of(username: str) -> str:
    n = re.split(r"[.]", username)[0].rstrip("_0123456789") or username
    h = len(n) // 2
    if len(n) >= 8 and n[:h] == n[h:]:
        n = n[:h]
    return n


def birth_reply(username: str, s: str, today: date, rnd: random.Random) -> str:
    d, kind = ugoku(s, today)
    name, _ = seinen.zodiac(date(int(s[:4]), int(s[4:6]), int(s[6:8])))
    lp = seinen.life_path(s)
    label, advice = HI[kind]
    next_week = d - timedelta(days=d.weekday()) > today - timedelta(days=today.weekday())
    when = f"{'来週' if next_week else ''}{d.day}日の{seinen.YOUBI[d.weekday()]}曜"
    lines = [rnd.choice(HEAD).format(n=name_of(username)),
             f"あんたが動いていいのは、{when}。",
             f"{name}で{lp}の人は、{HITO[lp]}{rnd.choice(GOBI)}{seinen.YOUBI[d.weekday()]}曜は「{label}」の巡り。{rnd.choice(advice)}",
             rnd.choice(TEASE)]
    return "\n".join(lines)


TSUKI = {
    1: "1月の縁は、始まりの縁。どちらかが手を引いて進む流れだよ。",
    2: "2月に出会った2人は、言葉より空気で分かり合う流れ。そのぶん、言わないことが溜まりやすい。",
    3: "3月の縁は、話して笑って近づく流れ。楽しい時は早いけど、真面目な話を後回しにしがちだね。",
    4: "4月に出会った2人は、ゆっくり積み上げる流れ。急には進まないぶん、崩れにくい縁だよ。",
    5: "5月に出会った2人は、会うたびに何か新しいことが起きる流れ。退屈はしないけど、落ち着く前に次の動きが入りやすいんだよ。",
    6: "6月の縁は、情で結ばれる流れ。相手の世話を焼くほど、自分の気持ちを言いそびれやすい。",
    7: "7月に出会った2人は、近いようで少し距離のある流れ。一人の時間を許し合えるかが分かれ目だね。",
    8: "8月の縁は、暮らしの事情が動かす流れ。仕事や住まいで、距離が変わりやすいんだよ。",
    9: "9月に出会った2人は、何かを手放した後に深まる流れ。区切りと始まりが重なる縁だね。",
    10: "10月の縁は、どちらが先に動くかで先が決まる流れ。待ち合いになると止まりやすいよ。",
    11: "11月に出会った2人は、気持ちが通じるのが早い。そのぶん、近づいたり離れたりの波も大きい流れだよ。",
    12: "12月に出会った2人は、振り返る時間の多い流れ。思い出が濃いぶん、過去に引っ張られやすいね。",
}
IMA = ["今のあんたは、相手の出方を待ってるように視えるね。", "今のあんたは、言いたいことを飲み込んでるように視える。",
       "今のあんたは、気持ちが少し先に行ってるように視えるね。", "今は、波の引いてるところに視える。引いてる時に追うと、相手は余計に遠くなるからね。"]


def month_reply(username: str, m: int, rnd: random.Random) -> str:
    return "\n".join([rnd.choice(HEAD).format(n=name_of(username)), TSUKI[m], rnd.choice(IMA), rnd.choice(TEASE)])


def make_reply(username: str, comment: str, post_text: str, today: date, seed: str):
    """(文面 or None, 読めなかった理由)"""
    rnd = random.Random(seed)
    if kinshi.needs_care(comment):
        return None, "気持ちが重い言葉あり（手で）"
    if "生年月日" in post_text:
        ds = hizuke.find_dates(comment)
        return (birth_reply(username, ds[0], today, rnd), "") if ds else (None, "生年月日が読めない")
    if "出会った月" in post_text:
        s = unicodedata.normalize("NFKC", comment)
        nums = [int(x) for x in re.findall(r"(?<!\d)(\d{1,2})(?!\d)", s) if 1 <= int(x) <= 12]
        return (month_reply(username, nums[0], rnd), "") if len(set(nums)) == 1 else (None, "月が読めない")
    return None, "型のない投稿"


# ---------- 回す ----------

def _ts(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z")


def _delay(cid: str) -> timedelta:
    return timedelta(minutes=random.Random("d" + cid).randint(15, 70))


def candidates(now: datetime) -> list:
    """返す候補 [(コメント, 投稿の文)]。古い順"""
    out = []
    for p in threads_api.my_posts(limit=25, account=ACCOUNT):
        text = p.get("text") or ""
        if "置いていきな" not in text or now - _ts(p["timestamp"]) > timedelta(hours=48):
            continue
        conv = threads_api.conversation(p["id"], account=ACCOUNT)
        answered = {(c.get("replied_to") or {}).get("id") for c in conv if c.get("is_reply_owned_by_me")}
        for c in conv:
            if c.get("is_reply_owned_by_me") or (c.get("replied_to") or {}).get("id") != p["id"]:
                continue
            if c["id"] in answered or c["id"] in _done or _fail.get(c["id"], 0) >= 2 or c.get("hide_status") in ("HIDDEN", "COVERED", "BLOCKED", "RESTRICTED"):
                continue
            if now - _ts(c["timestamp"]) > timedelta(hours=48):
                continue
            out.append((c, text))
    return sorted(out, key=lambda x: x[0]["timestamp"])


def job():
    if not enabled():
        return
    now = datetime.now(JST)
    if not (HOURS[0] <= now.hour < HOURS[1]):
        return
    try:
        cands = candidates(now)
    except Exception as e:
        _note(f"コメントの取得に失敗: {e}")
        return
    sent = 0
    for c, post_text in cands:
        if sent >= PER_RUN:
            break
        if now < _ts(c["timestamp"]) + _delay(c["id"]):
            continue
        text, why = make_reply(c.get("username", ""), c.get("text", ""), post_text, now.date(), c["id"])
        if text and kinshi.check(text):
            text, why = None, "チェックに引っかかった " + " / ".join(kinshi.check(text))
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
            sent += 1
            _note(f"@{c.get('username')} に返した\n{text}")
        except Exception as e:
            _fail[c["id"]] = _fail.get(c["id"], 0) + 1
            body = getattr(getattr(e, "response", None), "text", "")[:300]
            _note(f"@{c.get('username')} への返信に失敗（{_fail[c['id']]}回目）: {e} {body}")


@bp.get("/autoreply")
def page():
    rows = "\n".join(reversed(_log)) or "（まだ何もしていない）"
    state = "動いている" if enabled() else "止まっている（KANABAA_AUTOREPLY=0 かトークン無し）"
    return f"<pre style='white-space:pre-wrap;font-size:13px'>叶ばぁ 自動返信：{state}\n朝{HOURS[0]}時〜夜0時・コメントから15〜70分後・1回{PER_RUN}件まで\n\n{rows}</pre>"
