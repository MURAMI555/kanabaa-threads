"""叶ばぁの受付箱（下書きだけ自動。送るのはみかちゃんの手。本部⑥「自動返信ツール不使用」を守るため、ここからは何も送らない）。
・Threads：自分の投稿についたコメントを15分おきに読み、生年月日があれば返信の下書きを作る。返信済みは自動で「済」
・LINE（公式 @492vxwcy・Messaging API の Webhook）：届いたメッセージを置き場に貯め、最後のメッセージから10分たったら初視の下書きを作る
  LINE へは返事を送らない（reply も push もしない）。返事は LINE公式アカウントのアプリ／chat.line.biz から手で
・/inbox?pin=… で一覧（スマホ用）。コピー・送った・飛ばす・霊視メモで作り直す
環境変数：INBOX_PIN／INBOX_STORE_URL・INBOX_STORE_KEY（gas/kanabaa_inbox.gs）／ANTHROPIC_API_KEY／LINE_CHANNEL_SECRET・LINE_CHANNEL_ACCESS_TOKEN"""
import base64
import hashlib
import hmac
import html
import json
import os
import threading
import traceback
from datetime import datetime, timedelta

import pytz
import requests
from flask import Blueprint, abort, make_response, redirect, request

import threads_api
from . import drafts, hizuke, kinshi, store

JST = pytz.timezone("Asia/Tokyo")
bp = Blueprint("inbox", __name__)
_job_lock = threading.Lock()
_log: list = []
LINE_WAIT = timedelta(minutes=10)     # 分けて送ってくる人がいるので、最後のメッセージから少し待つ
LOOK_BACK = timedelta(days=10)        # この日数より古い投稿のコメントは見ない
MY_NAME = "kanabaa.yoru"
WINDOW = """病気・法律・借金のことは、婆さんは視ないよ。その道の人を頼っておくれ。"""
CARE_TEXT = """話してくれてありがとね。その気持ち、ひとりで抱えなくていい。
今夜は占いより先に、話を聞いてくれる人を頼っておくれ。
よりそいホットライン 0120-279-338（24時間）
いのちの電話 0570-783-556
婆さんは、あんたがここに書いてくれたことを、ちゃんと受け取ったよ。"""


def note(msg: str):
    _log.append(f"{datetime.now(JST).strftime('%m/%d %H:%M')} {msg}")
    del _log[:-100]
    print("[inbox] " + msg, flush=True)


def now_s() -> str:
    return datetime.now(JST).strftime("%Y-%m-%d %H:%M")


def ready() -> bool:
    return store.configured()


# ---------------- Threads ----------------

def collect_threads():
    """自分の投稿のコメントを読んで、新しい生年月日コメントに下書きを作る"""
    if not (ready() and threads_api.configured()):
        return
    items = store.all_items(max_age=0)
    since = datetime.now(JST) - LOOK_BACK
    for post in threads_api.my_posts(limit=40):
        try:
            ts = datetime.strptime(post["timestamp"], "%Y-%m-%dT%H:%M:%S%z").astimezone(JST)
        except (KeyError, ValueError):
            continue
        if ts < since:
            continue
        try:
            conv = threads_api.conversation(post["id"])
        except Exception as e:  # noqa: BLE001
            note(f"コメントの読み取りに失敗 {post['id']}: {e}")
            continue
        replied = {(c.get("replied_to") or {}).get("id") for c in conv
                   if c.get("is_reply_owned_by_me") or c.get("username") == MY_NAME}
        for c in conv:
            if c.get("is_reply_owned_by_me") or c.get("username") == MY_NAME:
                continue
            if c.get("hide_status") not in (None, "NOT_HUSHED", "UNHUSHED"):
                continue
            iid = "th:" + c["id"]
            it = items.get(iid)
            done = c["id"] in replied
            if it is None:
                text = c.get("text") or ""
                it = {"id": iid, "kind": "threads", "status": "sent" if done else "new", "name": c.get("username", ""),
                      "text": text, "permalink": c.get("permalink", ""), "at": c.get("timestamp", ""),
                      "post_text": (post.get("text") or "")[:400], "dates": hizuke.find_dates(text)}
                if kinshi.needs_care(text):
                    it.update(status="care", draft=CARE_TEXT, hits=[])
                elif not it["dates"] and not done:
                    it["status"] = "nodate"
                store.put(it)
            elif done and it["status"] not in ("sent", "skip"):
                it["status"] = "sent"
                store.put(it)


def draft_threads():
    if not (ready() and drafts.configured()):
        return
    for it in store.all_items().values():
        if it["kind"] == "threads" and it["status"] == "new" and not it.get("draft"):
            make_threads_draft(it)


def make_threads_draft(it: dict):
    try:
        text, hits = drafts.threads_reply(it["name"], it["text"], it.get("dates") or [], it.get("post_text", ""))
        it.update(draft=text, hits=hits, drafted=now_s(), status="drafted", error="")
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        it.update(error=str(e)[:200])
    store.put(it)


# ---------------- LINE ----------------

def _line_profile_name(user_id: str) -> str:
    tok = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
    if not tok:
        return ""
    try:
        r = requests.get(f"https://api.line.me/v2/bot/profile/{user_id}",
                         headers={"Authorization": f"Bearer {tok}"}, timeout=15)
        return r.json().get("displayName", "") if r.ok else ""
    except Exception:  # noqa: BLE001
        return ""


@bp.post("/line/webhook")
def line_webhook():
    secret = os.environ.get("LINE_CHANNEL_SECRET", "")
    body = request.get_data()
    if not secret:
        return "ok"
    sig = base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()
    if not hmac.compare_digest(sig, request.headers.get("X-Line-Signature", "")):
        abort(400)
    if not ready():
        return "ok"
    for ev in json.loads(body or b"{}").get("events", []):
        try:
            _on_line_event(ev)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            note(f"LINEの受け取りで失敗: {e}")
    return "ok"


def _on_line_event(ev: dict):
    uid = (ev.get("source") or {}).get("userId")
    if not uid or (ev.get("source") or {}).get("type") != "user":
        return
    iid = "line:" + uid
    it = store.get(iid) or {"id": iid, "kind": "line", "status": "follow", "name": _line_profile_name(uid),
                            "messages": [], "first": now_s()}
    t = ev.get("type")
    if t == "follow":
        it["followed"] = now_s()
    elif t == "unfollow":
        it["status"] = "blocked"
    elif t == "message":
        m = ev.get("message") or {}
        text = m.get("text") if m.get("type") == "text" else f"［{m.get('type', 'その他')}が届いた］"
        it.setdefault("messages", []).append({"at": now_s(), "text": text or ""})
        it["messages"] = it["messages"][-40:]
        it["last_in"] = now_s()
        if not it.get("name"):
            it["name"] = _line_profile_name(uid)
        if it["status"] in ("follow", "sent", "skip", "drafted", "new", "nodate"):
            it["status"] = "new"
    store.put(it)


def _new_text(it: dict) -> str:
    """まだ鑑定していないぶんのメッセージ（前回の下書きより後）"""
    base = it.get("drafted_upto", 0)
    return "\n".join(m["text"] for m in it.get("messages", [])[base:])


def draft_line():
    if not (ready() and drafts.configured()):
        return
    now = datetime.now(JST)
    for it in store.all_items().values():
        if it["kind"] != "line" or it["status"] != "new" or not it.get("last_in"):
            continue
        last = JST.localize(datetime.strptime(it["last_in"], "%Y-%m-%d %H:%M"))
        if now - last < LINE_WAIT:
            continue
        make_line_draft(it)


def make_line_draft(it: dict, memo: str | None = None):
    text_all = "\n".join(m["text"] for m in it.get("messages", []))
    new = _new_text(it) or text_all
    if memo is not None:
        it["memo"] = memo
    try:
        if kinshi.needs_care(new):
            it.update(status="care", draft=CARE_TEXT, hits=[], drafted=now_s())
        elif it.get("hatsumi_sent") and "本鑑定" in new:
            sq = os.environ.get("SQUARE_URL", "〔Squareのリンク〕")
            it.update(status="drafted", kind_note="本鑑定の希望", hits=[], drafted=now_s(), draft=(
                "本鑑定は4,980円だよ。決済はこのリンクから。\n" + sq +
                "\n決済が確認できたら、もう少しだけ聞いて、それから本鑑定文を書く。\n無理に勧めはしない。今じゃないと思ったら、それでいい。"))
        elif it.get("hatsumi_sent"):
            it.update(status="nodate", kind_note="初視のあとのメッセージ", draft="", hits=[])
        else:
            dates = hizuke.find_dates(text_all)
            if not dates and len(text_all) < 30:
                it.update(status="nodate", kind_note="4項目がまだ", draft="", hits=[])
            else:
                draft, hits = drafts.hatsumi(it.get("name") or "あんた", text_all, dates, it.get("memo", ""))
                it.update(status="drafted", kind_note="初視", dates=dates, draft=draft, hits=hits, drafted=now_s())
        it["drafted_upto"] = len(it.get("messages", []))
        it["error"] = ""
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        it["error"] = str(e)[:200]
    store.put(it)


# ---------------- 定期の仕事 ----------------

def job():
    if not _job_lock.acquire(blocking=False):
        return
    try:
        for f in (collect_threads, draft_threads, draft_line):
            try:
                f()
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                note(f"{f.__name__} で失敗: {e}")
    finally:
        _job_lock.release()


# ---------------- 画面 ----------------

def _pin_ok() -> bool:
    pin = os.environ.get("INBOX_PIN", "")
    if not pin:
        return False
    want = hashlib.sha256(("kanabaa:" + pin).encode()).hexdigest()
    return request.cookies.get("kb_inbox") == want or request.values.get("pin") == pin


def _set_pin(resp):
    pin = os.environ.get("INBOX_PIN", "")
    if request.values.get("pin") == pin and pin:
        resp.set_cookie("kb_inbox", hashlib.sha256(("kanabaa:" + pin).encode()).hexdigest(),
                        max_age=60 * 60 * 24 * 180, httponly=True, secure=True, samesite="Lax")
    return resp


LABEL = {"drafted": "下書きあり", "new": "下書き待ち", "nodate": "生年月日なし・様子見", "care": "占わない（窓口を案内）",
         "follow": "友だち追加だけ", "sent": "送った", "skip": "飛ばした", "blocked": "ブロックされた"}
ORDER = ["care", "drafted", "new", "nodate", "follow"]


def _card(it: dict) -> str:
    e = html.escape
    iid = e(it["id"])
    if it["kind"] == "threads":
        head = f"Threads ｜ {e(it.get('name', ''))}"
        body = e(it.get("text", ""))
        open_link = f'<a class="btn" href="{e(it.get("permalink", ""))}" target="_blank">Threadsで開く</a>' if it.get("permalink") else ""
    else:
        head = f"LINE ｜ {e(it.get('name') or '（名前なし）')} {e(it.get('kind_note', ''))}"
        body = "<br>".join(f"<small>{e(m['at'][5:])}</small> {e(m['text'])}" for m in it.get("messages", [])[-12:])
        open_link = '<a class="btn" href="https://chat.line.biz/" target="_blank">LINEのチャットを開く</a>'
    hits = it.get("hits") or []
    warn = f'<p class="warn">要確認 {e(" / ".join(hits))}</p>' if hits else ""
    err = f'<p class="warn">失敗 {e(it["error"])}</p>' if it.get("error") else ""
    draft = it.get("draft", "")
    ta = (f'<textarea id="d-{iid}" rows="{min(30, 4 + draft.count(chr(10)))}">{e(draft)}</textarea>'
          f'<p><button onclick="cp(\'d-{iid}\')">コピー</button> <small>{len(draft)}字</small></p>') if draft else ""
    memo = ""
    if it["kind"] == "line":
        memo = (f'<form method="post" action="act"><input type="hidden" name="id" value="{iid}">'
                f'<input type="hidden" name="op" value="redraft">'
                f'<textarea name="memo" rows="2" placeholder="霊視メモ（1〜2行）。書いて「作り直す」">{e(it.get("memo", ""))}</textarea>'
                f'<button>霊視メモで作り直す</button></form>')
    elif it.get("status") in ("nodate", "new", "drafted"):
        memo = (f'<form method="post" action="act"><input type="hidden" name="id" value="{iid}">'
                f'<input type="hidden" name="op" value="redraft"><button>下書きを作る／作り直す</button></form>')
    acts = "".join(f'<form method="post" action="act" class="in"><input type="hidden" name="id" value="{iid}">'
                   f'<input type="hidden" name="op" value="{op}"><button>{lab}</button></form>'
                   for op, lab in (("sent", "送った"), ("skip", "飛ばす")))
    return (f'<div class="card {e(it["status"])}"><p class="h">{head} <span class="tag">{LABEL.get(it["status"], it["status"])}</span></p>'
            f'<div class="body">{body}</div>{warn}{err}{ta}{memo}<p>{open_link} {acts}</p></div>')


@bp.get("/inbox")
def inbox():
    if not _pin_ok():
        return make_response('<form><input name="pin" type="password" placeholder="合言葉"><button>開く</button></form>', 401)
    if not ready():
        return "受付箱の置き場（INBOX_STORE_URL / INBOX_STORE_KEY）が未設定"
    items = list(store.all_items(max_age=20).values())
    live = sorted([i for i in items if i["status"] in ORDER],
                  key=lambda i: (ORDER.index(i["status"]), i.get("last_in") or i.get("at") or ""))
    done = len(items) - len(live)
    cards = "".join(_card(i) for i in live) or "<p>今は何も来ていないよ。</p>"
    page = f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">
<title>叶ばぁ 受付箱</title><style>
body{{font-family:sans-serif;margin:0;padding:12px 16px;background:#f6f3ee;color:#222;font-size:15px}}
h1{{font-size:18px}} .card{{background:#fff;border-radius:10px;padding:10px 12px;margin:12px 0;border-left:6px solid #bbb}}
.card.drafted{{border-color:#2a7}} .card.care{{border-color:#c33}} .card.new{{border-color:#d90}}
.h{{font-weight:bold;margin:0 0 6px}} .tag{{font-weight:normal;font-size:12px;background:#eee;border-radius:8px;padding:1px 8px}}
.body{{white-space:pre-wrap;background:#faf8f4;padding:6px 8px;border-radius:6px;font-size:14px}}
textarea{{width:100%;box-sizing:border-box;font-size:15px;margin-top:8px}}
button,.btn{{font-size:14px;padding:6px 12px;margin:4px 4px 0 0;border:1px solid #888;border-radius:6px;background:#fff;color:#222;text-decoration:none;display:inline-block}}
form.in{{display:inline}} .warn{{color:#c33;font-size:13px}} small{{color:#777}}
</style></head><body><h1>叶ばぁ 受付箱</h1>
<p><small>下書きを作るだけ。送るのはThreads・LINEのアプリから手で。送ったら「送った」を押す。済 {done}件 ｜ 更新 {now_s()}</small>
<a class="btn" href="inbox">再読み込み</a> <form method="post" action="act" class="in"><input type="hidden" name="op" value="pull"><button>今すぐ読み込む</button></form></p>
{cards}<script>function cp(id){{const t=document.getElementById(id);t.select();navigator.clipboard.writeText(t.value).then(()=>alert('コピーしたよ'))}}</script>
</body></html>"""
    return _set_pin(make_response(page))


@bp.post("/act")
def act():
    if not _pin_ok():
        abort(401)
    op = request.form.get("op", "")
    if op == "pull":
        job()
        return redirect("inbox")
    it = store.get(request.form.get("id", ""))
    if not it:
        abort(404)
    if op in ("sent", "skip"):
        it["status"] = op
        it["closed"] = now_s()
        if op == "sent" and it["kind"] == "line" and it.get("kind_note") == "初視":
            it["hatsumi_sent"] = now_s()
        store.put(it)
    elif op == "redraft":
        if it["kind"] == "line":
            it["drafted_upto"] = 0 if not it.get("hatsumi_sent") else it.get("drafted_upto", 0)
            make_line_draft(it, memo=request.form.get("memo", ""))
        else:
            it["dates"] = it.get("dates") or hizuke.find_dates(it.get("text", ""))
            make_threads_draft(it)
    return redirect("inbox")


@bp.get("/inbox/log")
def inbox_log():
    if not _pin_ok():
        abort(401)
    return {"log": _log[-50:], "store": ready(), "ai": drafts.configured(),
            "line": bool(os.environ.get("LINE_CHANNEL_SECRET"))}
