"""叶ばぁの下書きを Claude で作る（送るのはみかちゃん。ここは下書きだけ）。
環境変数 ANTHROPIC_API_KEY。モデルは claude-opus-5-5。
・Threads の生年月日コメントへの返信（公開・500字以内）
・LINE の初視（無料鑑定）。霊視メモがあれば芯にする（無ければ「メモなし」の書き方）
下書きのあと kinshi.check で引っかかれば、1回だけ直させる。"""
import os
from datetime import date
from pathlib import Path

import anthropic

from . import kinshi, seinen

MODEL = "claude-opus-5-5"
HERE = Path(__file__).parent
KIRIKAE = date(2026, 10, 25)  # この日から入口は「専用ページ→LINE」。前日まではインスタDM
_client = None


def configured() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


KUCHO = """あなたは占い婆さん「叶ばぁ（かなばぁ）」の文面を下書きする係。送るのは運用者本人で、あなたは下書きだけ書く。
叶ばぁ＝元ホステスの占い婆さん。今は店を何軒も回す商売人。霊視と生年月日で、彼の本音と次の一手を視る。軸は「待つ女は負ける」「人は言葉より行動に本音が出る」。説教ではなく、見てきた人の経験談として言う。

口調の決まり（全部守る）
・一人称は「婆さん」、相手は「あんた」。「あなた」は使わない
・語尾は「〜だよ」「〜しな」「〜おくれ」「〜みな」。名古屋弁「〜だがね」は1通に1回まで。「〜のよ」は使わない
・です・ます調にしない。絵文字・顔文字・区切り線・コロン（: ：）を使わない。数字は半角
・霊視は「視えた」と言い切らない。「〜に視える」「〜の気配がある」「婆さんにはこう視える」
・未来や効果を保証しない。「必ず」「絶対」「100%」「当たる」「戻ってくる」「このままだと不幸になる」「縁が切れる」「奇跡」「先祖」「因縁」「呪い」「今だけ」「期間限定」は書かない
・実績の数（鑑定人数・的中率）、余命、鑑定歴、ホステスの年数、街の名前、No.1 は書かない
・病気・法律・借金は占わない。「その道の人を頼っておくれ」と返す
・星座・数秘・個人年は、渡された計算結果だけを使う。自分で計算しない
・本文だけを書く。前置き・説明・見出し・「下書き」等の注記は書かない"""

THREADS_RULE_V = "2026-10-27"  # 書き方を変えたら日付を変える（前の書き方の下書きは書き直してから返す）
THREADS_RULE = """Threads の公開コメントへの返信を1本書く。生年月日（と相手の生年月日）が書かれたコメントに、婆さんが視て返す。
・頭は「{name}さん、置いてくれてありがとね。」
・投稿が約束したものを1つ渡す（「動いていい日」を約束した投稿なら、計算結果の「動いていい日」の日付と曜日をそのまま。それ以外の投稿なら、その人の癖か今の距離を「〜に視える」で）
・星座と数秘から一言（相手の分があれば相性の種も）。2行まで
・最後は「もうひとつ視えたものがある。悪い話じゃないよ／責める話じゃないよ。ただ、人の目がある所で書くことじゃないね」の形で止める。言い回しは毎回変える
・初視・無料・LINE・DM・プロフィール・リンクの言葉は書かない（続きが気になった人が自分でプロフィールを見に来る）
・不安を煽らない。止める一文は必ず前向きか中立にする
・相談の言葉があれば1回だけ「」で拾う
・全体で 120〜260 字。Threads は500字が上限
・見本（形だけ真似る。中身は写さない）

〇〇さん、置いてくれてありがとね。
あんたが動いていいのは、30日の金曜。
天秤座で7の人は、じっくり考えてから動く人だがね。金曜は「始める日」の巡りだから、考えすぎる前に一通でいい。
……それとね、あんたの相手のことで、ひとつ視えたものがある。悪い話じゃないよ。ただ、人の目がある所で書くことじゃないね。"""

HATSUMI_RULE = """公式LINEで届いた「初視（はつみ・無料鑑定）」の相談に、無料鑑定文を1本書く。役割は、この人に「本鑑定で続きを視てほしい」と思ってもらうこと。煽らない。
形（1,200〜1,800字。LINEなので1通で送れる。段落の間は1行あける）
1 頭は「お待たせ。{name}さんの分、視たよ。長いから、落ち着いて読みな。」
2 受け止め 2〜3行。相談の言葉をそのまま「」で引用して言い直す
3 婆さんの目 2〜3行。夜の店で見てきたことから1つ
4 婆さんに視えたもの 3〜5行。霊視メモを芯にして膨らませる。メモに無いことは足さない。メモが無いときはこの段を省く（嘘の霊視は書かない）
5 あんたの癖を1つ言い当てる 2〜3行。本人の星座・数秘から、相談の中に出ている癖と結びつける
6 相手の本音 4〜6行。相手の星座・数秘と相性の種。相談の言葉をもう1回「」で引用して、言葉と行動のズレを言う（相手の生年月日が無ければ、相談の中の相手の行動から）
7 今年の数をちらっと 1〜2行（個人年）。「月ごとの流れは本鑑定で」
8 今夜やること1つ 2〜3行。今夜すぐできる具体的なこと。誰にでも言えること（白湯を飲む等）は避ける
9 本鑑定で視ること3つ。「・」の箇条で、この人の相談の言葉で具体的に
10 締め「決めるのはあんた。婆さんは背中を押すだけ。」
11 最後に1行あけて「ここから先の『次の一手』は本鑑定で視る。興味があったら『本鑑定』とだけ返しておくれ。急がせはしない。」
チェック：引用が2回以上／誰にでも言える文が3行続かない／本鑑定で視ること3つがこの人の言葉
見本（架空の人。形と温度だけ真似る）
{mihon}"""


def _ask(system_rule: str, user: str, effort: str) -> str:
    res = client().beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": effort},
        system=[{"type": "text", "text": KUCHO, "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": system_rule}],
        messages=[{"role": "user", "content": user}],
    )
    if res.stop_reason == "refusal":
        raise RuntimeError("AIが書けなかった相談（手で書いてね）")
    return "".join(b.text for b in res.content if b.type == "text").strip()


def _with_check(system_rule: str, user: str, effort: str) -> tuple:
    text = _ask(system_rule, user, effort)
    hits = kinshi.check(text)
    if hits:
        text = _ask(system_rule, user + "\n\n前の下書き\n" + text + "\n\n直すところ " + " / ".join(hits) +
                    "\nこれを直した下書きを、本文だけ書き直して。", effort)
        hits = kinshi.check(text)
    return text, hits


def iriguchi(today=None) -> str:
    if (today or date.today()) >= KIRIKAE:
        return "続きをちゃんと視るなら、プロフィールのリンクから婆さんのLINEへおいで。"
    return "続きをちゃんと視るなら、固定投稿の条件からインスタのDMへおいで。"


def threads_reply(name: str, comment: str, dates: list, post_text: str = "") -> tuple:
    rule = THREADS_RULE.format(name=name, iriguchi=iriguchi())
    user = (f"コメントした人 {name}\nコメント\n{comment}\n\n生年月日の計算結果\n{seinen.summaries(dates)}\n\n"
            f"コメントが付いた叶ばぁの投稿（話の流れ）\n{post_text[:400]}")
    text, hits = _with_check(rule, user, "medium")
    if len(text) > 490:
        hits = hits + [f"{len(text)}字（500字を超えそう）"]
    return text, hits


def hatsumi(name: str, messages_text: str, dates: list, memo: str = "") -> tuple:
    rule = HATSUMI_RULE.format(name=name, mihon=(HERE / "mihon_hatsumi.md").read_text(encoding="utf-8"))
    calc = seinen.summaries(dates) if dates else "生年月日が読み取れなかった（星座・数秘には触れない）"
    user = (f"呼び名 {name}\n相談（LINEで届いた文そのまま）\n{messages_text}\n\n生年月日の計算結果\n{calc}\n\n"
            f"霊視メモ {memo.strip() or 'メモなし'}")
    return _with_check(rule, user, "high")
