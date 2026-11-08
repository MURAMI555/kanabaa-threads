"""叶ばぁの公式LINE：4項目が届いた人に、初視（無料鑑定書）まで自動で届ける（2026/11/03〜）。
（みかちゃん「初視・翌朝・夕方のメッセージも自動化したい」「初視はクロちゃんが書いて」→ 送る前の確認は A＝夜20時までに止めなければ送る）

流れ（受付＝line_uketsuke の①「届いたよ」を送った時）
  受付から30分ほどたったら（分けて送ってくる人を待つ）、Claude が hatsumi スキルの型で初視を書く → 禁止語チェック
  → みかちゃんにLINEで「◯◯さんの初視できたよ・◯/◯ 21時に送るよ・止めるならここ」
  初視を送る日 D ＝ 受付の翌日（朝5時前の受付は当日）。1日3人まで（4人目からは次の日へ）
    D  8時台   ③翌朝「眠れたかい・今夜届ける」
    D 17時台   ④夕方「もう少しで届けられるよ」
    D 21時台   初視（4,980円は D+8 の24時まで・?d=D）
    D+1 21時台 ⑥視直し（11/03 まりの翌日の一通を叶ばぁ口調に。霊視メモは要らない形）
    D+2 21時台 ⑦迷う人へ（11/03 まりの2通目を移した。「昨日の案内」とつながるので⑥の翌日）（⑥〜⑧とも、初視のあとに返事が来ていたら送らない）
    D+3 21時台 ⑦の2 違い（11/03 まりの3通目。初視と本鑑定の違い）
    D+4 21時台 ⑦の3 よくある質問（11/08 みかちゃん「もっとスパンよく」で毎日1通に）
    D+5 21時台 ⑦の4 読み返し（初視の手が止まるところ）
    D+6 21時台 ⑦の5 あと2日（期限の日付つき）
    D+7 21時台 ⑧前の日（同じ）
・2026/11/07〜 初視だけはみかちゃんが手で送る（みかちゃん決定）。/hatsumi/today に今日送る分の文とリンクをまとめ、「送った」を押すと⑥〜⑧の起点になる。
  翌朝・夕方と⑥〜⑧は自動のまま。KANABAA_HATSUMI_HAND=0 で初視も自動に戻る
・初視は表紙つきのPDFにして、LINEにはリンクを送る（2026/11/07〜・hatsumi_pdf.py）。リンクは推測できない文字列で、送った日から30日で開けなくなる。
  PDFは保存せず、開かれた時に本文から作る。PDFが作れない時と KANABAA_HATSUMI_PDF=0 の時は、これまでどおり本文をそのまま送る
・初視がチェックに引っかかった・書けなかった時は「保留」。③④も初視も送らず、みかちゃんに知らせる
・止める：/hatsumi?pin=…（受付箱と同じ合言葉）の「止める」。全部止めるのは Render の KANABAA_HATSUMI_AUTO=0
・型（スキルの kata.md など）は公開リポに置けないので、受付箱シートの cfg:hatsumi に置く
  （PC の MIKA-AI/.claude/skills/hatsumi/scripts/upload_prompt.py で上げる。型を直したら上げ直す）
・予定は受付箱シートの line:<userId> の行の "auto" に書く（Render が再起動しても消えない）
環境変数：INBOX_STORE_URL・INBOX_STORE_KEY・INBOX_PIN・ANTHROPIC_API_KEY・LINE_CHANNEL_ACCESS_TOKEN・NOTIFY_URL・NOTIFY_TOKEN"""
import html
import os
import random
import re
import secrets
import threading
import traceback
from datetime import datetime, timedelta

import pytz
import requests
from flask import abort, make_response, redirect, request

from inbox_kit import drafts, hizuke, kinshi, seinen, store

JST = pytz.timezone("Asia/Tokyo")
_lock = threading.Lock()
_log: list = []

SAME_DAY_UNTIL = 19               # この時より前に届いた人は、その日の夜に初視を送る
PER_DAY = 3                      # 1日に送る初視の数（全アカウント合計3件までの決まり。叶ばぁはここで守る）
GATHER = timedelta(minutes=30)   # 最後のメッセージからこれだけ待って書く
# 2026/11/06 みかちゃん「今夜は初視10人」：23時〜翌1時半の受付は1時半に送る（1時半を過ぎた受付はいつもの流れ）
TONIGHT_FROM = JST.localize(datetime(2026, 11, 6, 23, 0))
TONIGHT_SEND = JST.localize(datetime(2026, 11, 7, 1, 30))
TONIGHT_MAX = 10
TONIGHT_GATHER = timedelta(minutes=10)
LATE = {"asa": 3, "yu": 3, "hatsumi": 2, "minaoshi": 3, "mayou": 3, "chigai": 3, "shitsumon": 3, "yomikaeshi": 3, "nokori": 3, "mae": 3}  # 予定から何時間遅れまでなら送るか（再起動で遅れた時）
PAGE = "https://kanabaa-hatsumi.netlify.app/honkantei/?d={d}"
PAY_LIMITED = "https://kanabaa.stores.jp/items/6aef248ed168fb2c9f0d96f7"   # 4,980円（デジタル商品・住所入力なし 2026/11/07）
OLD_PAY = "https://kanabaa.stores.jp/items/6ae1ff617851cfc94d4f3d59"   # 11/07 より前に書いた下書きに入っている旧リンク
SITE = "https://kanabaa-threads.onrender.com"
PDF_DAYS = 30                    # 初視PDFのリンクが開ける日数
HATSUMI_MSG = ("{n}さん、初視ができたよ。\n\n"
               "婆さんが視たことを、あんたの分だけ1冊にまとめたでね。\n"
               "一人になれる時間に開いて、最後まで読んでおくれ。\n"
               "▼\n{url}\n\n"
               "読み返したい時のために、スマホに保存しておきな。\n"
               "うまく開けなかったら、このトークに「開けない」と送っておくれ。")

ASA = ("{n}さん、昨夜はちゃんと眠れたかい。\n\n"
       "あんたが書いてくれた言葉、婆さんに届いてるよ。\n今、あんたの分を視てるところだ。\n\n"
       "今夜、このトークに届けるでね。")
YU = ("{n}さん、もう少しで届けられるよ。\n\n"
      "視えたことを、今夜ちゃんと書いて送るでね。\n"
      "同じ言葉でも、落ち着いて読むのと、仕事の合間に読むのとでは届き方が違う。\n"
      "一人になれる時間に開いておくれ。")
MINAOSHI = ("{n}さん\n"
            "\n"
            "初視、\n"
            "ちゃんと\n"
            "受け取れたかい。\n"
            "\n"
            "あそこに書いたのは、\n"
            "今のあんたに\n"
            "届いてる\n"
            "最初のしるしだよ。\n"
            "\n"
            "でも、\n"
            "正直に言うね。\n"
            "\n"
            "初視だけで\n"
            "安心して終わると、\n"
            "また同じところで\n"
            "不安になる人も\n"
            "多いんだ。\n"
            "\n"
            "それは\n"
            "弱いからじゃないよ。\n"
            "\n"
            "まだ、\n"
            "流れが止まってる\n"
            "根っこのところまで\n"
            "視にいけていない\n"
            "だけでね。\n"
            "\n"
            "本鑑定では、\n"
            "\n"
            "なぜ同じ悩みに\n"
            "戻ってくるのか。\n"
            "\n"
            "どの縁や\n"
            "思い込みを\n"
            "ほどいていく必要が\n"
            "あるのか。\n"
            "\n"
            "今いちばん\n"
            "受け取っておくべき\n"
            "言葉は何か。\n"
            "\n"
            "そこまで\n"
            "深く視ていくでね。\n"
            "\n"
            "初視と本鑑定の違いは、\n"
            "ここに\n"
            "まとめておいた。\n"
            "▼\n" + PAGE)
MAYOU = ("{n}さん\n"
         "\n"
         "昨日の案内、\n"
         "少しでも\n"
         "見てくれたかい。\n"
         "\n"
         "ここで迷う人は、\n"
         "ほんとに多いよ。\n"
         "\n"
         "「今じゃなくても\n"
         "いいかな」\n"
         "\n"
         "「初視だけでも\n"
         "十分かな」\n"
         "\n"
         "「あたしが受けて\n"
         "いいのかな」\n"
         "\n"
         "そんなふうに\n"
         "止まるのも\n"
         "当たり前のことだがね。\n"
         "\n"
         "でもね、\n"
         "やさしい人ほど\n"
         "自分のことを\n"
         "後回しにする。\n"
         "\n"
         "人の気持ちは\n"
         "大事にできるのに、\n"
         "自分の本音だけは\n"
         "聞こえないふりを\n"
         "しちまう。\n"
         "\n"
         "本鑑定は、\n"
         "あんたが\n"
         "自分の気持ちを\n"
         "置いてけぼりにしない\n"
         "ためのもんだよ。\n"
         "\n"
         "詳しいページには、\n"
         "初視と本鑑定の違い、\n"
         "迷ってるあんたへの話、\n"
         "受け取るまでの流れまで\n"
         "まとめておいた。\n"
         "▼\n" + PAGE)
CHIGAI = ("{n}さん\n"
          "\n"
          "今日は、\n"
          "初視と\n"
          "本鑑定の違いを\n"
          "ちゃんと伝えるね。\n"
          "\n"
          "初視は、\n"
          "今いちばん\n"
          "表に出てる\n"
          "しるしを視るもの。\n"
          "\n"
          "本鑑定は、\n"
          "その奥にある\n"
          "根っこまで視る。\n"
          "\n"
          "なぜ同じ悩みを\n"
          "繰り返すのか。\n"
          "\n"
          "どの縁が\n"
          "{n}さんの流れを\n"
          "止めてるのか。\n"
          "\n"
          "何を整えると、\n"
          "流れが戻りはじめるのか。\n"
          "\n"
          "今いちばん\n"
          "受け取っておくべき\n"
          "言葉は何か。\n"
          "\n"
          "ここまで視るから、\n"
          "「当たってた」で\n"
          "終わらずに、\n"
          "ここからどう動くか\n"
          "まで受け取れるんだよ。\n"
          "\n"
          "詳しいことは\n"
          "案内のページに\n"
          "まとめておいた。\n"
          "\n"
          "あんたが\n"
          "今どこまで\n"
          "視てほしいか、\n"
          "読んで感じてみな。\n"
          "▼\n" + PAGE)
# 2026/11/08 みかちゃん「追いLINEをもっとスパンよく」→ 空いていた D+4〜D+6 にも毎晩1通（毎日1通の流れ）
SHITSUMON = ("{n}さん\n"
             "\n"
             "本鑑定のことで、\n"
             "よく聞かれることを\n"
             "まとめておくね。\n"
             "\n"
             "――何が届くの？\n"
             "あんたのためだけに書いた\n"
             "「次の一手」を、\n"
             "このトークに届けるよ。\n"
             "3,000〜4,000字くらいだ。\n"
             "\n"
             "――申し込んだら、どうなるの？\n"
             "申し込んだ画面を\n"
             "スクショして送っておくれ。\n"
             "婆さんから4つだけ聞くから、\n"
             "答えてくれたら\n"
             "2〜3日で届けるでね。\n"
             "\n"
             "――払い方は？\n"
             "カード、コンビニ、PayPay残高、\n"
             "楽天ペイ、PayPal、atone が使えるよ。\n"
             "\n"
             "――相手のこと、うまく書けない\n"
             "書ける分だけでいい。\n"
             "まとまってなくていいよ。\n"
             "\n"
             "ほかに聞きたいことがあったら、\n"
             "このトークに\n"
             "そのまま送っておくれ。\n"
             "▼\n" + PAGE)
YOMIKAESHI = ("{n}さん\n"
              "\n"
              "初視、\n"
              "もう一度\n"
              "開いてみたかい。\n"
              "\n"
              "一回目は\n"
              "目で読むもんだ。\n"
              "\n"
              "二回目は、\n"
              "手が止まるところが\n"
              "出てくる。\n"
              "\n"
              "そこが、\n"
              "あんたが\n"
              "いちばん\n"
              "引っかかってるところだよ。\n"
              "\n"
              "本鑑定では、\n"
              "その止まったところを、\n"
              "なんで止まるのか、\n"
              "どう動けばいいのか、\n"
              "いつ動けばいいのか\n"
              "まで視る。\n"
              "\n"
              "止まったところを\n"
              "ひとことだけ\n"
              "このトークに\n"
              "送ってくれてもいいよ。\n"
              "▼\n" + PAGE)
NOKORI = ("{n}さん\n"
          "\n"
          "初視から8日間の\n"
          "4,980円は、\n"
          "{lm}月{ld}日の24時までだよ。\n"
          "あと2日だ。\n"
          "\n"
          "急かすつもりはないけどね、\n"
          "決めないまま過ぎる2日と、\n"
          "決めて過ごす2日とでは、\n"
          "同じ2日でも\n"
          "違うもんだよ。\n"
          "\n"
          "受けるなら、\n"
          "ここからどうぞ。\n"
          "▼\n" + PAGE)
MAE = ("{n}さん、婆さんからはこれで最後にするね。\n\n"
       "初視から8日間の4,980円は、明日の24時までだよ。\nそのあとも受けられるけど、25,000円になる。\n\n"
       "暮らしを削ってまで受けるもんじゃないから、今じゃないと思ったら、それでいい。\n"
       "初視に書いたことは本当のことだから、何度でも読み返しな。\n▼\n" + PAGE)
STAGES = [("asa", "③翌朝"), ("yu", "④夕方"), ("hatsumi", "初視"), ("minaoshi", "⑥視直し"), ("mayou", "⑦迷う人へ"), ("chigai", "⑦の2違い"),
          ("shitsumon", "⑦の3よくある質問"), ("yomikaeshi", "⑦の4読み返し"), ("nokori", "⑦の5あと2日"), ("mae", "⑧前の日")]
NAME = dict(STAGES)
FOLLOW = ("minaoshi", "mayou", "chigai", "shitsumon", "yomikaeshi", "nokori", "mae")  # 初視のあとのフォロー（返事が来たら全部止める）

RULE = """公式LINEに届いた相談に、叶ばぁの「初視（はつみ）」＝無料鑑定書を1通だけ書く。
下に渡す「型」（運用者のスキル・鑑定書の段の型・見本）のとおりに書く。型と口調の決まりがぶつかったら型が勝つ。
・霊視メモは無い。段5は型の「メモなし型」で書く。メモに無い「視えた」は書かない
・段16（料金と期限）は、渡す「段16に貼る文」を一字も変えずにそのまま入れる
・生年月日の星座・数は、渡す計算結果だけを使う。読み取れなかった時は星座と数に触れない
・相談の中身が病気・法律・借金だけなら、そこは占わず「その道の人を頼っておくれ」と1行
・長さは1,800〜2,500字
・出力の1行目は「呼び名 ◯◯」（相談の中に「呼ばれたい名前」があればそれ、無ければLINEの名前を短くしたもの。さんは付けない）、
  2行目は空けて、3行目から鑑定書の本文だけ。前置き・注記・見出しは書かない"""


def _now():
    return datetime.now(JST)


def _s(t: datetime) -> str:
    return t.strftime("%Y-%m-%d %H:%M")


def _t(s: str) -> datetime:
    return JST.localize(datetime.strptime(s, "%Y-%m-%d %H:%M"))


def note(msg: str):
    _log.append(f"{_now().strftime('%m/%d %H:%M')} {msg}")
    del _log[:-100]
    print("[hatsumi_auto] " + msg, flush=True)


def enabled() -> bool:
    return (os.environ.get("KANABAA_HATSUMI_AUTO", "1") != "0" and store.configured() and drafts.configured()
            and bool(os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")))


def tell_mika(text: str):
    """みかちゃんへLINEで知らせる（nurikae-linebot の /notify）"""
    url, tok = os.environ.get("NOTIFY_URL"), os.environ.get("NOTIFY_TOKEN")
    if not (url and tok):
        note("NOTIFY_URL/NOTIFY_TOKEN が無いので、みかちゃんへの知らせは出していない")
        return
    try:
        requests.post(url, json={"text": text[:1900]}, headers={"x-notify-token": tok}, timeout=20).raise_for_status()
    except Exception as e:  # noqa: BLE001
        note(f"みかちゃんへの知らせに失敗: {e}")


def _push(uid: str, text: str):
    tok = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
    r = requests.post("https://api.line.me/v2/bot/message/push", timeout=20,
                      headers={"Authorization": f"Bearer {tok}"},
                      json={"to": uid, "messages": [{"type": "text", "text": text[:5000]}]})
    r.raise_for_status()


def by_hand() -> bool:
    return os.environ.get("KANABAA_HATSUMI_HAND", "1") != "0"


def _hatsumi_message(it: dict, a: dict, now: datetime) -> str:
    """初視として送る文。PDFのリンクを送る。PDFが作れない時はこれまでどおり本文をそのまま送る"""
    a["draft"] = a["draft"].replace(OLD_PAY, PAY_LIMITED)
    if os.environ.get("KANABAA_HATSUMI_PDF", "1") == "0":
        return a["draft"]
    try:
        import hatsumi_pdf
        hatsumi_pdf.render(a["draft"], a["name"], a["plan"]["d"])  # 先に作ってみて、失敗なら本文で送る
        a["pdf_token"] = a.get("pdf_token") or secrets.token_urlsafe(18)
        a["pdf_at"] = _s(now)
        store.put(it)  # リンクが開けるように、送る前に書いておく
        # openExternalBrowser＝LINEの中の画面だとPDFを開けない端末があるので、外のブラウザで開く
        return HATSUMI_MSG.format(n=a["name"], url=f"{SITE}/h/{a['pdf_token']}.pdf?openExternalBrowser=1")
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        note(f"{it['id'][-6:]} の初視PDFを作れなかった: {e}")
        tell_mika(f"【叶ばぁ】{a['name']}さんの初視をPDFにできなかったので、本文をそのまま送るよ（{str(e)[:80]}）")
        return a["draft"]


# ---------------- 受付 ----------------

def start(uid: str):
    """line_uketsuke が①受付を送ったあとに呼ぶ。この人の自動の流れを始める"""
    if not enabled():
        return
    iid = "line:" + uid
    it = store.get(iid) or {"id": iid, "kind": "line", "status": "new", "messages": [], "first": _s(_now())}
    a = it.get("auto") or {}
    if a.get("state") in ("wait", "ready", "hold", "done"):
        return  # すでに流れの中（2回目の相談は手で）
    it["auto"] = {"state": "wait", "uketsuke": _s(_now()), "plan": {}, "sent": {}}
    store.put(it)
    note(f"{uid[-6:]} の初視の流れを始めた")


def _in_tonight(t: datetime) -> bool:
    return TONIGHT_FROM <= t < TONIGHT_SEND


def _tonight_count(items) -> int:
    return sum(1 for it in items.values() if ((it.get("auto") or {}).get("plan") or {}).get("tonight"))


def _plan_tonight() -> dict:
    day = TONIGHT_SEND.date()
    return {"hatsumi": _s(TONIGHT_SEND), "tonight": True,
            **_follow(day), "d": day.strftime("%Y%m%d")}


FOLLOW_DAYS = {"minaoshi": 1, "mayou": 2, "chigai": 3, "shitsumon": 4, "yomikaeshi": 5, "nokori": 6, "mae": 7}


def _follow(day) -> dict:
    """初視の日 day から、毎晩21時台に1通ずつ（D+1〜D+7）"""
    return {k: _at(day + timedelta(days=n), 21, 0, 21, 30) for k, n in FOLLOW_DAYS.items()}


def _add_new_follow(a: dict) -> bool:
    """11/08 より前に予定を作った人にも、まだ先の D+4〜D+6 を足す（過ぎた分は足さない）"""
    d = a["plan"].get("d")
    if not d or "mae" not in a["plan"] or a.get("stop") or "返事が来た" in a.get("skipped", {}).values():
        return False
    day = datetime.strptime(d, "%Y%m%d").date()
    added = False
    for k, v in _follow(day).items():
        if k in ("shitsumon", "yomikaeshi", "nokori") and k not in a["plan"] and _t(v) > _now():
            a["plan"][k] = v
            added = True
    return added


def _day_counts(items) -> dict:
    c = {}
    for it in items.values():
        pl = (it.get("auto") or {}).get("plan") or {}
        h = pl.get("hatsumi")
        if h and not pl.get("tonight"):  # 今夜の10人は1日の上限に数えない
            c[h[:10]] = c.get(h[:10], 0) + 1
    return c


def _at(day, h1, m1, h2, m2) -> str:
    a = h1 * 60 + m1
    b = h2 * 60 + m2
    m = random.randint(a, b)
    return _s(JST.localize(datetime(day.year, day.month, day.day, m // 60, m % 60)))


def _plan(it: dict, items: dict) -> dict:
    # 2026/11/03 みかちゃん「夕方くらいに送ってくれる人はその日の夜に送っちゃおう。夜遅くの人は次の日でいい」
    # 0〜19時に届いた人＝その日の21時台（0〜5時の深夜は前からその日）。19時以降＝次の日の21時台
    uk = _t(it["auto"]["uketsuke"])
    if _in_tonight(uk) and _tonight_count(items) < TONIGHT_MAX:
        return _plan_tonight()
    day = uk.date() if uk.hour < SAME_DAY_UNTIL else uk.date() + timedelta(days=1)
    counts = _day_counts(items)
    while counts.get(day.isoformat(), 0) >= PER_DAY:
        day += timedelta(days=1)
    p = {"asa": _at(day, 8, 0, 8, 59), "yu": _at(day, 17, 0, 17, 59), "hatsumi": _at(day, 21, 0, 21, 40),
         **_follow(day), "d": day.strftime("%Y%m%d")}
    if day == uk.date() and uk.hour >= 5:  # 朝〜夕方に届いてその日に送る人は「昨夜は眠れたかい」の③翌朝を送らない。④夕方は届いて1時間たっていれば
        p.pop("asa")
        if _t(p["yu"]) < uk + timedelta(hours=1):
            p.pop("yu")
    return p


def kigen_text(d: str) -> str:
    day = datetime.strptime(d, "%Y%m%d").date()
    limit = day + timedelta(days=8)
    return ("初視を受け取ったあんたは、今日から8日間、本鑑定を4,980円で受けられるよ。\n"
            f"{limit.month}月{limit.day}日の24時を過ぎたら、25,000円になる。\n\n"
            f"申し込みはここから\n{PAY_LIMITED}\n\n初視と本鑑定の違いは、ここにまとめておいた\n{PAGE.format(d=d)}")


def check(text: str) -> list:
    """叶ばぁの禁止語・口調チェック。リンクの「https:」はコロン扱いにしない"""
    return kinshi.check(re.sub(r"https?://\S+", "", text))


def _kata() -> str:
    c = store.get("cfg:hatsumi")
    return (c or {}).get("text", "")


def write(it: dict):
    """Claude に初視を書かせる。it["auto"] に draft・name・hits を入れる"""
    a = it["auto"]
    kata = _kata()
    if not kata:
        raise RuntimeError("型（cfg:hatsumi）が受付箱シートに無い。PCの upload_prompt.py で上げて")
    msgs = [m["text"] for m in it.get("messages", []) if _t(m["at"]) >= _t(a["uketsuke"]) - timedelta(days=2)]
    text = "\n".join(msgs) or "\n".join(m["text"] for m in it.get("messages", [])[-10:])
    dates = hizuke.find_dates(text)
    calc = seinen.summaries(dates) if dates else "生年月日が読み取れなかった（星座・数には触れない）"
    user = (f"LINEの名前 {it.get('name') or '（なし）'}\n\n相談（LINEで届いた文そのまま）\n{text}\n\n"
            f"生年月日の計算結果（最初が本人、2つ目があれば相手）\n{calc}\n\n霊視メモ なし\n\n"
            f"段16に貼る文（このまま入れる）\n{kigen_text(a['plan']['d'])}")
    system = RULE + "\n\n＝＝＝ 型 ＝＝＝\n" + kata
    out = drafts._ask(system, user, "high")
    first = check(out)
    if first:
        out = drafts._ask(system, user + "\n\n前の下書き\n" + out + "\n\n直すところ " + " / ".join(first) +
                          "\nこれを直した下書きを、1行目の呼び名から書き直して。", "high")
    m = re.match(r"\s*呼び名[\s:：]*(.+?)\n\s*\n(.*)", out, re.S)
    name, body = (m.group(1).strip().removesuffix("さん"), m.group(2).strip()) if m else ((it.get("name") or "")[:10], out)
    hits = check(body)
    if not 1200 <= len(body) <= 4500:
        hits.append(f"{len(body)}字（長さが型と違う）")
    if PAY_LIMITED not in body or PAGE.format(d=a["plan"]["d"]) not in body:
        hits.append("申し込みリンクか期限のリンクが入っていない")
    if kinshi.needs_care(text):
        hits.append("「死にたい」等の言葉がある（占わずに手で）")
    a.update(draft=body, name=name or "あんた", hits=hits, written=_s(_now()))


def _prepare(it: dict, items: dict):
    a = it["auto"]
    a["plan"] = _plan(it, items)
    try:
        write(it)
        a["state"] = "hold" if a["hits"] else "ready"
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        a.update(state="hold", hits=[f"書けなかった: {e}"[:200]])
    store.put(it)
    p = a["plan"]
    link = f"{SITE}/hatsumi"
    if a["state"] == "ready" and p.get("tonight"):
        tell_mika(f"【叶ばぁ】{a['name']}さんの初視ができたよ（{len(a['draft'])}字・今夜{_tonight_count(items)}人目）。1時半に自動で送るよ。\n"
                  f"読む・直す・止めるのはここ\n{link}")
    elif a["state"] == "ready" and by_hand():
        tell_mika(f"【叶ばぁ】{a['name']}さんの初視ができたよ（{len(a['draft'])}字）。\n"
                  f"{p['hatsumi'][5:10].replace('-', '/')} の夜に手で送ってね（翌朝・夕方のひとことは自動）。\n"
                  f"送る文とリンクはここ\n{SITE}/hatsumi/today")
    elif a["state"] == "ready":
        tell_mika(f"【叶ばぁ】{a['name']}さんの初視ができたよ（{len(a['draft'])}字）。\n"
                  f"{p['hatsumi'][5:].replace('-', '/')} に自動で送るよ（翌朝・夕方のひとことも）。\n"
                  f"読む・直す・止めるのはここ（その日の20時までに）\n{link}")
    else:
        tell_mika(f"【叶ばぁ】{a.get('name') or it.get('name')}さんの初視は自動で送らないで止めてるよ。\n"
                  f"理由 {' / '.join(a['hits'])}\nここで直して「送る予定に戻す」か、手で送ってね\n{link}")
    note(f"{it['id'][-6:]} の初視 {a['state']} 送る日 {p['d']}")


# ---------------- 見回り（10分おき） ----------------

def _replied_after(it: dict, t: str) -> bool:
    return any(m["at"] > t for m in it.get("messages", []))


def _due(it: dict, key: str, now: datetime):
    a = it["auto"]
    at = a["plan"].get(key)
    if not at or key in a["sent"] or key in a.get("skipped", {}):
        return False
    t = _t(at)
    if now < t:
        return False
    if now - t > timedelta(hours=LATE[key]):
        a.setdefault("skipped", {})[key] = "遅れた"
        note(f"{it['id'][-6:]} の{NAME[key]}は時間を過ぎたので送らなかった")
        if key == "hatsumi":
            tell_mika(f"【叶ばぁ】{a['name']}さんの初視、時間内に送れなかった（サーバーの入れ替え中だったかも）。手で送ってね\n{SITE}/hatsumi")
        return False
    return True


def tick():
    if not enabled() or not _lock.acquire(blocking=False):
        return
    try:
        now = _now()
        items = store.all_items(max_age=0)
        for it in list(items.values()):
            a = it.get("auto")
            if it.get("kind") != "line" or not a:
                continue
            try:
                _step(it, a, items, now)
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                note(f"{it['id'][-6:]} で失敗: {e}")
    finally:
        _lock.release()


def _step(it, a, items, now):
    tonight_uk = _in_tonight(_t(a["uketsuke"]))
    if a["state"] == "ready" and tonight_uk and not a["plan"].get("tonight") and "hatsumi" not in a["sent"] \
            and not a.get("stop") and now < TONIGHT_SEND and _tonight_count(items) < TONIGHT_MAX:
        # 投稿より先に受け付けて翌日の予定になっていた人も、今夜の1時半へ（期限の日付が違う人は書き直す）
        if a["plan"].get("d") == TONIGHT_SEND.strftime("%Y%m%d"):
            a["plan"] = _plan_tonight()
            store.put(it)
            note(f"{it['id'][-6:]} を今夜の1時半に移した")
        else:
            a["state"] = "wait"
    if a["state"] == "wait":
        last = max([_t(a["uketsuke"])] + [_t(m["at"]) for m in it.get("messages", [])])
        if now - last >= (TONIGHT_GATHER if tonight_uk else GATHER):
            _prepare(it, items)
        if a["state"] != "ready" or not a["plan"].get("tonight"):
            return
    if a["state"] != "ready" or a.get("stop"):
        return
    if it.get("status") == "blocked":
        a["state"] = "done"
        store.put(it)
        return
    if _add_new_follow(a):
        store.put(it)
    hand = by_hand() and "hatsumi" not in a["sent"] and "hatsumi" not in a.get("skipped", {})
    if hand and a["plan"].get("hatsumi") and now - _t(a["plan"]["hatsumi"]) > timedelta(hours=12) and not a.get("hand_late"):
        a["hand_late"] = _s(now)  # 翌朝になっても送っていない時だけ知らせる（1回）
        tell_mika(f"【叶ばぁ】{a['name']}さんの初視がまだ送れていないよ。\n{SITE}/hatsumi/today")
        store.put(it)
    for key, label in STAGES:
        if key == "hatsumi" and hand:
            continue  # 初視はみかちゃんが /hatsumi/today から手で送る
        if not _due(it, key, now):
            continue
        if key in FOLLOW and "hatsumi" not in a["sent"]:
            if not hand:
                a.setdefault("skipped", {})[key] = "初視を自動で送っていない"
            continue
        if key in FOLLOW and _replied_after(it, a["sent"]["hatsumi"]):
            for k in FOLLOW:
                a.setdefault("skipped", {})[k] = "返事が来た"
            tell_mika(f"【叶ばぁ】{a['name']}さんから初視のあとに返事が来てるよ。⑥〜⑧の自動は止めたから、返事は手でね（「開けない」と来ていたら、{SITE}/hatsumi の本文を貼って送ってね）\nhttps://chat.line.biz/")
            break
        n = a["name"]
        lim = datetime.strptime(a["plan"]["d"], "%Y%m%d") + timedelta(days=8)
        text = {"asa": ASA, "yu": YU, "minaoshi": MINAOSHI, "mayou": MAYOU, "chigai": CHIGAI, "shitsumon": SHITSUMON,
                "yomikaeshi": YOMIKAESHI, "nokori": NOKORI, "mae": MAE}.get(key, "").format(
                    n=n, d=a["plan"]["d"], lm=lim.month, ld=lim.day) \
            if key != "hatsumi" else _hatsumi_message(it, a, now)
        try:
            _push(it["id"][5:], text)
            a["sent"][key] = _s(now)
            note(f"{it['id'][-6:]} に{label}を送った")
        except Exception as e:  # noqa: BLE001
            note(f"{it['id'][-6:]} への{label}に失敗: {e}")
            if key == "hatsumi":
                tell_mika(f"【叶ばぁ】{n}さんへの初視の自動送信に失敗した（{str(e)[:80]}）。手で送ってね")
                a.setdefault("skipped", {})["hatsumi"] = "失敗"
        break  # 1回の見回りで1人1通まで
    if all(k in a["sent"] or k in a.get("skipped", {}) or k not in a["plan"] for k, _ in STAGES):  # ⑥を足す前の予定には minaoshi が無い
        a["state"] = "done"
    store.put(it)


# ---------------- 初視PDF ----------------

def _pdf_response(pdf: bytes):
    r = make_response(pdf)
    r.headers.update({"Content-Type": "application/pdf", "Content-Disposition": 'inline; filename="hatsumi.pdf"',
                      "Cache-Control": "private, no-store", "X-Robots-Tag": "noindex, nofollow", "Referrer-Policy": "no-referrer"})
    return r


def _gone(text: str, code: int):
    r = make_response(f'<!doctype html><html lang=ja><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">'
                      f'<meta name=robots content=noindex><title>叶ばぁ</title><body style="font-family:serif;padding:32px 20px;'
                      f'background:#f2ece1;color:#26354a;line-height:1.9">{text}</body></html>', code)
    r.headers.update({"X-Robots-Tag": "noindex, nofollow", "Cache-Control": "no-store"})
    return r


def pdf_public(token: str):  # /h/<token>.pdf（LINEで送ったリンク。合言葉なし・文字列を知っている人だけ）
    found = None
    if store.configured() and re.fullmatch(r"[A-Za-z0-9_-]{20,}", token):
        for it in store.all_items(max_age=60).values():
            a = it.get("auto") or {}
            if a.get("pdf_token") and secrets.compare_digest(a["pdf_token"], token):
                found = a
                break
    if not found or not found.get("pdf_at") or not found.get("draft"):
        return _gone("このリンクは開けないよ。お手数だけど、婆さんのLINEに「開けない」と送っておくれ。", 404)
    if _now() - _t(found["pdf_at"]) > timedelta(days=PDF_DAYS):
        return _gone("このリンクは期限が過ぎて開けなくなったよ。読み返したい時は、婆さんのLINEに一言送っておくれ。", 410)
    import hatsumi_pdf
    return _pdf_response(hatsumi_pdf.render(found["draft"], found.get("name") or "あんた", found["plan"]["d"]))


def pdf_preview():  # /hatsumi/pdf?id=…（みかちゃんが送る前に見る。合言葉あり）
    if not _pin_ok():
        abort(401)
    it = store.get(request.args.get("id", ""))
    a = (it or {}).get("auto") or {}
    if not a.get("draft"):
        abort(404)
    import hatsumi_pdf
    d = (a.get("plan") or {}).get("d") or _now().strftime("%Y%m%d")
    return _pdf_response(hatsumi_pdf.render(a["draft"].replace(OLD_PAY, PAY_LIMITED), a.get("name") or "あんた", d))


def pdf_mihon():  # /hatsumi/mihon.pdf（架空の「ゆいさん」の見本。スマホで開けるかの確認用。お客様の情報は入っていない）
    m = re.search(r"■ 見本.*?```\n(.*?)```", _kata() if store.configured() else "", re.S)
    if not m:
        abort(404)
    import hatsumi_pdf
    return _pdf_response(hatsumi_pdf.render(m.group(1), "ゆい", _now().strftime("%Y%m%d")))


# ---------------- 手で送る分 /hatsumi/today ----------------

def _unsent(it: dict) -> bool:
    a = it.get("auto") or {}
    return (it.get("kind") == "line" and a.get("state") == "ready" and not a.get("stop") and a.get("draft")
            and (a.get("plan") or {}).get("hatsumi") and "hatsumi" not in a.get("sent", {}) and "hatsumi" not in a.get("skipped", {}))


def _hand_text(it: dict, a: dict) -> str:
    """手で送る文。リンクは最初に作ったものを使い回す"""
    if a.get("pdf_token") and os.environ.get("KANABAA_HATSUMI_PDF", "1") != "0":
        return HATSUMI_MSG.format(n=a["name"], url=f"{SITE}/h/{a['pdf_token']}.pdf?openExternalBrowser=1")
    return _hatsumi_message(it, a, _now())


def today():  # /hatsumi/today（今日みかちゃんが手で送る初視のまとめ。合言葉あり）
    from inbox_kit.routes import _set_pin
    if not _pin_ok():
        return make_response('<form><input name="pin" type="password" placeholder="合言葉"><button>開く</button></form>', 401)
    e = html.escape
    now = _now()
    day = now.strftime("%Y-%m-%d")
    items = [i for i in store.all_items(max_age=10).values() if i.get("kind") == "line" and i.get("auto")]
    unsent = sorted((i for i in items if _unsent(i)), key=lambda i: i["auto"]["plan"]["hatsumi"])
    pin = request.values.get("pin", "")
    pin_input = f'<input type=hidden name=pin value="{e(pin)}">' if pin else ""
    cards = []
    for it in unsent:
        a = it["auto"]
        if a["plan"]["hatsumi"][:10] > day:
            continue
        text = _hand_text(it, a)
        limit = datetime.strptime(a["plan"]["d"], "%Y%m%d") + timedelta(days=8)
        late = "<b class=warn>送る日を過ぎているよ</b> " if a["plan"]["hatsumi"][:10] < day else ""
        pdf = (f'<a class=btn href="{e(SITE)}/h/{e(a["pdf_token"])}.pdf" target="_blank">PDFを見る</a>'
               if a.get("pdf_token") else '<b class=warn>PDFにできなかったので本文を送るよ</b>')
        cards.append(f'<div class=card><p class=h>{late}{e(a["name"])}さん <small>LINEの名前 {e(it.get("name") or "")}</small></p>'
                     f'<p><small>4,980円は{limit.month}/{limit.day}まで</small></p><textarea readonly rows=9>{e(text)}</textarea>'
                     f'<p><button type=button class=copy>文をコピー</button> {pdf} <a class=btn href="https://chat.line.biz/" target="_blank">LINEを開く</a></p>'
                     f'<form method=post action="act">{pin_input}<input type=hidden name=id value="{e(it["id"])}"><input type=hidden name=op value=sent>'
                     f'<button class=done>送った</button></form></div>')
    later = [f'{i["auto"]["plan"]["hatsumi"][5:10].replace("-", "/")} {e(i["auto"]["name"])}さん' for i in unsent if i["auto"]["plan"]["hatsumi"][:10] > day]
    autos = []
    for it in items:
        a = it["auto"]
        if a.get("state") != "ready" or a.get("stop"):
            continue
        for k, lab in STAGES:
            at = (a.get("plan") or {}).get(k, "")
            if k != "hatsumi" and at[:10] == day and k not in a.get("sent", {}) and k not in a.get("skipped", {}):
                autos.append((at[11:], f'{at[11:]} {e(a.get("name") or "")}さん {lab}'))
    hold = sum(1 for i in items if i["auto"].get("state") == "hold")
    body = "".join(cards) or "<p>今日手で送る初視は、今のところ無いよ。</p>"
    r = make_response(f"""<!doctype html><html lang=ja><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><meta name=robots content=noindex><title>今日送る初視</title>
<style>body{{font-family:sans-serif;margin:0;padding:12px 16px;background:#f6f3ee;color:#222;font-size:15px}}
.card{{background:#fff;border-radius:10px;padding:10px 12px;margin:12px 0}} .h{{font-weight:bold;margin:0 0 4px}} .h small{{font-weight:normal;color:#777}}
p{{margin:6px 0}} textarea{{width:100%;box-sizing:border-box;font-size:14px}} .warn{{color:#c33}}
button,.btn{{display:inline-block;font-size:15px;padding:9px 14px;margin:4px 4px 0 0;border:1px solid #bbb;border-radius:8px;background:#fafafa;color:#222;text-decoration:none}}
.copy,.done{{background:#1f3350;color:#fff;border-color:#1f3350}} .done{{background:#06c755;border-color:#06c755;width:100%}}
ul{{padding-left:18px;margin:6px 0;color:#555;font-size:14px}}</style></head><body>
<h1 style="font-size:18px">今日送る初視 {sum(1 for i in unsent if i["auto"]["plan"]["hatsumi"][:10] <= day)}人</h1>
<p><small>文をコピー → LINEで相手を開いて貼る → 送ったら「送った」を押す。⑥〜⑧はここから数えて自動で続くよ。</small></p>
{body}
{f'<p class=warn>保留の人が{hold}人いるよ。<a href="../hatsumi">直す画面へ</a></p>' if hold else ''}
{'<h2 style="font-size:15px">明日からの初視（まだ送らない）</h2><ul>' + ''.join(f'<li>{x}</li>' for x in later) + '</ul>' if later else ''}
{'<h2 style="font-size:15px">今日の自動（手で送らなくていいよ）</h2><ul>' + ''.join(f'<li>{x[1]}</li>' for x in sorted(autos)) + '</ul>' if autos else ''}
<script>document.querySelectorAll('.copy').forEach(function(b){{b.onclick=function(){{
var t=b.closest('.card').querySelector('textarea');t.select();t.setSelectionRange(0,99999);
var ok=function(){{b.textContent='コピーしたよ';setTimeout(function(){{b.textContent='文をコピー'}},2000)}};
if(navigator.clipboard){{navigator.clipboard.writeText(t.value).then(ok,function(){{document.execCommand('copy');ok()}})}}else{{document.execCommand('copy');ok()}}
}}}});</script></body></html>""")
    return _set_pin(r)


# ---------------- 画面 /hatsumi ----------------

def _pin_ok() -> bool:
    from inbox_kit.routes import _pin_ok as ok
    return ok()


ST = {"wait": "書く前（30分待ち）", "ready": "送る予定", "hold": "保留（自動で送らない）", "done": "終わり"}


def page():  # /hatsumi（inbox_kit/routes.py の bp に付ける）
    if not _pin_ok():
        return make_response('<form><input name="pin" type="password" placeholder="合言葉"><button>開く</button></form>', 401)
    if not store.configured():
        return "受付箱の置き場（INBOX_STORE_URL / INBOX_STORE_KEY）が未設定"
    e = html.escape
    items = [i for i in store.all_items(max_age=10).values() if i.get("kind") == "line" and i.get("auto")]
    items.sort(key=lambda i: i["auto"].get("uketsuke", ""), reverse=True)
    cards = []
    for it in items[:30]:
        a, iid = it["auto"], e(it["id"])
        p = a.get("plan") or {}
        rows = "".join(f"<li>{lab} {e(p.get(k, '')[5:])} "
                       f"{'✅' + e(a['sent'][k][11:]) if k in a.get('sent', {}) else ('⏭' + e(a['skipped'][k]) if k in a.get('skipped', {}) else '')}</li>"
                       for k, lab in STAGES)
        stop = " <b style='color:#c33'>止めてある</b>" if a.get("stop") else ""
        hits = f"<p class=warn>{e(' / '.join(a.get('hits') or []))}</p>" if a.get("hits") else ""
        btn = lambda op, lab: (f'<form method=post action="hatsumi/act" class=in><input type=hidden name=id value="{iid}">'
                               f'<input type=hidden name=op value="{op}"><button>{lab}</button></form>')
        acts = btn("go", "止めるのをやめる") if a.get("stop") else btn("stop", "止める")
        if a.get("state") == "hold":
            acts += btn("ready", "このまま送る予定に戻す")
        acts += btn("rewrite", "書き直す")
        draft = a.get("draft", "")
        if draft:
            acts += f' <a href="hatsumi/pdf?id={iid}" target="_blank">PDFを見る</a>'
        ed = (f'<form method=post action="hatsumi/act"><input type=hidden name=id value="{iid}"><input type=hidden name=op value=save>'
              f'<textarea name=draft rows=18>{e(draft)}</textarea><button>直したのを保存</button> <small>{len(draft)}字</small></form>') if draft else ""
        msgs = "<br>".join(e(m["text"]) for m in it.get("messages", [])[-6:])
        cards.append(f"<div class=card><p class=h>{e(a.get('name') or it.get('name') or '')}さん "
                     f"<span class=tag>{ST.get(a.get('state'), a.get('state'))}</span>{stop}</p>"
                     f"<details><summary>届いた相談</summary><div class=body>{msgs}</div></details>"
                     f"<ul>{rows}</ul>{hits}<p>{acts}</p>{ed}</div>")
    body = "".join(cards) or "<p>まだ誰も来ていないよ。</p>"
    logs = "<br>".join(e(x) for x in reversed(_log[-15:]))
    return make_response(f"""<!doctype html><html lang=ja><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><meta name=robots content=noindex><title>叶ばぁ 初視の自動</title>
<style>body{{font-family:sans-serif;margin:0;padding:12px 16px;background:#f6f3ee;color:#222;font-size:15px}}
.card{{background:#fff;border-radius:10px;padding:10px 12px;margin:12px 0}} .h{{font-weight:bold;margin:0 0 6px}}
.tag{{font-weight:normal;font-size:12px;background:#eee;border-radius:8px;padding:1px 8px}} .body{{white-space:pre-wrap;font-size:14px}}
textarea{{width:100%;box-sizing:border-box;font-size:15px}} button{{font-size:14px;padding:6px 12px;margin:4px 4px 0 0}}
form.in{{display:inline}} .warn{{color:#c33;font-size:13px}} ul{{padding-left:18px;margin:6px 0}}</style></head><body>
<h1 style="font-size:18px">叶ばぁ 初視の自動</h1>
<p><small>自動：{'動いている' if enabled() else '止まっている（設定が足りないか KANABAA_HATSUMI_AUTO=0）'}。
{'初視は手で送る。<a href="hatsumi/today">今日送る分はここ</a>。' if by_hand() else '初視はその日の21時台に、PDFのリンクで送る。止めたい人は20時までに「止める」。'}</small></p>{body}
<p><small>{logs}</small></p></body></html>""")


def act():  # POST /hatsumi/act
    if not _pin_ok():
        abort(401)
    it = store.get(request.form.get("id", ""))
    if not it or not it.get("auto"):
        abort(404)
    a, op = it["auto"], request.form.get("op")
    if op == "sent":  # /hatsumi/today の「送った」
        a["sent"]["hatsumi"] = _s(_now())
        a["pdf_at"] = _s(_now())  # リンクの30日はここから数える
        store.put(it)
        note(f"{it['id'][-6:]} の初視を手で送った")
        return redirect("today")
    if op == "stop":
        a["stop"] = _s(_now())
    elif op == "go":
        a.pop("stop", None)
    elif op == "save":
        a["draft"] = request.form.get("draft", "").replace("\r\n", "\n").strip()
        a["hits"] = check(a["draft"])
        a["edited"] = _s(_now())
    elif op == "ready":
        a["state"] = "ready"
        a["hits"] = []
    elif op == "rewrite":
        a["plan"] = a.get("plan") or _plan(it, store.all_items())
        try:
            write(it)
        except Exception as e:  # noqa: BLE001
            a["hits"] = [f"書けなかった: {e}"[:200]]
        a["state"] = "hold" if a["hits"] else "ready"
    store.put(it)
    return redirect("../hatsumi")


def status():  # /hatsumi/status
    """合言葉なしで見られる様子（名前・中身は出さない）"""
    items = [i for i in store.all_items().values() if i.get("kind") == "line" and i.get("auto")] if store.configured() else []
    return {"enabled": enabled(), "store": store.configured(), "ai": drafts.configured(),
            "notify": bool(os.environ.get("NOTIFY_URL")), "kata": bool(_kata()) if store.configured() else False,
            "people": [{"state": i["auto"].get("state"), "d": (i["auto"].get("plan") or {}).get("d"),
                        "sent": sorted(i["auto"].get("sent", {}))} for i in items],
            "log": _log[-20:]}
