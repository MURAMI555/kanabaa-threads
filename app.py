"""叶ばぁ Threads 自動投稿（Render の Web Service）。
・5分おきに schedule.POSTS を見て、時間が来た枠を投稿する（30分以内の遅れなら出す）。
・1つの枠は 本体（画像つき可）→ 返信 → 返信 の順につなぐ（1/3・2/3・3/3）。
・二重投稿防止：メモリの投稿済みリスト ＋ Threads上の直近の投稿と本文の先頭を照合。
・トークンは毎週月曜に更新。RENDER_API_KEY があれば Render の環境変数も更新する。
・/health（生存確認・UptimeRobot用）、/status（予定と直近の結果）、/check（接続確認。投稿はしない）。
・/oauth/start → /oauth/callback で長期トークンを取る（最初の1回。THREADS_APP_ID と THREADS_APP_SECRET が要る）。"""
import os
import threading
import traceback
from datetime import datetime, timedelta

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, jsonify, redirect, request

import threads_api
from schedule import POSTS

JST = pytz.timezone("Asia/Tokyo")
LATE_LIMIT = timedelta(minutes=30)
IMG_BASE = os.environ.get("IMG_BASE", "").rstrip("/")  # 例: https://raw.githubusercontent.com/MURAMI555/kanabaa-threads/main/img
app = Flask(__name__)
_lock = threading.Lock()
_done: dict = {}      # slot -> {"status","ids","error","at"}
_log: list = []


def _note(msg: str):
    _log.append(f"{datetime.now(JST).strftime('%m/%d %H:%M')} {msg}")
    del _log[:-200]
    print(msg, flush=True)


def _already_on_threads(first_text: str, at: datetime) -> bool:
    """同じ本文の先頭が、その枠の前後12時間に投稿済みなら True"""
    head = first_text.strip().splitlines()[0][:25]
    try:
        for p in threads_api.my_posts():
            t = (p.get("text") or "").strip()
            if not t.startswith(head):
                continue
            ts = datetime.strptime(p["timestamp"], "%Y-%m-%dT%H:%M:%S%z").astimezone(JST)
            if abs(ts - at) < timedelta(hours=12):
                return True
    except Exception as e:  # noqa: BLE001
        _note(f"直近投稿の確認に失敗（続行）: {e}")
    return False


def post_slot(slot: str, parts: list) -> list:
    ids = []
    reply_to = None
    for p in parts:
        img = f"{IMG_BASE}/{p['image']}" if p.get("image") and IMG_BASE else None
        pid = threads_api.post(p["text"], image_url=img, reply_to_id=reply_to)
        ids.append(pid)
        reply_to = pid
    return ids


def post_due():
    if not threads_api.configured():
        return
    now = datetime.now(JST)
    with _lock:
        for slot, parts in sorted(POSTS.items()):
            at = JST.localize(datetime.strptime(slot, "%Y-%m-%d %H:%M"))
            if not (at <= now < at + LATE_LIMIT) or slot in _done:
                continue
            if _already_on_threads(parts[0]["text"], at):
                _done[slot] = {"status": "skipped(already)", "at": now.isoformat()}
                _note(f"{slot} は投稿済みなので飛ばした")
                continue
            _done[slot] = {"status": "posting", "at": now.isoformat()}
            try:
                ids = post_slot(slot, parts)
                _done[slot] = {"status": "posted", "ids": ids, "at": now.isoformat()}
                _note(f"{slot} 投稿した {ids}")
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                _done[slot] = {"status": "error", "error": str(e)[:300], "at": now.isoformat()}
                _note(f"{slot} 投稿に失敗: {e}")


def refresh_weekly():
    if not threads_api.configured():
        return
    try:
        new = threads_api.refresh_token()
        threads_api.set_token(new)
        saved = threads_api.save_token_to_render(new)
        _note("トークンを更新した" + ("（Renderの環境変数も更新）" if saved else "（メモリのみ。Renderの環境変数は手で更新が要る）"))
    except Exception as e:  # noqa: BLE001
        _note(f"トークン更新に失敗: {e}")


@app.get("/")
@app.get("/health")
def health():
    return "ok", 200


@app.get("/status")
def status():
    now = datetime.now(JST)
    upcoming = [s for s in sorted(POSTS) if JST.localize(datetime.strptime(s, "%Y-%m-%d %H:%M")) >= now][:10]
    return jsonify({"now": now.strftime("%Y-%m-%d %H:%M"), "configured": threads_api.configured(),
                    "img_base": IMG_BASE, "upcoming": upcoming, "done": _done, "log": _log[-30:]})


@app.get("/check")
def check():
    try:
        return jsonify({"me": threads_api.me(), "limit": threads_api.publishing_limit()})
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)}), 500


def _redirect_uri() -> str:
    return request.url_root.rstrip("/").replace("http://", "https://") + "/oauth/callback"


@app.get("/oauth/start")
def oauth_start():
    app_id = os.environ.get("THREADS_APP_ID", "")
    url = ("https://threads.net/oauth/authorize?client_id=" + app_id +
           "&redirect_uri=" + _redirect_uri() +
           "&scope=threads_basic,threads_content_publish,threads_manage_replies,threads_read_replies&response_type=code")
    return redirect(url)


@app.get("/oauth/callback")
def oauth_callback():
    code = request.args.get("code", "")
    if not code:
        return "code がありません: " + str(dict(request.args)), 400
    try:
        long_token = threads_api.exchange_code(os.environ["THREADS_APP_ID"], os.environ["THREADS_APP_SECRET"],
                                               _redirect_uri(), code)
    except Exception as e:  # noqa: BLE001
        return "トークン取得に失敗: " + str(e), 500
    threads_api.set_token(long_token)
    saved = threads_api.save_token_to_render(long_token)
    hint = ("Renderの環境変数にも保存した。" if saved else
            "この値を Render の環境変数 THREADS_ACCESS_TOKEN に貼って保存してください（再デプロイされる）。")
    return ("<h2>長期トークン（60日）</h2><p>" + hint + "</p><textarea rows=6 cols=90>" + long_token + "</textarea>"
            "<p>保存したら /check で接続を確認。</p>")


_sched = None
if os.environ.get("DISABLE_SCHEDULER") != "1":
    _sched = BackgroundScheduler(timezone=JST)
    _sched.add_job(post_due, "interval", minutes=5, id="post_due")
    _sched.add_job(refresh_weekly, "cron", day_of_week="mon", hour=4, minute=0, id="refresh")
    _sched.start()
    _note("scheduler started")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "10000")))
