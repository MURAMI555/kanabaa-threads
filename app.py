"""叶ばぁ＋キャラ4本の Threads 自動投稿（Render の Web Service）。
・5分おきに schedule.POSTS を見て、時間が来た枠を投稿する（30分以内の遅れなら出す）。
・1つの枠は 本体（画像つき可）→ 返信 → 返信 の順につなぐ（1/3・2/3・3/3）。
・二重投稿防止：メモリの投稿済みリスト ＋ Threads上の直近の投稿と本文の先頭を照合。
・トークンは毎週月曜に更新。RENDER_API_KEY があれば Render の環境変数も更新する。
・/health（生存確認）、/status（予定と直近の結果）、/check?account=mio（接続確認。投稿はしない）。
・/oauth/start?account=mio → /oauth/callback で長期トークンを取る（THREADS_APP_ID と THREADS_APP_SECRET が要る）。
2026/10/22 複数アカウント：予定表のキーは "YYYY-MM-DD HH:MM"（叶ばぁ）か "mio@YYYY-MM-DD HH:MM"（キャラ名@日時）。
  トークンが入っていないアカウントの枠は飛ばす（投稿しない）。"""
import os
import threading
import traceback
import time
from datetime import datetime, timedelta

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, jsonify, redirect, request

import instagram_api
import threads_api
from inbox_kit import routes as inbox
from schedule import POSTS
from schedule_insta import INSTA_POSTS

JST = pytz.timezone("Asia/Tokyo")
LATE_LIMIT = timedelta(minutes=30)
IMG_BASE = os.environ.get("IMG_BASE", "").rstrip("/")  # 例: https://raw.githubusercontent.com/MURAMI555/kanabaa-threads/main/img
REEL_BASE = os.environ.get("REEL_BASE", "https://murami555.github.io/kanabaa-threads/reels").rstrip("/")  # リールの動画（docs/reels/）。raw は octet-stream なので Pages を使う
app = Flask(__name__)
app.register_blueprint(inbox.bp)  # 受付箱 /inbox・LINE Webhook /line/webhook（下書きだけ。送らない）
_lock = threading.Lock()
_done: dict = {}      # slot -> {"status","account","ids","error","at"}
_log: list = []


def _note(msg: str):
    _log.append(f"{datetime.now(JST).strftime('%m/%d %H:%M')} {msg}")
    del _log[:-200]
    print(msg, flush=True)


def split_slot(slot: str):
    """'mio@2026-10-27 08:00' → ('mio', '2026-10-27 08:00')。'@' が無ければ叶ばぁ"""
    if "@" in slot:
        acc, t = slot.split("@", 1)
        return acc.strip(), t.strip()
    return threads_api.DEFAULT, slot


def slot_time(slot: str) -> datetime:
    return JST.localize(datetime.strptime(split_slot(slot)[1], "%Y-%m-%d %H:%M"))


def _already_on_threads(first_text: str, at: datetime, account: str) -> bool:
    """同じ本文の先頭が、その枠の前後12時間に投稿済みなら True"""
    head = first_text.strip().splitlines()[0][:25]
    try:
        for p in threads_api.my_posts(account=account):
            t = (p.get("text") or "").strip()
            if not t.startswith(head):
                continue
            ts = datetime.strptime(p["timestamp"], "%Y-%m-%dT%H:%M:%S%z").astimezone(JST)
            if abs(ts - at) < timedelta(hours=12):
                return True
    except Exception as e:  # noqa: BLE001
        _note(f"[{account}] 直近投稿の確認に失敗（続行）: {e}")
    return False


def post_slot(slot: str, parts: list, account: str) -> list:
    ids = []
    reply_to = None
    # 抜けた続きを後から足す時：1本目に "reply_under"（すでに出た親投稿の本文の書き出し）を書くと、その下に返信でつなぐ
    head = parts[0].get("reply_under")
    if head:
        parent = next((p for p in threads_api.my_posts(account=account) if (p.get("text") or "").startswith(head)), None)
        if not parent:
            raise RuntimeError(f"つなぐ先の投稿が見つからない: {head}")
        reply_to = parent["id"]
    for p in parts:
        img = f"{IMG_BASE}/{p['image']}" if p.get("image") and IMG_BASE else None
        # 続き（返信）は公開直後だと落ちることがある（10/27 麗子8:00の2本目が抜けた）。少し待って3回まで試す
        for n in range(3 if reply_to else 1):
            if reply_to:
                time.sleep(10 * (n + 1))
            try:
                pid = threads_api.post(p["text"], image_url=img, reply_to_id=reply_to, account=account)
                break
            except Exception as e:  # noqa: BLE001
                if not reply_to or n == 2:
                    raise
                _note(f"[{account}] {slot} の{len(ids) + 1}本目に失敗、やり直す: {e}")
        ids.append(pid)
        reply_to = pid
    return ids


def post_due():
    now = datetime.now(JST)
    with _lock:
        for slot, parts in sorted(POSTS.items(), key=lambda kv: split_slot(kv[0])[1]):
            account, _ = split_slot(slot)
            at = slot_time(slot)
            if not (at <= now < at + LATE_LIMIT) or slot in _done:
                continue
            if not threads_api.configured(account):
                _done[slot] = {"status": "skipped(no token)", "account": account, "at": now.isoformat()}
                _note(f"[{account}] {slot} はトークン未設定なので飛ばした")
                continue
            if _already_on_threads(parts[0]["text"], at, account):
                _done[slot] = {"status": "skipped(already)", "account": account, "at": now.isoformat()}
                _note(f"[{account}] {slot} は投稿済みなので飛ばした")
                continue
            _done[slot] = {"status": "posting", "account": account, "at": now.isoformat()}
            try:
                ids = post_slot(slot, parts, account)
                _done[slot] = {"status": "posted", "account": account, "ids": ids, "at": now.isoformat()}
                _note(f"[{account}] {slot} 投稿した {ids}")
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                _done[slot] = {"status": "error", "account": account, "error": str(e)[:300], "at": now.isoformat()}
                _note(f"[{account}] {slot} 投稿に失敗: {e}")


def refresh_weekly():
    for account in threads_api.configured_accounts():
        try:
            new = threads_api.refresh_token(account)
            threads_api.set_token(new, account)
            saved = threads_api.save_token_to_render(new, account)
            _note(f"[{account}] トークンを更新した" + ("（Renderの環境変数も更新）" if saved else "（メモリのみ。Renderの環境変数は手で更新が要る）"))
        except Exception as e:  # noqa: BLE001
            _note(f"[{account}] トークン更新に失敗: {e}")


@app.get("/")
@app.get("/health")
def health():
    return "ok", 200


@app.get("/status")
def status():
    now = datetime.now(JST)
    upcoming = [s for s in sorted(POSTS, key=lambda k: split_slot(k)[1]) if slot_time(s) >= now][:15]
    return jsonify({"now": now.strftime("%Y-%m-%d %H:%M"),
                    "accounts": {a: threads_api.configured(a) for a in threads_api.ACCOUNTS},
                    "img_base": IMG_BASE, "upcoming": upcoming, "done": _done, "log": _log[-30:]})


@app.get("/check")
def check():
    account = request.args.get("account", threads_api.DEFAULT)
    try:
        return jsonify({"account": account, "me": threads_api.me(account), "limit": threads_api.publishing_limit(account)})
    except Exception as e:  # noqa: BLE001
        return jsonify({"account": account, "error": str(e)}), 500


def _redirect_uri() -> str:
    return request.url_root.rstrip("/").replace("http://", "https://") + "/oauth/callback"


@app.get("/oauth/start")
def oauth_start():
    app_id = os.environ.get("THREADS_APP_ID", "")
    account = request.args.get("account", threads_api.DEFAULT)
    url = ("https://threads.net/oauth/authorize?client_id=" + app_id +
           "&redirect_uri=" + _redirect_uri() +
           "&scope=threads_basic,threads_content_publish,threads_manage_replies,threads_read_replies&response_type=code"
           "&state=" + account)
    return redirect(url)


@app.get("/oauth/callback")
def oauth_callback():
    code = request.args.get("code", "")
    account = request.args.get("state", threads_api.DEFAULT) or threads_api.DEFAULT
    if not code:
        return "code がありません: " + str(dict(request.args)), 400
    try:
        long_token = threads_api.exchange_code(os.environ["THREADS_APP_ID"], os.environ["THREADS_APP_SECRET"],
                                               _redirect_uri(), code)
    except Exception as e:  # noqa: BLE001
        return "トークン取得に失敗: " + str(e), 500
    threads_api.set_token(long_token, account)
    saved = threads_api.save_token_to_render(long_token, account)
    env = threads_api.env_name("THREADS_ACCESS_TOKEN", account)
    hint = ("Renderの環境変数にも保存した。" if saved else
            f"この値を Render の環境変数 {env} に貼って保存してください（再デプロイされる）。")
    return (f"<h2>長期トークン（60日）・アカウント {account}</h2><p>" + hint + "</p><textarea rows=6 cols=90>" + long_token + "</textarea>"
            f"<p>保存したら /check?account={account} で接続を確認。</p>")


# ── インスタ（2026/10/25〜・鈴から）。予定表は schedule_insta.INSTA_POSTS、キーは "rin@YYYY-MM-DD HH:MM" ──
_ig_done: dict = {}   # slot -> {"status","ids","error","at"}


def _ig_already(caption: str, at: datetime, account: str) -> bool:
    """同じキャプションの先頭が、その枠の前後12時間に投稿済みなら True"""
    head = caption.strip().splitlines()[0][:20]
    try:
        for p in instagram_api.my_posts(account):
            if not (p.get("caption") or "").strip().startswith(head):
                continue
            ts = datetime.strptime(p["timestamp"], "%Y-%m-%dT%H:%M:%S%z").astimezone(JST)
            if abs(ts - at) < timedelta(hours=12):
                return True
    except Exception as e:  # noqa: BLE001
        _note(f"[ig:{account}] 直近投稿の確認に失敗（続行）: {e}")
    return False


def ig_post_due():
    now = datetime.now(JST)
    with _lock:
        for slot, item in sorted(INSTA_POSTS.items(), key=lambda kv: split_slot(kv[0])[1]):
            account, _ = split_slot(slot)
            at = slot_time(slot)
            if not (at <= now < at + LATE_LIMIT) or slot in _ig_done:
                continue
            if not instagram_api.configured(account):
                _ig_done[slot] = {"status": "skipped(no token)", "at": now.isoformat()}
                _note(f"[ig:{account}] {slot} はトークン未設定なので飛ばした")
                continue
            if _ig_already(item["caption"], at, account):
                _ig_done[slot] = {"status": "skipped(already)", "at": now.isoformat()}
                _note(f"[ig:{account}] {slot} は投稿済みなので飛ばした")
                continue
            _ig_done[slot] = {"status": "posting", "at": now.isoformat()}
            try:
                if item.get("video"):  # リール（2026/10/25 鈴・週4本）。動画は GitHub Pages（video/mp4 で配られる）から
                    cover = f"{REEL_BASE}/{item['cover']}" if item.get("cover") else ""  # 表紙（一覧で何の投稿か分かるように）
                    pid = instagram_api.post_reel(item["caption"], f"{REEL_BASE}/{item['video']}", account, cover)
                else:
                    urls = [f"{IMG_BASE}/{p}" for p in item["images"]]
                    pid = instagram_api.post(item["caption"], urls, account)
                _ig_done[slot] = {"status": "posted", "ids": [pid], "at": now.isoformat()}
                _note(f"[ig:{account}] {slot} 投稿した {pid}")
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                _ig_done[slot] = {"status": "error", "error": str(e)[:300], "at": now.isoformat()}
                _note(f"[ig:{account}] {slot} 投稿に失敗: {e}")


def ig_refresh_weekly():
    for account in instagram_api.configured_accounts():
        try:
            new = instagram_api.refresh_token(account)
            instagram_api.set_token(new, account)
            saved = instagram_api.save_token_to_render(new, account)
            _note(f"[ig:{account}] トークンを更新した" + ("（Renderの環境変数も更新）" if saved else "（メモリのみ。Renderの環境変数は手で更新が要る）"))
        except Exception as e:  # noqa: BLE001
            _note(f"[ig:{account}] トークン更新に失敗: {e}")


@app.get("/ig/status")
def ig_status():
    now = datetime.now(JST)
    upcoming = [s for s in sorted(INSTA_POSTS, key=lambda k: split_slot(k)[1]) if slot_time(s) >= now][:15]
    return jsonify({"now": now.strftime("%Y-%m-%d %H:%M"),
                    "accounts": {a: instagram_api.configured(a) for a in instagram_api.ACCOUNTS},
                    "upcoming": upcoming, "done": _ig_done})


@app.get("/ig/check")
def ig_check():
    account = request.args.get("account", "rin")
    try:
        return jsonify({"account": account, "me": instagram_api.me(account), "limit": instagram_api.publishing_limit(account)})
    except Exception as e:  # noqa: BLE001
        return jsonify({"account": account, "error": str(e)}), 500


@app.get("/ig/stats")
def ig_stats():
    """投稿ごとの閲覧数（スマホで見る表）。/ig/stats?account=rin、?format=json でJSON"""
    account = request.args.get("account", "rin")
    try:
        prof = instagram_api.profile(account)
        rows = instagram_api.media_stats(account, int(request.args.get("limit", 20)))
    except Exception as e:  # noqa: BLE001
        return jsonify({"account": account, "error": str(e)}), 500
    if request.args.get("format") == "json":
        return jsonify({"account": account, "profile": prof, "posts": rows})
    cols = [("views", "閲覧"), ("reach", "リーチ"), ("likes", "いいね"), ("comments", "コメ"), ("saved", "保存"), ("shares", "シェア")]
    total = sum(r.get("views") or 0 for r in rows)
    body = []
    for r in rows:
        ts = datetime.strptime(r["timestamp"], "%Y-%m-%dT%H:%M:%S%z").astimezone(JST).strftime("%m/%d %H:%M")
        cells = "".join(f"<td>{'' if r.get(k) is None else r[k]}</td>" for k, _ in cols)
        err = f"<div class=e>閲覧数が取れない：{html.escape(r['error'])}</div>" if r.get("error") else ""
        body.append(f"<tr><td><a href='{html.escape(r.get('permalink') or '')}'>{ts}</a><br><small>{html.escape(r['caption'])}</small>{err}</td>{cells}</tr>")
    head = "".join(f"<th>{n}</th>" for _, n in cols)
    name = html.escape(prof.get("username", account))
    return (f"<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>@{name} 閲覧数</title>"
            "<style>body{font-family:sans-serif;margin:12px}table{border-collapse:collapse;width:100%;font-size:13px}"
            "td,th{border-bottom:1px solid #ddd;padding:6px 4px;text-align:right}td:first-child,th:first-child{text-align:left}"
            "small{color:#777}.e{color:#c00;font-size:11px}</style>"
            f"<h3>@{name}</h3>"
            f"<p>フォロワー {prof.get('followers_count', '-')}・投稿 {prof.get('media_count', '-')}・直近{len(rows)}本の閲覧合計 {total}"
            f"<br><small>{datetime.now(JST).strftime('%Y-%m-%d %H:%M')} 時点</small></p>"
            f"<table><tr><th>投稿</th>{head}</tr>{''.join(body)}</table>")


_sched = None
if os.environ.get("DISABLE_SCHEDULER") != "1":
    _sched = BackgroundScheduler(timezone=JST)
    _sched.add_job(post_due, "interval", minutes=5, id="post_due")
    _sched.add_job(ig_post_due, "interval", minutes=5, id="ig_post_due")
    _sched.add_job(refresh_weekly, "cron", day_of_week="mon", hour=4, minute=0, id="refresh")
    _sched.add_job(ig_refresh_weekly, "cron", day_of_week="mon", hour=4, minute=10, id="ig_refresh")
    _sched.add_job(inbox.job, "interval", minutes=15, id="inbox", max_instances=1)
    _sched.start()
    _note("scheduler started")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "10000")))
