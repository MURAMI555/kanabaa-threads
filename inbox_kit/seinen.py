"""生年月日から星座・元素・数秘（ライフパス）を出す。鑑定文の下書き用。
使い方: python -I -X utf8 seinen.py 19850614 [19801102]
"""
import sys
from datetime import date

ZODIAC = [  # (終わりの月, 日, 星座, 元素)
    (1, 19, "山羊座", "土"), (2, 18, "水瓶座", "風"), (3, 20, "魚座", "水"),
    (4, 19, "牡羊座", "火"), (5, 20, "牡牛座", "土"), (6, 21, "双子座", "風"),
    (7, 22, "蟹座", "水"), (8, 22, "獅子座", "火"), (9, 22, "乙女座", "土"),
    (10, 23, "天秤座", "風"), (11, 22, "蠍座", "水"), (12, 21, "射手座", "火"),
    (12, 31, "山羊座", "土"),
]

LP = {
    1: "自分で道を切り開く・先に動きたい", 2: "相手に合わせる・気持ちを察する",
    3: "楽しさ・言葉で人を惹きつける", 4: "堅実・約束と積み重ね",
    5: "自由・変化を求める・縛られると離れる", 6: "情が深い・世話を焼く・家庭的",
    7: "一人の時間が要る・本音を見せにくい", 8: "仕事と力・現実的に物事を回す",
    9: "人に尽くす・手放すことを覚える", 11: "直感が鋭い・繊細で揺れやすい",
    22: "大きなものを形にする・責任を背負いやすい", 33: "無償の愛・人を包む",
}

# 元素の組み合わせ（鑑定の言い回しの種。断定しない）
AISHO = {
    frozenset(["火"]): "同じ熱さ。燃えるのも早いがぶつかるのも早い",
    frozenset(["土"]): "同じ歩幅。急な変化は少ないが動き出しが遅い",
    frozenset(["風"]): "同じ軽さ。話は合うが、どちらも決めきらない",
    frozenset(["水"]): "同じ深さ。分かり合えるが、黙ると沈む",
    frozenset(["火", "風"]): "風が火をあおる。勢いは出るが言葉が先走る",
    frozenset(["土", "水"]): "水が土を潤す。時間をかけるほど根が張る",
    frozenset(["火", "水"]): "火と水。惹かれるが、温度差で疲れやすい",
    frozenset(["風", "土"]): "風と土。考え方の速さが違う。待つ側が疲れる",
    frozenset(["火", "土"]): "火と土。片方が急ぎ、片方が固める",
    frozenset(["風", "水"]): "風と水。気持ちを言葉にする側と、言葉にできない側",
}


def zodiac(d):
    for m, day, name, elem in ZODIAC:
        if (d.month, d.day) <= (m, day):
            return name, elem
    return "山羊座", "土"


def life_path(s):
    n = sum(int(c) for c in s)
    while n > 9 and n not in (11, 22, 33):
        n = sum(int(c) for c in str(n))
    return n


PY = {1: "始まり", 2: "待つ・支える", 3: "明るさ・表現", 4: "土台を固める", 5: "変化",
      6: "家庭と責任", 7: "立ち止まって考える", 8: "現実的に決める・力", 9: "区切り・手放す",
      11: "直感・揺れ", 22: "大きく形にする", 33: "包む"}


def personal(s, year, month=None):
    """個人年（誕生月日＋その年）。monthを渡すと個人月（個人年＋月）。"""
    n = life_path(f"{int(s[4:6])}{int(s[6:8])}{year}")
    if month:  # 個人月はマスター数を残さず1桁まで
        n = sum(int(c) for c in f"{n}{month}")
        while n > 9:
            n = sum(int(c) for c in str(n))
    return n


def one(s):
    d = date(int(s[:4]), int(s[4:6]), int(s[6:8]))
    name, elem = zodiac(d)
    lp = life_path(s)
    print(f"{d:%Y/%m/%d}  {name}（{elem}）  数秘{lp}：{LP[lp]}")
    t = date.today()
    y0 = personal(s, t.year)
    y1 = personal(s, t.year + 1)
    print(f"  個人年 {t.year}={y0}（{PY[y0]}） {t.year + 1}={y1}（{PY[y1]}）")
    months = []
    for i in range(6):
        m, y = (t.month + i - 1) % 12 + 1, t.year + (t.month + i - 1) // 12
        months.append(f"{y % 100}/{m}={personal(s, y, m)}")
    print("  個人月 " + " ".join(months))
    if name in ("牡牛座", "双子座") and (d.month, d.day) in ((5, 20), (5, 21), (5, 22)):
        print("  ※星座の境目の日。生まれた時刻で変わるので「境目」と書く")
    return elem


def summary(s, label="", today=None):
    """受付箱用：one() と同じ中身を文字で返す。(文, 元素)"""
    d = date(int(s[:4]), int(s[4:6]), int(s[6:8]))
    name, elem = zodiac(d)
    lp = life_path(s)
    t = today or date.today()
    y0 = personal(s, t.year)
    lines = [f"{label}{d:%Y/%m/%d} {name}（{elem}） 数秘{lp}＝{LP[lp]}",
             f"  個人年 {t.year}={y0}（{PY[y0]}）"]
    months = []
    for i in range(4):
        m, y = (t.month + i - 1) % 12 + 1, t.year + (t.month + i - 1) // 12
        months.append(f"{y % 100}/{m}={personal(s, y, m)}")
    lines.append("  個人月 " + " ".join(months))
    if (d.month, d.day) in ((5, 20), (5, 21), (5, 22)):
        lines.append("  ※星座の境目の日。「境目」と書く")
    return "\n".join(lines), elem


def summaries(dates, today=None):
    """[本人, 相手] の8桁 → 鑑定の材料の文"""
    out, elems = [], []
    for label, s in zip(["本人 ", "相手 "], dates[:2]):
        txt, e = summary(s, label, today)
        out.append(txt)
        elems.append(e)
    if len(elems) == 2:
        out.append("相性の種 " + AISHO[frozenset(elems)])
    return "\n".join(out)


if __name__ == "__main__":
    elems = [one(a.replace("/", "").replace("-", "")) for a in sys.argv[1:3]]
    if len(elems) == 2:
        print("相性の種：" + AISHO[frozenset(elems)])
