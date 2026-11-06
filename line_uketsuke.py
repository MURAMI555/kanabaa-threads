"""叶ばぁの公式LINE（@492vxwcy）の自動の声かけ（2026/10/31〜・11/01 広げた）。

・4項目（名前・生年月日・悩み・願い）が届いたら
    8〜12分後に 定型文①受付（名前入り・読み物のリンク）だけ送る
    （②読んだかい は 11/03 やめた。みかちゃん「同じような連絡を2回送ってる・連投いらない」）
  （2026/10/31 みかちゃん「届いたよは自動で10分後くらいに」→ 11/01「ライン登録してくれた人も自動で返して」）
・友だち追加したのに4項目が来ない人には、20〜26時間後に1回だけ「4つ書いて送っておくれ」（朝8時〜夜22時のあいだに）
・初視（無料鑑定書）・③翌朝・④夕方からあとは今までどおり手で送る（③④は「今夜届ける」と約束する文なので、
  初視を送ったかどうかが見えない自動では送らない。管理画面のチャットから送った分は Webhook に来ない）
・4項目かどうかは、生年月日（8桁・1968.10.21 など）か「①②」「生年月日」が入っていて、ある程度の長さがあるかで見る
・同じ人には3日に1回まで（分けて送ってくる人・追加の質問に何度も送らない）
・送るのは LINE の push（無料枠の通数を使う）。様子は /line/status
・止めるときは Render の環境変数 KANABAA_LINE_ACK=0（全部止まる）
環境変数：LINE_CHANNEL_SECRET・LINE_CHANNEL_ACCESS_TOKEN（受付箱と同じもの）
※待ち時間はこのプロセスの中で数える。待っている間に再起動（push・Render の入れ替え）があると、その人の分は送られない"""
import os
import random
import re
import threading
import time
from datetime import datetime, timedelta

import pytz
import requests
from inbox_kit import hizuke

JST = pytz.timezone("Asia/Tokyo")
YOMIMONO = "https://kanabaa-hatsumi.netlify.app/yomimono/"
UKETSUKE = ("{n}ちゃんと届いたよ。ありがとね。\n\n"
            "書いてくれた言葉、婆さんが一つずつ読んで視ていくでね。\n"
            "届けるまで1〜3日もらうよ。\n\n"
            "その前に、ひとつだけ読んでおいてほしいもんがある。\n"
            "婆さんがどんな人間で、初視をどう受け取ってほしいかを書いておいた。\n\n"
            "最後まで読んでから初視を開くと、書いてあることがすっと入るでね。\n\n" + YOMIMONO)
UNAGASHI = ("{n}友だちになってくれて、ありがとね。\n\n"
            "初視は、あんたのことを4つ聞いてから視るよ。\n"
            "――――――――――\n"
            "① 呼ばれたい名前\n② 生年月日\n③ いま一番の悩み\n（つらいだろうけど、がんばって100字くらい聞かせておくれ）\n④ 本当はどうなりたいか\n"
            "――――――――――\n"
            "うまく書かんでいいよ。このトークに送っておくれ。届いたら、婆さんが順番に視るでね。")
AGAIN = timedelta(days=3)
_sent: dict = {}      # user_id → 「受付」を送った時刻（このプロセスの中だけ）
_hearing: set = set() # 4項目が来た user_id（友だち追加の声かけを止める）
_wait: set = set()    # いま待っている user_id
_log: list = []


def _note(msg: str):
    _log.append(f"{datetime.now(JST).strftime('%m/%d %H:%M')} {msg}")
    del _log[:-100]
    print("[line_uketsuke] " + msg, flush=True)


def enabled() -> bool:
    return os.environ.get("KANABAA_LINE_ACK", "1") != "0" and bool(os.environ.get("LINE_CHANNEL_ACCESS_TOKEN"))


def looks_like_hearing(text: str) -> bool:
    t = text or ""
    return len(t) >= 15 and bool(hizuke.find_dates(t) or re.search(r"[①②]|生年月日", t))


def _name(uid: str) -> str:
    """LINEの表示名＋「さん、」。取れなければ空（文の頭がそのまま始まる）"""
    tok = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
    try:
        r = requests.get(f"https://api.line.me/v2/bot/profile/{uid}", headers={"Authorization": f"Bearer {tok}"}, timeout=15)
        n = (r.json().get("displayName") or "").strip() if r.ok else ""
    except Exception:  # noqa: BLE001
        n = ""
    return f"{n}さん、" if n and len(n) <= 15 else ""


def _push(uid: str, text: str):
    tok = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
    r = requests.post("https://api.line.me/v2/bot/message/push", timeout=20,
                      headers={"Authorization": f"Bearer {tok}"},
                      json={"to": uid, "messages": [{"type": "text", "text": text}]})
    r.raise_for_status()


def _send(uid: str, text: str, label: str) -> bool:
    try:
        _push(uid, text.format(n=_name(uid)))
        _note(f"{uid[-6:]} に「{label}」を送った")
        return True
    except Exception as e:  # noqa: BLE001
        _note(f"{uid[-6:]} への「{label}」に失敗: {e} {getattr(getattr(e, 'response', None), 'text', '')[:200]}")
        return False


def _hearing_flow(uid: str, wait: int):
    try:
        time.sleep(wait)
        if not enabled() or not _send(uid, UKETSUKE, "①受付"):
            return
        _sent[uid] = datetime.now(JST)
    finally:
        _wait.discard(uid)


def _follow_flow(uid: str):
    wait = random.randint(20 * 3600, 26 * 3600)
    at = datetime.now(JST) + timedelta(seconds=wait)
    if at.hour < 8:      # 夜中にかかったら朝8時台に
        at = at.replace(hour=8, minute=random.randint(0, 59))
    elif at.hour >= 22:  # 夜遅くなら翌朝8時台に
        at = (at + timedelta(days=1)).replace(hour=8, minute=random.randint(0, 59))
    time.sleep(max(0, (at - datetime.now(JST)).total_seconds()))
    if enabled() and uid not in _hearing:
        _send(uid, UNAGASHI, "4つ書いて送っておくれ")


def on_event(ev: dict):
    """LINE Webhook のイベント1つ"""
    if not enabled():
        return
    uid = (ev.get("source") or {}).get("userId")
    if not uid or (ev.get("source") or {}).get("type") != "user":
        return
    if ev.get("type") == "follow":
        threading.Thread(target=_follow_flow, args=(uid,), daemon=True).start()
        _note(f"{uid[-6:]} が友だち追加。4項目が来なければ、約1日後に声をかける")
        return
    if ev.get("type") != "message" or (ev.get("message") or {}).get("type") != "text":
        return
    if not looks_like_hearing(ev["message"].get("text", "")):
        return
    _hearing.add(uid)
    try:  # 続きの③翌朝・④夕方・初視・⑦⑧は hatsumi_auto（11/03〜。予定はシートに置くので再起動しても続く）
        import hatsumi_auto
        hatsumi_auto.start(uid)
    except Exception as e:  # noqa: BLE001
        _note(f"{uid[-6:]} の初視の流れを始められなかった: {e}")
    if uid in _wait or (uid in _sent and datetime.now(JST) - _sent[uid] < AGAIN):
        return
    wait = random.randint(8 * 60, 12 * 60)
    _wait.add(uid)
    threading.Thread(target=_hearing_flow, args=(uid, wait), daemon=True).start()
    _note(f"{uid[-6:]} から4項目らしいメッセージ。{wait // 60}分後に「①受付」を送る")


def status():
    """/line/status（inbox_kit/routes.py から呼ぶ）"""
    state = "動いている" if enabled() else "止まっている（KANABAA_LINE_ACK=0 か LINE_CHANNEL_ACCESS_TOKEN が無い）"
    secret = "あり" if os.environ.get("LINE_CHANNEL_SECRET") else "無し（Webhookが受け取れない）"
    rows = "\n".join(reversed(_log)) or "（まだ何も来ていない）"
    return (f"<pre style='white-space:pre-wrap;font-size:13px'>叶ばぁLINE 自動の声かけ：{state}\nチャネルシークレット：{secret}\n"
            f"4項目→約10分後に①受付（1通だけ）／友だち追加だけの人→約1日後に1回\n\n{rows}</pre>")
