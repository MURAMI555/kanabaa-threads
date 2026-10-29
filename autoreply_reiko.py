"""麗子の「夜のカウンター」投稿へのコメントに、夜だけ自動で返す（2026/10/29 みかちゃん「いいね」）。

叶ばぁの autoreply.py と同じ回し方で、文面と時間帯だけ麗子用。
・対象：麗子の直近48時間の投稿のうち「0時で閉店」を含むもの（彼の星座か誕生日の月日、分からなければアナタの星座を置かせる）
・返すのは、投稿に直接ついたコメントで、まだ麗子が返していないものだけ
・閉店の約束どおり、投稿した夜の0時までに来たコメントだけ。返すのは21時〜深夜0時59分（0時直前の分を返しきるため）
・自然な間：コメントから 10〜40分。1回（10分ごと）に2件まで、1件ごとに40〜120秒あける
・星座の名前・月日（3/14・3月14日）・生年月日を読む。「私」「自分」などがあればアナタの星座として返す
・文面は禁止語チェック（麗子は「のよ」「です・ます」OKなので語だけ）を通ったものだけ。読めないコメントは返さず /autoreply/reiko に残す
止めるときは Render の環境変数 REIKO_AUTOREPLY=0。"""
import os
import random
import re
import time
import unicodedata
from datetime import date, datetime, timedelta

from flask import Blueprint

import threads_api
from autoreply import JST, _ts, name_of, pick
from inbox_kit import hizuke, kinshi, seinen

ACCOUNT = "reiko"
MARK = "0時で閉店"
PER_RUN = 2
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


def read_comment(comment: str):
    """(星座, 月日の言い直し or "", 誰の星座 'him'/'me') か None"""
    s = unicodedata.normalize("NFKC", comment or "")
    who = "me" if SELF.search(s) and not HIM.search(s) else "him"
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
    return None


# ---------- 文面 ----------

HEAD = ["{n}ちゃん、いらっしゃい。", "{n}ちゃん、いらっしゃい。置いてってくれてありがと。", "あら{n}ちゃん、いらっしゃい。"]
CLOSE = ["もっと聞きたい夜は、プロフィールからカウンター席にいらっしゃい。",
         "続きは、プロフィールのカウンター席でゆっくり聞くわ。",
         "今夜は、それだけ覚えて寝なさい。",
         "今夜はここまで。いい夢見なさいね。"]

HIM_TXT = {
    "牡羊座": ["牡羊座の男はね、好きになったら自分から走ってくる男よ。走ってこない時は、まだ火がついてないだけ。追いかけるより、火がつく話題をひとつ投げなさい。",
            "牡羊座の男は、待たされるのが大の苦手。返事を引っぱる駆け引きは、ほどほどにしなさい。"],
    "牡牛座": ["牡牛座の男は、とにかく慎重。決めるまでは長いけど、決めたら簡単には動かないわ。急かすと固まるから、会う回数でゆっくり温めなさい。",
            "牡牛座の男は、言葉より「一緒にいて楽か」を見てるの。おいしいものを一緒に食べる時間が、いちばん効くのよ。"],
    "双子座": ["双子座の男は、話がうまくて気が変わりやすいの。でも、楽しい相手のところには何度でも戻ってくるわ。重い話より、笑える話を投げなさい。",
            "双子座の男は、連絡がマメな時とぱったり止まる時があるの。止まった時に詰めると逃げるから、アナタも自分の予定で忙しくしてなさい。"],
    "蟹座": ["蟹座の男は、身内には甘くて、外には固いの。アナタを内側に入れたかどうかは、家族や昔の話をしてくれるかで分かるわ。",
           "蟹座の男は、傷つくのが怖いから自分からは踏み込まないの。安心させてあげると、ちゃんと殻から出てくるわよ。"],
    "獅子座": ["獅子座の男は、褒められて動くタイプ。ちゃんと見てるわよって伝えると、驚くほど動くの。ほかの男の話はしないこと。",
            "獅子座の男は、プライドが高いぶん、断られるのが怖いの。誘いを待ってるなら、断られにくい形でアナタから投げてあげなさい。"],
    "乙女座": ["乙女座の男は、細かいところをよく見てるわ。約束の時間や、前に言ったこと。小さな約束を守る子に、いちばん心を開くの。",
            "乙女座の男は、好きでもすぐには言わないの。頭の中で何度も確かめてから動くから、返事が遅くても冷めたとは限らないわよ。"],
    "天秤座": ["天秤座の男は、誰にでも感じがいいの。だから、アナタにだけ特別かどうかは、二人きりの時の顔で見なさい。",
            "天秤座の男は、決めるのが苦手。どっちがいいか聞くより、「ここ行こう」ってひとつ出してあげると話が進むわ。"],
    "蠍座": ["蠍座の男は、口数より行動。好きでもそっけないことがあるの。言葉の数じゃなくて、してくれたことを数えなさい。",
           "蠍座の男は、一度信じた相手には深いの。でも、試されてると感じると扉を閉めるわ。探るより、素直に聞きなさい。"],
    "射手座": ["射手座の男は、自由がいちばん大事。縛られると逃げるけど、放っておかれると、ふらっと戻ってくることも多いの。アナタも自分の楽しみを持ってなさい。",
            "射手座の男は、正直すぎるくらい正直。言ったことはだいたいそのままよ。期待を足さずに、言葉どおりに受け取りなさい。"],
    "山羊座": ["山羊座の男は、仕事の山を越えるまで恋の話をしないの。山の終わりがいつか、明るく聞いてみなさい。",
            "山羊座の男は、口約束より段取りの男。会う日を自分から決めてくるなら、それが本気の目印よ。"],
    "水瓶座": ["水瓶座の男は、友達みたいな距離が好きなの。近すぎると息苦しくなるから、ちょっと引いたくらいがちょうどいいわ。",
            "水瓶座の男は、ありきたりの口説き文句が効かないの。アナタの面白いところを見せなさい。"],
    "魚座": ["魚座の男は、優しくて流されやすいの。断るのが苦手だから、返事がない時は迷ってることが多いわ。",
           "魚座の男は、雰囲気に弱いの。言葉で詰めるより、一緒にいて心地いい時間を作りなさい。"],
}
ME_TXT = {
    "牡羊座": ["牡羊座のアナタは、好きになったら一直線。でも返事が来ないと、すぐ自分から終わらせたくなるでしょ。一晩だけ待ってから決めなさい。",
            "牡羊座のアナタは、追う恋のほうが燃えるタイプ。追いかけてる自分が好きなのか、彼が好きなのか、たまに確かめなさい。"],
    "牡牛座": ["牡牛座のアナタは、一度好きになると長いの。そのぶん、もう終わってる恋も手放せないことがあるわ。",
            "牡牛座のアナタは、安心をくれる男のそばで、いちばんきれいになる子よ。ドキドキだけで選ばないこと。"],
    "双子座": ["双子座のアナタは、頭の回転が速いぶん、彼の一言を何通りにも読んじゃうの。読みすぎて疲れたら、スマホを置きなさい。",
            "双子座のアナタは、話が合う男に弱いわね。話が合うのと、大事にしてくれるのは別よ。"],
    "蟹座": ["蟹座のアナタは、尽くしすぎるクセがあるの。彼の事情を先に分かってあげて、自分が後回しになってない？",
           "蟹座のアナタは、守りたい人ができると強くなる子。でも、守ってもらう側に回る練習もしなさい。"],
    "獅子座": ["獅子座のアナタは、強がるのが上手。平気な顔して、本当はいちばん待ってるでしょ。たまには寂しいって言っていいのよ。",
            "獅子座のアナタは、大事にされると輝く子。雑に扱う男のそばで、光を小さくしなくていいの。"],
    "乙女座": ["乙女座のアナタは、反省しすぎるの。返事が来ないのを、自分の送った文のせいにしてない？たいてい、アナタのせいじゃないわ。",
            "乙女座のアナタは、彼の小さな変化によく気づく子。気づいたことを、一人で抱えないで口にしなさい。"],
    "天秤座": ["天秤座のアナタは、相手に合わせるのが上手すぎるの。アナタが本当はどうしたいか、彼は知ってる？",
            "天秤座のアナタは、波風を立てたくなくて我慢しちゃう子。言いたいことは、明るくひとつだけ言いなさい。"],
    "蠍座": ["蠍座のアナタは、好きになると深いわ。深いぶん、彼の言葉の裏まで探っちゃうでしょ。探るより、まっすぐ聞きなさい。",
           "蠍座のアナタは、白黒つけたい子。グレーのまま待つのがいちばんしんどいのよね。待つ期限は、自分で決めていいの。"],
    "射手座": ["射手座のアナタは、自由な恋が好き。でも本当は、帰る場所がほしい子よ。それを言っていいの。",
            "射手座のアナタは、楽しいうちは追いかけて、重くなると逃げたくなるクセがあるわ。逃げる前に、一回だけ話しなさい。"],
    "山羊座": ["山羊座のアナタは、しっかりしすぎて甘えるのが下手。頼るのは負けじゃないわよ。",
            "山羊座のアナタは、先のことを考えすぎるの。今夜の楽しいを、もうちょっと味わいなさい。"],
    "水瓶座": ["水瓶座のアナタは、平気そうに見えて、実はちゃんと寂しい子。強がりは、アタシの前ではいらないわ。",
            "水瓶座のアナタは、ありきたりの恋に収まらない子。周りの正解じゃなくて、アナタの正解で選びなさい。"],
    "魚座": ["魚座のアナタは、相手の気持ちを感じ取りすぎるの。彼の機嫌で、自分の一日を決めないこと。",
           "魚座のアナタは、夢を見るのが上手。彼のいいところを足しすぎてないか、たまに確かめなさい。"],
}


def make_reply(username: str, comment: str, seed: str, used=()):
    """(文面 or None, 読めなかった理由)"""
    rnd = random.Random(seed)
    if kinshi.needs_care(comment):
        return None, "気持ちが重い言葉あり（手で）"
    got = read_comment(comment)
    if not got:
        return None, "星座も月日も読めない"
    sign, md, who = got
    n = re.sub(r"[_.]?(chan|chang|tyan)$", "", name_of(username), flags=re.I) or name_of(username)
    lines = [pick(HEAD, used, rnd).format(n=n)]
    if md:
        lines.append(f"{md}生まれなら、{sign}ね。")
    lines.append(pick((ME_TXT if who == "me" else HIM_TXT)[sign], used, rnd))
    lines.append(pick(CLOSE, used, rnd))
    return "\n".join(lines), ""


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
        answered = {(c.get("replied_to") or {}).get("id") for c in conv if c.get("is_reply_owned_by_me")}
        used = [c.get("text") or "" for c in conv if c.get("is_reply_owned_by_me")]
        for c in conv:
            if c.get("is_reply_owned_by_me") or (c.get("replied_to") or {}).get("id") != p["id"]:
                continue
            if c["id"] in answered or c["id"] in _done or _fail.get(c["id"], 0) >= 2 or c.get("hide_status") in ("HIDDEN", "COVERED", "BLOCKED", "RESTRICTED"):
                continue
            if _ts(c["timestamp"]) >= close:
                if c["id"] not in _skip:
                    _note(f"@{c.get('username')} は閉店後のコメントなので返さない")
                _skip[c["id"]] = "閉店後"
                continue
            out.append((c, used))
    return sorted(out, key=lambda x: x[0]["timestamp"])


def _delay(cid: str) -> timedelta:
    return timedelta(minutes=random.Random("r" + cid).randint(10, 40))


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
    for c, used in cands:
        if sent >= (20 if rush else PER_RUN):
            break
        # 0時台は待ち時間を短くして、0時前のコメントを返しきる
        if not rush and now.hour != 0 and now < _ts(c["timestamp"]) + _delay(c["id"]):
            continue
        text, why = make_reply(c.get("username", ""), c.get("text", ""), c["id"], used)
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
    return f"<pre style='white-space:pre-wrap;font-size:13px'>麗子 自動返信：{state}\n夜21時〜0時台・0時までのコメントだけ・コメントから10〜40分後・1回{PER_RUN}件まで\n\n{rows}</pre>"
