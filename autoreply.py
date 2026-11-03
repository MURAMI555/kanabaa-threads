"""叶ばぁの「置かせる」投稿へのコメントに、自然な間をあけて自動で返す（2026/10/28 みかちゃん指示・本部OK）。

受付箱（inbox_kit）と違って AI もデータ置き場も使わない。返信は型から組み立てる（同じ文の使い回しにならないよう、言い回しを人ごとに選ぶ）。
・対象：叶ばぁの直近48時間の投稿のうち「置いていきな」を含むもの。
  型：生年月日8桁（動いていい日）／出会った月／漢字一字／彼の誕生日4桁→星座の11月の癖／2人の生まれ月→噛み合わせ／
      彼の誕生日の「日」→待たせ方の癖／最後に会ってから何日→温度／8桁＋「手放す」→この冬手放す癖（3週目 11/2〜11/8・2026/10/31 追加）
  お題の言葉に型が無い投稿でも、コメントの中身（8桁の日付・1〜12の数字・漢字）で返し方を選ぶ（10/31〜）
・フォローの呼びかけ・「また次も」の一言は書かない（10/31に入れたが、11/02 みかちゃん「言わなくていい」でやめた）
・返すのは、投稿に直接ついたコメントで、まだ叶ばぁが返していないものだけ（手で返した分も API で見えるので二重にならない）
・叶ばぁの返信にさらに返してくれた人（2往復目）にも1回だけ返す：お礼→短く／LINEに送った→届いてるよ／身の上話→受け止め＋プロフィールのリンク。重い言葉は手で（2026/11/01〜）
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
OKASE = re.compile(r"置いていきな|置いてきな|置きな")  # 置かせ投稿の目印（言い方が少し変わっても拾う）
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
    if len(n) > 10 and "_" in n.strip("_"):  # iamyu_chan_desu → iamyu
        n = n.strip("_").split("_")[0]
    return n


def pick(options: list, used, rnd: random.Random) -> str:
    """同じ投稿でもう使った言い回しを避けて1つ選ぶ（全部使っていたら一番使っていないもの）"""
    opts = options[:]
    rnd.shuffle(opts)
    return min(opts, key=lambda o: sum(o in u for u in used))


def birth_reply(username: str, s: str, today: date, rnd: random.Random, used=()) -> str:
    d, kind = ugoku(s, today)
    name, _ = seinen.zodiac(date(int(s[:4]), int(s[4:6]), int(s[6:8])))
    lp = seinen.life_path(s)
    label, advice = HI[kind]
    next_week = d - timedelta(days=d.weekday()) > today - timedelta(days=today.weekday())
    when = f"{'来週' if next_week else ''}{d.day}日の{seinen.YOUBI[d.weekday()]}曜"
    lines = [pick(HEAD, used, rnd).format(n=name_of(username)),
             f"あんたが動いていいのは、{when}。",
             f"{name}で{lp}の人は、{HITO[lp]}{rnd.choice(GOBI)}{seinen.YOUBI[d.weekday()]}曜は「{label}」の巡り。{pick(advice, used, rnd)}",
             pick(TEASE, used, rnd)]
    return "\n".join(lines)


TSUKI = {  # 月ごとに3通り。同じ月の人が続いても同じ文にしない（10/28 みかちゃん）
    1: ["1月の縁は、始まりの縁。どちらかが手を引いて進む流れだよ。",
        "1月に出会った2人は、どちらかが先に決めて動く流れ。引っ張る側と待つ側が、はっきり分かれやすいよ。",
        "1月の縁は、新しいことと一緒に始まった縁。勢いはあるけど、立ち止まると迷いやすいね。"],
    2: ["2月に出会った2人は、言葉より空気で分かり合う流れ。そのぶん、言わないことが溜まりやすい。",
        "2月の縁は、そばにいるだけで落ち着く流れ。ただ、遠慮が続くと距離が縮まらないんだよ。",
        "2月に始まった2人は、相手に合わせ合う流れ。優しいぶん、本音が後回しになりやすいね。"],
    3: ["3月の縁は、話して笑って近づく流れ。楽しい時は早いけど、真面目な話を後回しにしがちだね。",
        "3月に出会った2人は、言葉で近づく流れ。連絡が弾む時と止まる時の差が大きいんだよ。",
        "3月の縁は、明るく始まる縁。軽く見えて、実は相手の一言を長く覚えてる流れだね。"],
    4: ["4月に出会った2人は、ゆっくり積み上げる流れ。急には進まないぶん、崩れにくい縁だよ。",
        "4月の縁は、約束を一つずつ守って深まる流れ。小さな約束が崩れると、気持ちも止まりやすいよ。",
        "4月に始まった2人は、地に足のついた流れ。派手さはないけど、時間が味方になる縁だね。"],
    5: ["5月に出会った2人は、会うたびに何か新しいことが起きる流れ。退屈はしないけど、落ち着く前に次の動きが入りやすいんだよ。",
        "5月の縁は、自由でいられる時ほどうまくいく流れ。縛ろうとすると、相手の足が遠のきやすいよ。",
        "5月に始まった2人は、動きの多い流れ。会う間隔が空いても、それだけで終わる縁じゃないね。"],
    6: ["6月の縁は、情で結ばれる流れ。相手の世話を焼くほど、自分の気持ちを言いそびれやすい。",
        "6月に出会った2人は、世話を焼き合う流れ。優しさが重なるほど、言えないことも増えやすいよ。",
        "6月の縁は、暮らしに近いところで深まる縁。特別な日より、普段の一言が効く流れだね。"],
    7: ["7月に出会った2人は、近いようで少し距離のある流れ。一人の時間を許し合えるかが分かれ目だね。",
        "7月の縁は、一人の時間を大事にする2人の流れ。連絡が少なくても、気持ちが冷めたとは限らないよ。",
        "7月に始まった2人は、ゆっくり本音に近づく流れ。急かすと扉が閉まりやすいね。"],
    8: ["8月の縁は、暮らしの事情が動かす流れ。仕事や住まいで、距離が変わりやすいんだよ。",
        "8月に出会った2人は、現実の事情に揺られる流れ。気持ちより先に、時間と場所が距離を決めやすいよ。",
        "8月の縁は、力のある縁。どちらが舵を握るかで、流れががらっと変わるね。"],
    9: ["9月に出会った2人は、何かを手放した後に深まる流れ。区切りと始まりが重なる縁だね。",
        "9月の縁は、手放すことで近づく流れ。握りしめるほど、相手は息苦しくなりやすいよ。",
        "9月に始まった2人は、古い何かと入れ替わるように出会った縁。昔のことが片づくと流れが動くね。"],
    10: ["10月の縁は、どちらが先に動くかで先が決まる流れ。待ち合いになると止まりやすいよ。",
         "10月に出会った2人は、先に動いたほうが流れを作る縁。様子見が長いと、そのまま止まりやすいよ。",
         "10月の縁は、始まりの気配をまとった縁。一度区切りがあっても、もう一度動き出しやすい流れだね。"],
    11: ["11月に出会った2人は、気持ちが通じるのが早い。そのぶん、近づいたり離れたりの波も大きい流れだよ。",
         "11月の縁は、理屈より先に気持ちが動く縁。言葉にしなくても伝わってる、と思い込みやすいのが癖だね。",
         "11月に始まった2人は、勘で引き合う流れ。会った瞬間に何か感じたなら、その勘は大事にしな。勘の強い縁ほど、すれ違いも大きく感じるもんだよ。"],
    12: ["12月に出会った2人は、振り返る時間の多い流れ。思い出が濃いぶん、過去に引っ張られやすいね。",
         "12月の縁は、一年の終わりに結ばれた縁。季節の区切りごとに、気持ちを確かめたくなる流れだよ。",
         "12月に始まった2人は、思い出の濃い流れ。昔の話が増えた時は、今の話を一つ足しな。"],
}
IMA = ["今のあんたは、相手の出方を待ってるように視えるね。", "今のあんたは、言いたいことを飲み込んでるように視える。",
       "今のあんたは、気持ちが少し先に行ってるように視えるね。", "今は、波の引いてるところに視える。引いてる時に追うと、相手は余計に遠くなるからね。",
       "今のあんたは、相手の本音を確かめたくて落ち着かないように視える。", "今は、2人の間に少し遠慮が挟まってるように視えるね。"]


def month_reply(username: str, m: int, rnd: random.Random, used=()) -> str:
    return "\n".join([pick(HEAD, used, rnd).format(n=name_of(username)), pick(TSUKI[m], used, rnd),
                      pick(IMA, used, rnd), pick(TEASE, used, rnd)])


KANJI = {  # 「今の気持ちを漢字一字で」（10/29〜）。一字ごとに2通り＝その字の読み。続けて HOSHII（欲しい言葉）
    "待": ["「待」の一字だね。待てるのは、あんたの気持ちが本物だからだよ。",
          "「待」か。待つ時間が長いと、自分の値打ちまで小さく思えてくるもんだ。でもね、待てる人は弱い人じゃないよ。"],
    "迷": ["「迷」の一字だね。迷うのは、どっちも大事にしたいからだよ。",
          "「迷」か。迷ってる時は、答えが無いんじゃない。答えを出すのが怖いだけのことが多いんだよ。"],
    "恋": ["「恋」の一字だね。まっすぐな字を置いたね。今のあんたは、気持ちを隠さなくていい時だよ。",
          "「恋」か。言い訳をしない一字だね。好きな気持ちを、恥ずかしがらなくていいんだよ。"],
    "疲": ["「疲」の一字だね。よくここまで頑張ってきたね。",
          "「疲」か。疲れたって言えるのは、ちゃんと向き合ってきた証拠だよ。"],
    "愛": ["「愛」の一字だね。与える側に回ってばかりじゃないかい。",
          "「愛」か。大きな字を置いたね。人を想える心は、それだけで値打ちがあるんだよ。"],
    "寂": ["「寂」の一字だね。寂しいと認められるのは、強い人だよ。",
          "「寂」か。夜になると、その字は余計に重たくなるもんだね。"],
    "淋": ["「淋」の一字だね。淋しいと認められるのは、強い人だよ。",
          "「淋」か。夜になると、その字は余計に重たくなるもんだね。"],
    "会": ["「会」の一字だね。会いたい気持ちは、我慢するほど大きくなるもんだ。",
          "「会」か。顔を見れば分かることが、文字だと分からないんだよね。"],
    "逢": ["「逢」の一字だね。会いたい気持ちは、我慢するほど大きくなるもんだ。",
          "「逢」か。顔を見れば分かることが、文字だと分からないんだよね。"],
    "苦": ["「苦」の一字だね。苦しいのに、まだ手放してないんだね。",
          "「苦」か。苦しい恋ほど、真剣な恋なんだよ。"],
    "辛": ["「辛」の一字だね。辛いのに、まだ投げ出してないんだね。",
          "「辛」か。辛いって字を置けただけで、少し前に進んでるよ。"],
    "不": ["「不」の一字だね。不安の『不』かい。確かめたいことが、胸に溜まってるね。",
          "「不」か。答えの出ないことを、ずっと一人で抱えてるね。"],
    "悩": ["「悩」の一字だね。悩むのは、ちゃんと考えてる証拠だよ。",
          "「悩」か。同じところをぐるぐる回ってる気がしてるね。"],
    "諦": ["「諦」の一字だね。諦めたい気持ちと、諦めきれない気持ちが、まだ両方あるね。",
          "「諦」か。本当に諦めた人は、この字を置かないもんだよ。"],
    "願": ["「願」の一字だね。願う気持ちを、恥ずかしがらなくていい。",
          "「願」か。まっすぐな字だね。願いを持てる人は、まだ前を向いてるよ。"],
    "信": ["「信」の一字だね。信じたい気持ちと、確かめたい気持ちの間にいるね。",
          "「信」か。信じるって、実は一番体力がいることなんだよ。"],
    "幸": ["「幸」の一字だね。幸せになりたいって、遠慮なく言っていいんだよ。",
          "「幸」か。その字を置けるあんたは、まだ明るい方を見てるね。"],
    "怖": ["「怖」の一字だね。怖いのは、失いたくないものがあるからだよ。",
          "「怖」か。怖いと言えたなら、半分は越えてるもんだよ。"],
    "焦": ["「焦」の一字だね。周りと比べて、気持ちだけ先に走ってるね。",
          "「焦」か。焦ってる時ほど、一つ深呼吸してからでいいんだよ。"],
    "無": ["「無」の一字だね。何も感じないくらい、気持ちが疲れてるのかもしれないね。",
          "「無」か。空っぽに見える時は、心が休みたがってる時だよ。"],
    "楽": ["「楽」の一字だね。いい字だ。今の気持ちを、ちゃんと大事にしな。",
          "「楽」か。楽しめてる時のあんたは、一番いい顔をしてるはずだよ。"],
    "嬉": ["「嬉」の一字だね。いい字だ。その気持ちを、相手にも少し分けてやりな。",
          "「嬉」か。嬉しいことは、言葉にするともっと大きくなるよ。"],
    "好": ["「好」の一字だね。まっすぐな字を置いたね。好きな気持ちを隠さなくていい。",
          "「好」か。シンプルな字ほど、気持ちが本物なんだよ。"],
    "泣": ["「泣」の一字だね。泣ける場所があるのは、悪いことじゃないよ。",
          "「泣」か。涙が出るのは、心がまだ動いてる証拠だよ。"],
    "涙": ["「涙」の一字だね。泣ける場所があるのは、悪いことじゃないよ。",
          "「涙」か。涙が出るのは、心がまだ動いてる証拠だよ。"],
    "耐": ["「耐」の一字だね。ずいぶん長いこと、我慢してきたね。",
          "「耐」か。耐えてばかりだと、自分の声が聞こえなくなるもんだよ。"],
    "想": ["「想」の一字だね。言葉にしてない想いが、たくさん溜まってるね。",
          "「想」か。想う時間の長さは、気持ちの深さそのものだよ。"],
    "思": ["「思」の一字だね。言葉にしてない思いが、たくさん溜まってるね。",
          "「思」か。思う時間の長さは、気持ちの深さそのものだよ。"],
    "心": ["「心」の一字だね。いちばん大事なものを、そのまま置いたね。",
          "「心」か。心ごと置いていったね。ちゃんと受け取ったよ。"],
    "望": ["「望」の一字だね。望みを持てる人は、まだ前を向いてるよ。",
          "「望」か。望む気持ちを、小さくしなくていいんだよ。"],
    "希": ["「希」の一字だね。希望の『希』かい。前を向く字を置いたね。",
          "「希」か。その字を選べるあんたは、まだ明るい方を見てるね。"],
}
KANJI_OMOI = set("鬱死殺消絶病傷壊孤痛憎恨呪闇")  # 型で軽く返すと失礼になる字は手で
KANJI_ANY = ["「{k}」の一字だね。その字を選んだ時の気持ちごと、ちゃんと受け取ったよ。",
             "「{k}」か。たった一字に、今のあんたがよく出てるね。"]
HOSHII = [
    "あんたが今いちばん欲しいのは、「もう十分頑張ってる」って言葉に視えるよ。",
    "あんたが今いちばん欲しいのは、「あんたのせいじゃない」って言葉に視えるね。",
    "あんたが今いちばん欲しいのは、「そのままでいい」って一言に視えるよ。",
    "あんたが今いちばん欲しいのは、「ちゃんと想われてる」って安心に視えるね。",
    "あんたが今いちばん欲しいのは、「焦らなくていい」って言葉に視えるよ。",
    "あんたが今いちばん欲しいのは、「自分の気持ちを優先していい」って許しに視えるね。",
]


def kanji_of(comment: str):
    m = re.search(r"[一-鿿]", unicodedata.normalize("NFKC", comment))
    return m.group(0) if m else None


def kanji_reply(username: str, k: str, rnd: random.Random, used=()) -> str:
    yomi = pick(KANJI[k], used, rnd) if k in KANJI else pick(KANJI_ANY, used, rnd).format(k=k)
    return "\n".join([pick(HEAD, used, rnd).format(n=name_of(username)), yomi,
                      pick(HOSHII, used, rnd), pick(TEASE, used, rnd)])


# ---------- 3週目（11/2〜11/8）の置かせ型（2026/10/31） ----------

SEIZA = {  # 彼の誕生日4桁 → 星座の「11月の動き方の癖」。断定せず「〜やすい」「〜が多い」で
    "牡羊座": ["牡羊座の男は、11月は仕事に火がついて、連絡が雑になりやすい。冷めたんじゃなく、前しか見えてないだけのことが多いよ。",
             "牡羊座の男の11月は、動きが速いぶん、あんたの話を聞き流しやすい。短く、結論から言うと通りやすいね。"],
    "牡牛座": ["牡牛座の男は、11月は腰が重い。急かされるほど動かない。会う日を決めるなら、先の日を一つだけ出しな。",
             "牡牛座の男の11月は、変化を嫌う時期。いつもの店、いつもの時間に誘うと、すっと来やすいよ。"],
    "双子座": ["双子座の男は、11月は気が散りやすい。返事が飛び飛びでも、話題が合えばすぐ戻ってくるよ。",
             "双子座の男の11月は、口は軽いが腰は重い。言葉より、会う約束が入ったかどうかで測りな。"],
    "蟹座": ["蟹座の男は、11月は家や身内のことで気持ちが内に向く。寂しがってるのに言わないのが癖だね。",
            "蟹座の男の11月は、守りに入る時期。責めると殻に入る。先にこっちの弱さを一つ見せると、出てきやすいよ。"],
    "獅子座": ["獅子座の男は、11月は褒められたい時期。張り合うより、一つ認めてやるとよく動くよ。",
             "獅子座の男の11月は、周りの目を気にして格好をつけやすい。2人きりの時の顔だけ見ておきな。"],
    "乙女座": ["乙女座の男は、11月は考えすぎて動けない。理屈で詰めるより、段取りを一つ軽くしてやりな。",
             "乙女座の男の11月は、細かいことが気になる時期。返事が遅いのは、言葉を選んでるだけのことも多いよ。"],
    "天秤座": ["天秤座の男は、11月は迷いが長い。決めかねてる時に二択を出すと、動きやすいよ。",
             "天秤座の男の11月は、人に合わせて疲れてる。あんたの前でだけ本音が出るなら、それは悪くない位置だね。"],
    "蠍座": ["蠍座の男は、11月は本音を深くしまう。追うと閉じる。待つより、こっちの本音を一つだけ先に置きな。",
            "蠍座の男の11月は、黙って見てる時期。連絡が少なくても、あんたの近況は見てることが多いよ。"],
    "射手座": ["射手座の男は、11月は外に気が向く。会えない日が増えても、気持ちが消えたとは限らないよ。",
             "射手座の男の11月は、約束を軽く忘れる時期。怒るより、日付を一つだけ念押ししな。"],
    "山羊座": ["山羊座の男は、11月は年末の仕事で頭がいっぱい。会う話は、日付を決めて短く言いな。",
             "山羊座の男の11月は、責任を抱えて余裕がない。労いの一言が、口説き文句より効くよ。"],
    "水瓶座": ["水瓶座の男は、11月は距離を取りたがる。放っておくと戻る。詰めると遠くなる癖があるね。",
             "水瓶座の男の11月は、自分の時間を守りたい時期。会う回数より、会った時の中身で測りな。"],
    "魚座": ["魚座の男は、11月は気持ちが揺れやすい。優しい言葉が増えた時ほど、行動のほうを見ておきな。",
            "魚座の男の11月は、流されやすい。あんたが決めてやると、ほっとして付いてくることが多いよ。"],
}


def tanjobi_of(comment: str):
    """「0314」「3/14」「3月14日」「19950314」→ (月, 日)。読めなければ None"""
    ds = hizuke.find_dates(comment)
    if ds:
        return int(ds[0][4:6]), int(ds[0][6:8])
    s = unicodedata.normalize("NFKC", comment)
    m = re.search(r"(?<!\d)(\d{1,2})\s*[/.月\-]\s*(\d{1,2})", s)
    if m:
        mo, da = int(m.group(1)), int(m.group(2))
    else:
        m = re.search(r"(?<!\d)(\d{3,4})(?!\d)", s)
        if not m:
            return None
        t = m.group(1).zfill(4)
        mo, da = int(t[:2]), int(t[2:])
    return (mo, da) if 1 <= mo <= 12 and 1 <= da <= 31 else None


def seiza_reply(username: str, mo: int, da: int, rnd: random.Random, used=()) -> str:
    name, _ = seinen.zodiac(date(2000, mo, da))
    return "\n".join([pick(HEAD, used, rnd).format(n=name_of(username)), f"{mo}月{da}日なら、{name}だね。",
                      pick(SEIZA[name], used, rnd), pick(TEASE, used, rnd)])


UMARE = {1: "決めたら早い", 2: "空気を読んで合わせる", 3: "話して近づく", 4: "一歩ずつ確かめて進む", 5: "動いていないと落ち着かない",
         6: "世話を焼いて近づく", 7: "一人の時間がないと息が詰まる", 8: "先に舵を取りたい", 9: "区切りをつけてから動く",
         10: "相手の出方を見てから動く", 11: "勘で近づいて勘で離れる", 12: "思い出を長く抱える"}
KAMI = {  # 2人の生まれ月の差（0／1〜2／3〜4／5〜6）→ 噛み合わせ
    0: ["同じ月の2人は、テンポが似てる。楽なぶん、2人とも待つ側に回ると止まりやすいよ。",
        "同じ月同士は、言わなくても分かる気になりやすい。それが甘えになると、すれ違いが長引くね。"],
    1: ["隣り合う月の2人は、半歩のずれ。片方が少し先を歩く形だね。先を歩くほうが待てるかどうかが分かれ目だよ。",
        "近い月の2人は、似てるようで一歩ずれてる。そのずれを責めずに面白がれると、長く続きやすいよ。"],
    2: ["少し離れた月の2人は、違うところに惹かれ合う縁。噛み合う時はぴたっと合うけど、ずれると長引きやすい。",
        "季節の違う月の2人は、ペースが違う。合わせるんじゃなく、どっちのペースで会うかを先に決めると楽だよ。"],
    3: ["向かい合う月の2人は、正反対。惹かれ合う力は強いけど、連絡のテンポが合わないのが癖だね。",
        "真向かいの月の2人は、相手に無いものを持ってる。だから惹かれるし、だから疲れる。間に一つ約束を置きな。"],
}


def months_of(comment: str) -> list:
    s = unicodedata.normalize("NFKC", comment)
    if hizuke.find_dates(s):
        return []
    return [int(x) for x in re.findall(r"(?<!\d)(\d{1,2})(?!\d)", s) if 1 <= int(x) <= 12][:2]


def pair_reply(username: str, a: int, b: int, rnd: random.Random, used=()) -> str:
    d = abs(a - b)
    d = min(d, 12 - d)
    key = 0 if d == 0 else 1 if d <= 2 else 2 if d <= 4 else 3
    hito = (f"2人とも{a}月生まれ。{UMARE[a]}人同士{rnd.choice(GOBI)}" if a == b
            else f"{a}月生まれは{UMARE[a]}人。{b}月生まれは{UMARE[b]}人{rnd.choice(GOBI)}")
    return "\n".join([pick(HEAD, used, rnd).format(n=name_of(username)), hito,
                      pick(KAMI[key], used, rnd), pick(TEASE, used, rnd)])


def month_only_reply(username: str, a: int, rnd: random.Random, used=()) -> str:
    return "\n".join([pick(HEAD, used, rnd).format(n=name_of(username)), f"{a}月生まれは、{UMARE[a]}人だよ。",
                      "彼の生まれ月も分かったら、2つ並べてもう一度置いておくれ。噛み合わせまで視る。"])


MATASE = {  # 彼の誕生日の「日」を1桁（11・22は残す）にした数 → 待たせ方の癖
    1: "1の日に生まれた男は、待たせてる自覚がない。自分の用事が先に来る人だよ。",
    2: "2の日に生まれた男は、返事を考えすぎて遅くなる。遅いが、来ると丁寧だね。",
    3: "3の日に生まれた男は、気分で返す。早い日と遅い日の差が大きいよ。",
    4: "4の日に生まれた男は、決めた順番を崩さない。待たせるけど、約束は守る人だよ。",
    5: "5の日に生まれた男は、目の前のことに流される。返事が遅いのは、忘れてるだけのことも多いね。",
    6: "6の日に生まれた男は、人の世話で手いっぱいになる。待たせてる相手が、あんただけじゃないこともあるね。",
    7: "7の日に生まれた男は、一人で考え込んでから返す。沈黙は、冷めたとは限らないよ。",
    8: "8の日に生まれた男は、仕事を先に片づけてから返す。順番は後ろでも、本気じゃないわけじゃないよ。",
    9: "9の日に生まれた男は、気を遣って返事を選びすぎる。遅いのは、傷つけたくないからのことが多いね。",
    11: "11の日に生まれた男は、勘で動く。返事がある日とない日が、はっきり分かれるよ。",
    22: "22の日に生まれた男は、背負ってるものが多い。待たせる時は、たいてい何かを抱えてるね。",
}
MATASE_TE = ["待つなら、次に会う日だけ先に聞いておきな。", "返事を待つ間に、あんたの予定を一つ入れておきな。",
             "催促するなら、質問は一つに絞りな。", "待ってる、とは言っていい。何度も言わなければ重くならないよ。"]


def day_of(comment: str):
    ds = hizuke.find_dates(comment)
    if ds:
        return int(ds[0][6:8])
    s = unicodedata.normalize("NFKC", comment)
    m = re.search(r"(?<!\d)(\d{1,2})(?!\d)", s)
    return int(m.group(1)) if m and 1 <= int(m.group(1)) <= 31 else None


def day_reply(username: str, d: int, rnd: random.Random, used=()) -> str:
    n = d
    while n > 9 and n not in (11, 22):
        n = sum(int(c) for c in str(n))
    head = f"{d}日生まれ。数にすると{n}だね。" if n != d else f"{d}日生まれだね。"
    return "\n".join([pick(HEAD, used, rnd).format(n=name_of(username)), head + MATASE[n], pick(MATASE_TE, used, rnd),
                      pick(TEASE, used, rnd)])


ONDO = [  # 最後に会ってからの日数 → 温度（上限日数, 文2通り）
    (7, ["7日のうちなら、まだ温かいよ。今は追わずに、次の約束だけ軽く置いておく時期だね。",
         "1週間以内なら、湯気がまだ立ってる。追い焚きはいらない。こっちの予定を一つ入れて待ちな。"]),
    (30, ["1か月のうちは、ぬるくなりかけ。こっちから一度、短い一通を入れてもいい頃だね。",
          "数週間あくと、温度は下がり始めてる。長い文じゃなく、用事のある短い一通が通りやすいよ。"]),
    (90, ["3か月まで来ると、冷めたんじゃなく、置かれてる。動くなら、用事を一つ作ってからだよ。",
          "季節が一つ変わる間、会ってないね。向こうの中で順番が下がってる気配がある。追うより、自分の近況を一つ変えな。"]),
    (365, ["1年近くなると、相手の中で季節が変わってる。戻すんじゃなく、新しく始めるつもりで一通だよ。",
           "半年を越えた縁は、懐かしさで返事が来ることがある。それを今の温度と間違えないでおくれ。"]),
    (10 ** 9, ["1年を越えた縁は、思い出のほうが温かい。会うなら、昔の2人じゃなく今の2人として会いな。",
               "1年以上たってるね。向こうの暮らしは、もう別の形になってるかもしれない。確かめてから、期待しな。"]),
]


def days_of(comment: str):
    s = unicodedata.normalize("NFKC", comment)
    if hizuke.find_dates(s):
        return None
    m = re.search(r"(?<!\d)(\d{1,5})(?!\d)", s)
    return int(m.group(1)) if m else None


def days_reply(username: str, n: int, rnd: random.Random, used=()) -> str:
    band = next(t for lim, t in ONDO if n <= lim)
    return "\n".join([pick(HEAD, used, rnd).format(n=name_of(username)), f"最後に会ってから{n}日。" + pick(band, used, rnd),
                      pick(TEASE, used, rnd)])


TEBANASU = {  # 生年月日→あんたの数 → この冬手放すといい癖
    1: "先に全部決めてしまう癖", 2: "相手の顔色を先に読む癖", 3: "明るく振る舞って本音を隠す癖",
    4: "約束を守りすぎて自分を後回しにする癖", 5: "飽きたふりをして逃げる癖", 6: "世話を焼いて好かれようとする癖",
    7: "一人で抱えて黙る癖", 8: "結果を急いで相手を試す癖", 9: "尽くして自分をすり減らす癖",
    11: "勘で分かった気になって確かめない癖", 22: "全部自分の責任にする癖", 33: "甘えるのが下手で強がる癖",
}
TEBANASU_TE = ["全部やめなくていい。今週、1回だけやらずにいてみな。",
               "やめ方は簡単だよ。その癖が出そうな時に、ひと呼吸おいてから動きな。",
               "癖は悪者じゃない。あんたを守ってきたものだ。でも、この冬は少し休ませてやりな。"]


def tebanasu_reply(username: str, s: str, rnd: random.Random, used=()) -> str:
    name, _ = seinen.zodiac(date(int(s[:4]), int(s[4:6]), int(s[6:8])))
    lp = seinen.life_path(s)
    return "\n".join([pick(HEAD, used, rnd).format(n=name_of(username)),
                      f"{name}で{lp}の人がこの冬手放すといいのは、「{TEBANASU[lp]}」だよ。", pick(TEBANASU_TE, used, rnd),
                      pick(TEASE, used, rnd)])


def make_reply(username: str, comment: str, post_text: str, today: date, seed: str, used=()):
    """(文面 or None, 読めなかった理由)。used＝同じ投稿で叶ばぁがもう返した文（言い回しをかぶらせない）"""
    rnd = random.Random(seed)
    if kinshi.needs_care(comment):
        return None, "気持ちが重い言葉あり（手で）"
    if "手放す" in post_text:  # 11/7 自分の8桁 → この冬手放す癖
        ds = hizuke.find_dates(comment)
        return (tebanasu_reply(username, ds[0], rnd, used), "") if ds else (None, "生年月日が読めない")
    if "4桁" in post_text and "誕生日" in post_text:  # 11/2 彼の誕生日4桁 → 星座の11月
        t = tanjobi_of(comment)
        return (seiza_reply(username, t[0], t[1], rnd, used), "") if t else (None, "誕生日が読めない")
    if "生まれた月" in post_text:  # 11/3 2人の生まれ月 → 噛み合わせ
        nums = months_of(comment)
        if len(nums) >= 2:
            return pair_reply(username, nums[0], nums[1], rnd, used), ""
        return (month_only_reply(username, nums[0], rnd, used), "") if nums else (None, "月が読めない")
    if "誕生日の「日」" in post_text or "月はいらない" in post_text:  # 11/5 彼の誕生日の日 → 待たせ方の癖
        d = day_of(comment)
        return (day_reply(username, d, rnd, used), "") if d else (None, "日が読めない")
    if "何日か" in post_text or "日数" in post_text:  # 11/6 最後に会ってからの日数 → 温度
        n = days_of(comment)
        return (days_reply(username, n, rnd, used), "") if n is not None else (None, "日数が読めない")
    if "生年月日" in post_text:
        ds = hizuke.find_dates(comment)
        return (birth_reply(username, ds[0], today, rnd, used), "") if ds else (None, "生年月日が読めない")
    if "出会った月" in post_text:
        s = unicodedata.normalize("NFKC", comment)
        nums = [int(x) for x in re.findall(r"(?<!\d)(\d{1,2})(?!\d)", s) if 1 <= int(x) <= 12]
        return (month_reply(username, nums[0], rnd, used), "") if len(set(nums)) == 1 else (None, "月が読めない")
    if "漢字一字" in post_text:
        k = kanji_of(comment)
        if k in KANJI_OMOI:
            return None, "重い字（手で）"
        return (kanji_reply(username, k, rnd, used), "") if k else (None, "漢字が読めない")
    return by_content(username, comment, post_text, today, rnd, used)


def by_content(username: str, comment: str, post_text: str, today: date, rnd: random.Random, used=()):
    """お題の言い方が型と違う投稿は、コメントの中身で返し方を選ぶ（10/31 みかちゃん「お題が変わるたびに直さなくていいように」）。
    8桁の日付→生年月日の型（どのお題でも）／「出会」のお題で短いコメントの1〜12→月の型／「一字・漢字」のお題で短いコメントの漢字→漢字一字の型。
    どれでもない（頭文字・誕生月など新しい種類のお題）は返さず /autoreply に残す＝手で返すか、型を足す"""
    ds = hizuke.find_dates(comment)
    if ds:
        return birth_reply(username, ds[0], today, rnd, used), ""
    s = re.sub(r"[\s、。,.!！?？~〜ー…・笑w]|です|でした|お願いします|おねがいします|よろしく", "", unicodedata.normalize("NFKC", comment))
    nums = re.findall(r"\d+", s)
    if "出会" in post_text and len(s) <= 6 and len(nums) == 1 and 1 <= int(nums[0]) <= 12 and len(nums[0]) <= 2:
        return month_reply(username, int(nums[0]), rnd, used), ""
    k = kanji_of(s)
    if re.search(r"一字|漢字", post_text) and k and not nums and len(s) <= 3:
        if k in KANJI_OMOI:
            return None, "重い字（手で）"
        return kanji_reply(username, k, rnd, used), ""
    return None, "読めないコメント（手で）"


# ---------- 2往復目（叶ばぁの返信に、さらに返してくれた人・2026/11/01 みかちゃん「完璧じゃない」） ----------
# 「ありがとうございます」「LINEに送りました」「実は今…」の返事が放置されていた。1人1回だけ返す（往復を続けない）

SOTCHI_RE = re.compile(r"LINE|ライン|らいん|メッセ|送りました|送らせて|投稿させて|登録しました|友だち追加")
THANKS_RE = re.compile(r"ありがと|有難|有り難|嬉し|うれし|当たって|あたって|頑張|がんば|楽しみ|心強|救われ|泣|感謝|励み")
THANKS = [
    "{n}さん、こっちこそありがとね。今週は、自分を急かさんでいいよ。",
    "{n}さん、届いてよかった。焦らんでいいからね。あんたの順番は、ちゃんと来るよ。",
    "どういたしまして、{n}さん。また夜に、ここで待ってるでね。",
    "{n}さん、そう言ってもらえると婆さんも嬉しいよ。今夜は、あったかくして寝な。",
]
SOTCHI = [
    "{n}さん、そっちにも届いてるよ。一人ずつ順番に視るでね、少し待っておくれ。",
    "{n}さん、ちゃんと受け取ってるよ。急がずに視るから、ゆっくり待っててね。",
    "{n}さん、届いてるよ、ありがとね。順番が来たら、婆さんから声をかけるでね。",
]
STORY_HEAD = ["{n}さん、話してくれてありがとね。", "{n}さん、聞かせてくれてありがとね。"]
STORY_UKE = [
    "そういう時は、相手のことより先に、あんたの心が疲れてないかを見てやりな。",
    "待つ時間が長いと、自分ばっかり悪いように思えてくるもんだ。そうとは限らないよ。",
    "言葉にできただけで、もう一歩は進んでる。婆さんはそう視るよ。",
    "一人で抱えてきたんだね。ここまで、よく持ちこたえた。",
]
STORY_END = [
    "込み入った話は、表で書くより、ゆっくり視たほうがいい。気になったらプロフィールのリンクからおいで。",
    "続きは、人の目がない所で視てやりたい話だね。プロフィールのリンクから、いつでもおいで。",
    "ここで全部は書けないけど、あんたの話はちゃんと覚えておくよ。続きはプロフィールのリンクからね。",
]
SHORT = [
    "{n}さん、読んでくれてありがとね。思い当たることがあったなら、それで十分だよ。",
    "{n}さん、そうかい。自分で気づけてるなら、もう半分は変われてるよ。",
]


def second_reply(username: str, comment: str, seed: str, used=()):
    """(文面 or None, 理由)。叶ばぁの返信への返事"""
    rnd = random.Random("2" + seed)
    n = name_of(username)
    if kinshi.needs_care(comment):
        return None, "気持ちが重い言葉あり（手で）"
    s = re.sub(r"\s", "", unicodedata.normalize("NFKC", comment or ""))
    if not s:
        return None, "中身が無い（スタンプだけ等）"
    if SOTCHI_RE.search(s):
        return pick(SOTCHI, used, rnd).format(n=n), ""
    if len(s) <= 40 and THANKS_RE.search(s):
        return pick(THANKS, used, rnd).format(n=n), ""
    if len(s) >= 10:
        return "\n".join([pick(STORY_HEAD, used, rnd).format(n=n), pick(STORY_UKE, used, rnd),
                          pick(STORY_END, used, rnd)]), ""
    return pick(SHORT, used, rnd).format(n=n), ""


# ---------- 回す ----------

def _ts(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z")


def _delay(cid: str) -> timedelta:
    return timedelta(minutes=random.Random("d" + cid).randint(15, 70))


def candidates(now: datetime) -> list:
    """返す候補 [(コメント, 投稿の文, その投稿で叶ばぁが返した文のリスト, 2往復目か)]。古い順
    2往復目＝叶ばぁの返信にさらに返してくれたもの。その人の2往復目に一度返したら、そこで止める（往復を続けない）"""
    out = []
    for p in threads_api.my_posts(limit=25, account=ACCOUNT):
        text = p.get("text") or ""
        if not OKASE.search(text) or now - _ts(p["timestamp"]) > timedelta(hours=48):
            continue
        conv = threads_api.conversation(p["id"], account=ACCOUNT)
        mine = {c["id"]: c for c in conv if c.get("is_reply_owned_by_me")}
        byid = {c["id"]: c for c in conv}
        answered = {(c.get("replied_to") or {}).get("id") for c in mine.values()}
        used = [c.get("text") or "" for c in mine.values()]
        # 2往復目にもう返した人（叶ばぁの返信の宛先が、投稿への直のコメントでない＝2往復目）
        second_done = set()
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
            if now - _ts(c["timestamp"]) > timedelta(hours=48):
                continue
            out.append((c, text, used, second))
            if second:
                second_done.add(c.get("username"))  # 同じ人が続けて2つ書いても、返すのは1つ
    return sorted(out, key=lambda x: x[0]["timestamp"])


def job(rush: bool = False):
    """rush＝みかちゃんの「今日のは全部返して」。待ち時間と件数の上限を外す（間は40〜120秒あける）"""
    if not enabled():
        return
    now = datetime.now(JST)
    if not rush and not (HOURS[0] <= now.hour < HOURS[1]):
        return
    try:
        cands = candidates(now)
    except Exception as e:
        _note(f"コメントの取得に失敗: {e}")
        return
    sent = 0
    for c, post_text, used, second in cands:
        if sent >= (20 if rush else PER_RUN):
            break
        if not rush and now < _ts(c["timestamp"]) + _delay(c["id"]):
            continue
        if second:
            text, why = second_reply(c.get("username", ""), c.get("text", ""), c["id"], used)
        else:
            text, why = make_reply(c.get("username", ""), c.get("text", ""), post_text, now.date(), c["id"], used)
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
            used.append(text)
            sent += 1
            _note(f"@{c.get('username')} に返した\n{text}")
        except Exception as e:
            _fail[c["id"]] = _fail.get(c["id"], 0) + 1
            body = getattr(getattr(e, "response", None), "text", "")[:300]
            _note(f"@{c.get('username')} への返信に失敗（{_fail[c['id']]}回目）: {e} {body}")


def peek() -> str:
    """送らずに、いま何が見えているかを書き出す（/autoreply?peek=1）"""
    now = datetime.now(JST)
    out = []
    for p in threads_api.my_posts(limit=25, account=ACCOUNT):
        text = p.get("text") or ""
        if not OKASE.search(text):
            continue
        conv = threads_api.conversation(p["id"], account=ACCOUNT)
        out.append(f"■ {p['timestamp']} {text[:20]} コメント{len(conv)}件")
        for c in conv[:40]:
            out.append(f"  @{c.get('username')} {c.get('timestamp')} 自分={c.get('is_reply_owned_by_me')} "
                       f"親={(c.get('replied_to') or {}).get('id')} 隠={c.get('hide_status')} {(c.get('text') or '')[:15]}")
    cands = candidates(now)
    out.append(f"\n候補 {len(cands)}件（うち2往復目 {sum(1 for x in cands if x[3])}件）")
    out += [f"  {'2往復目' if s else '1往復目'} @{c.get('username')} {(c.get('text') or '')[:20]}" for c, _, _, s in cands]
    return "\n".join(out)


@bp.get("/autoreply")
def page():
    from flask import request
    if request.args.get("rush") == "1019":
        import threading
        threading.Thread(target=job, kwargs={"rush": True}, daemon=True).start()
        _note("今いる分を全部返す（みかちゃん指示）")
        return "<pre>今いる分を順番に返しはじめた。数分後に /autoreply を見てね</pre>"
    if request.args.get("peek"):
        try:
            return f"<pre style='white-space:pre-wrap;font-size:12px'>{peek()}</pre>"
        except Exception as e:
            return f"<pre>{e} {getattr(getattr(e, 'response', None), 'text', '')[:300]}</pre>"
    rows = "\n".join(reversed(_log)) or "（まだ何もしていない）"
    state = "動いている" if enabled() else "止まっている（KANABAA_AUTOREPLY=0 かトークン無し）"
    return f"<pre style='white-space:pre-wrap;font-size:13px'>叶ばぁ 自動返信：{state}\n朝{HOURS[0]}時〜夜0時・コメントから15〜70分後・1回{PER_RUN}件まで\n\n{rows}</pre>"
