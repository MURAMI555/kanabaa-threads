"""叶ばぁの公式LINE（@492vxwcy）に4項目（名前・生年月日・悩み・願い）が届いたら、約10分後に「届いたよ」を1通だけ自動で送る
（2026/10/31 みかちゃん「きてるよ、ちゃんと届いたよ。ありがとね は自動でおくってほしいな１０分後くらいに」）。

・受付の合図だけ。初視（無料鑑定書）は今までどおり hatsumi で書いて手で送る
・4項目かどうかは、生年月日（8桁・1968.10.21 など）か「①②」「生年月日」が入っていて、ある程度の長さがあるかで見る
・同じ人には3日に1回まで（分けて送ってくる人・追加の質問に何度も送らない）
・待ち時間は8〜12分でばらす。送るのは LINE の push（無料枠の通数を使う）
・止めるときは Render の環境変数 KANABAA_LINE_ACK=0
環境変数：LINE_CHANNEL_SECRET・LINE_CHANNEL_ACCESS_TOKEN（受付箱と同じもの）"""
import os
import random
import re
import threading
import time
from datetime import datetime, timedelta

import requests

from inbox_kit import hizuke

TEXT = "きてるよ、ちゃんと届いたよ。ありがとね"
AGAIN = timedelta(days=3)
_sent: dict = {}      # user_id → 送った時刻（このプロセスの中だけ。再起動で忘れても3日以内の二重は起きにくい）
_wait: set = set()    # いま待っている user_id
_log: list = []


def _note(msg: str):
    _log.append(f"{datetime.now().strftime('%m/%d %H:%M')} {msg}")
    del _log[:-100]
    print("[line_uketsuke] " + msg, flush=True)


def enabled() -> bool:
    return os.environ.get("KANABAA_LINE_ACK", "1") != "0" and bool(os.environ.get("LINE_CHANNEL_ACCESS_TOKEN"))


def looks_like_hearing(text: str) -> bool:
    t = text or ""
    return len(t) >= 15 and bool(hizuke.find_dates(t) or re.search(r"[①②]|生年月日", t))


def _push(uid: str):
    tok = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
    r = requests.post("https://api.line.me/v2/bot/message/push", timeout=20,
                      headers={"Authorization": f"Bearer {tok}"},
                      json={"to": uid, "messages": [{"type": "text", "text": TEXT}]})
    r.raise_for_status()


def _later(uid: str, wait: int):
    time.sleep(wait)
    try:
        _push(uid)
        _sent[uid] = datetime.now()
        _note(f"{uid[-6:]} に「届いたよ」を送った（{wait // 60}分後）")
    except Exception as e:  # noqa: BLE001
        _note(f"{uid[-6:]} への「届いたよ」に失敗: {e} {getattr(getattr(e, 'response', None), 'text', '')[:200]}")
    finally:
        _wait.discard(uid)


def on_event(ev: dict):
    """LINE Webhook のイベント1つ。4項目らしいメッセージなら、8〜12分後に「届いたよ」を送る"""
    if not enabled() or ev.get("type") != "message" or (ev.get("message") or {}).get("type") != "text":
        return
    uid = (ev.get("source") or {}).get("userId")
    if not uid or uid in _wait or (uid in _sent and datetime.now() - _sent[uid] < AGAIN):
        return
    if not looks_like_hearing(ev["message"].get("text", "")):
        return
    wait = random.randint(8 * 60, 12 * 60)
    _wait.add(uid)
    threading.Thread(target=_later, args=(uid, wait), daemon=True).start()
    _note(f"{uid[-6:]} から4項目らしいメッセージ。{wait // 60}分後に「届いたよ」を送る")
