#!/usr/bin/env python3
"""Extract a cross-atlas works index from the six volume HTML files.

Reads each volume's 本編 articles and 付録/読み物 app-items, assigns stable
ids, maps tags onto a shared vocabulary, writes works/works.json, and
injects id anchors into the volume pages (idempotent).

Usage (from the repository root):

    python3 tools/build-works.py
"""

from __future__ import annotations

import hashlib
import html as htmlmod
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

VOLUMES = [
    ("ai", "人工知能アトラス", "ai/index.html"),
    ("virtual-reality", "仮想現実アトラス", "virtual-reality/index.html"),
    ("spacetime", "時空間アトラス", "spacetime/index.html"),
    ("management-society", "管理社会アトラス", "management-society/index.html"),
    ("post-apocalypse", "ポストアポカリプスアトラス", "post-apocalypse/index.html"),
    ("end-of-the-world", "終焉アトラス", "end-of-the-world/index.html"),
]

# Volume-axis themes (the question each book is built around).
AXIS_THEMES = {
    "ai": ["意識の判定", "作られた存在"],
    "virtual-reality": ["仮想世界", "現実の判定"],
    "spacetime": ["時間の操作"],
    "management-society": ["管理と支配"],
    "post-apocalypse": ["終わった後"],
    "end-of-the-world": ["終わる直前"],
}

# Complete theme lists for works whose automatic tags would mislead
# (e.g. AI axis always adds 作られた存在; the keyword 「判定」 also flags VR works).
THEME_OVERRIDES = {
    "klein-bottle": ["仮想世界", "現実の判定"],
    "dareka-ga-naka-ni-iru": ["意識の判定"],
    "mahotsukai-no-deshitachi": ["終わる直前", "感染", "時間の操作"],
}

# Authoritative regions for works whose names would otherwise be
# mis-tagged (CJK personal names as 日本, Netflix as アメリカ, etc.).
REGION_OVERRIDES = {
    "invention-of-morel": ["アルゼンチン"],
    "lathe-of-heaven": ["アメリカ"],
    "memories-of-the-alhambra": ["韓国"],
    "solaris": ["ポーランド"],
    "pluto": ["日本"],
    "innocence": ["日本"],
    "never-let-me-go": ["イギリス"],
    "ship-of-theseus": ["インド"],
    "frankenstein-in-baghdad": ["イラク"],
    "millennium-actress": ["日本"],
    "dark": ["ドイツ"],
    "if-we-cannot-go-at-the-speed-of-light": ["韓国"],
    "district-9": ["南アフリカ"],
    "folding-beijing": ["中国"],
    "stalker": ["ロシア"],
    "station-eleven": ["カナダ"],
    "pumzi": ["ケニア"],
    "three-body": ["中国"],
    "the-leftovers": ["アメリカ"],
}


# Manual aliases: normalized key -> canonical id.
# Keys are produced by alias_key() (NFKC, lower, kana, no punctuation).
MERGE_ALIASES = {
    "メトロポリス": "metropolis",
    "metropolis": "metropolis",
    "ターミネーター": "terminator",
    "theterminator": "terminator",
    "ターミネーター未来戦の断片": "terminator",
    "攻殻機動隊": "ghost-in-the-shell",
    "ghostintheshell": "ghost-in-the-shell",
    "ドラえもん": "doraemon",
    "ウェストワールド": "westworld",
    "ウエストワールド": "westworld",
    "westworld": "westworld",
    "メガゾーン23": "megazone-23",
    "メガゾーン23歌姫イヴ": "megazone-23",
    "megazone23": "megazone-23",
    "ニーアオートマタ": "nier-automata",
    "nierautomata": "nier-automata",
    "akira": "akira",
    "ドラゴンヘッド": "dragon-head",
    "シュタインズゲート": "steins-gate",
    "steinsgate": "steins-gate",
    "steins;gate": "steins-gate",
    "クラインの壺": "klein-bottle",
    "ダレカガナカニイル": "dareka-ga-naka-ni-iru",
    "魔法使いの弟子たち": "mahotsukai-no-deshitachi",
    "モレルの発明": "invention-of-morel",
    "lainvenciondemorel": "invention-of-morel",
    "天のろくろ": "lathe-of-heaven",
    "thelatheofheaven": "lathe-of-heaven",
    "アルハンブラ宮殿の思い出": "memories-of-the-alhambra",
    "ストーカー": "stalker",
    "路傍のピクニック": "stalker",
    "ソラリス": "solaris",
    "pluto": "pluto",
    "プルートゥ": "pluto",
    "イノセンス": "innocence",
    "innocence": "innocence",
    "innocenceghostintheshell2": "innocence",
    "わたしを離さないで": "never-let-me-go",
    "neverletmego": "never-let-me-go",
    "shipoftheseus": "ship-of-theseus",
    "バグダードのフランケンシュタイン": "frankenstein-in-baghdad",
    "frankensteininbaghdad": "frankenstein-in-baghdad",
    "千年女優": "millennium-actress",
    "millenniumactress": "millennium-actress",
    "dark": "dark",
    "わたしたちが光の速さで進めないなら": "if-we-cannot-go-at-the-speed-of-light",
    "제9지구": "district-9",
    "第9地区": "district-9",
    "district9": "district-9",
    "折りたたみ北京": "folding-beijing",
    "北京折叠": "folding-beijing",
    "foldingbeijing": "folding-beijing",
    "pumzi": "pumzi",
    "ステーションイレブン": "station-eleven",
    "stationeleven": "station-eleven",
    "三体": "three-body",
    "thethreebodyproblem": "three-body",
    "leftovers残された世界": "the-leftovers",
    "theleftovers": "the-leftovers",
}

# Human titles for canonical merged ids (used when appearances disagree).
CANON_TITLES = {
    "metropolis": ("メトロポリス", "Metropolis"),
    "terminator": ("ターミネーター", "The Terminator"),
    "ghost-in-the-shell": ("攻殻機動隊", "GHOST IN THE SHELL"),
    "doraemon": ("ドラえもん", ""),
    "westworld": ("ウェストワールド", "Westworld"),
    "megazone-23": ("メガゾーン23", "MEGAZONE 23"),
    "nier-automata": ("ニーア オートマタ", "NieR:Automata"),
    "akira": ("AKIRA", ""),
    "dragon-head": ("ドラゴンヘッド", ""),
    "steins-gate": ("シュタインズ・ゲート", "STEINS;GATE"),
}

MEDIA_LABELS = ("小説", "映画", "アニメ", "漫画", "ゲーム", "ドラマ", "哲学・思想", "戯曲", "評論・実務", "伝承", "その他")
THEME_LABELS = (
    "意識の判定", "作られた存在", "仮想世界", "現実の判定", "夢・記憶", "死後の世界",
    "時間の操作", "時間移動", "ループ", "時間改変", "時間のずれ", "因果の輪",
    "監視", "管理と支配", "階級", "身体の管理", "情報統制",
    "核／災害", "感染", "終わった後", "終わる直前",
    "哲学", "家族", "遊び・ゲーム", "戦争", "複製・コピー",
)

# Existing volume tags / phrases -> shared themes.
TAG_THEME_MAP = {
    "動物機械論": ["哲学", "作られた存在"],
    "精神と身体の分割": ["哲学"],
    "人間も機械": ["哲学", "作られた存在"],
    "唯物論": ["哲学"],
    "意識の判定": ["意識の判定"],
    "作られた存在": ["作られた存在"],
    "ループ": ["ループ"],
    "繰り返す一日": ["ループ"],
    "人生リピート": ["ループ"],
    "死に戻り": ["ループ"],
    "監視": ["監視"],
    "スコア": ["監視", "身体の管理"],
    "階級": ["階級"],
    "垂直の都市": ["階級"],
    "情報統制": ["情報統制"],
    "検閲": ["情報統制"],
    "快楽と薬": ["管理と支配"],
    "仮想世界": ["仮想世界"],
    "模造世界": ["仮想世界"],
    "シミュレーション": ["仮想世界"],
    "電脳": ["仮想世界"],
    "メタバース": ["仮想世界"],
    "現実の判定": ["現実の判定"],
    "夢": ["夢・記憶"],
    "記憶": ["夢・記憶"],
    "死後": ["死後の世界"],
    "モラトリアム": ["死後の世界"],
    "タイムマシン": ["時間移動"],
    "時間旅行": ["時間移動"],
    "時間移動": ["時間移動"],
    "書き換える": ["時間改変"],
    "改変": ["時間改変"],
    "ずれる": ["時間のずれ"],
    "ブートストラップ": ["因果の輪"],
    "閉じる": ["因果の輪"],
    "核": ["核／災害"],
    "放射能": ["核／災害"],
    "隕石": ["核／災害"],
    "彗星": ["核／災害"],
    "惑星衝突": ["核／災害"],
    "気候": ["核／災害"],
    "感染": ["感染"],
    "ゾンビ": ["感染"],
    "ウイルス": ["感染"],
    "終わった後": ["終わった後"],
    "終焉": ["終わる直前"],
    "カウントダウン": ["終わる直前"],
    "家族": ["家族"],
    "ゲーム": ["遊び・ゲーム"],
    "戦争": ["戦争"],
    "複製": ["複製・コピー"],
    "コピー": ["複製・コピー"],
    "クローン": ["複製・コピー", "身体の管理"],
    "身体": ["身体の管理"],
    "生殖": ["身体の管理"],
    "健康": ["身体の管理"],
    "哲学": ["哲学"],
}

# Creator / byline hints for region.
JAPAN_HINTS = (
    "手塚治虫", "藤子", "押井守", "士郎正宗", "宮崎駿", "今敏", "新海誠", "庵野秀明",
    "大友克洋", "伊藤計劃", "小松左京", "筒井康隆", "光瀬龍", "梶尾真治", "上田早夕里",
    "小川一水", "冲方丁", "西尾維新", "奈須きのこ", "虚淵玄", "綾辻行人", "舞城王太郎",
    "永井豪", "諫山創", "荒木", "高橋留美子", "CLAMP", "安彦良和", "大場つぐみ",
    "石黒浩", "山本弘", "藤井太洋", "円城塔", "森博嗣", "東浩紀", "村上春樹",
    "豊田有恒", "眉村卓", "堀晃", "神林長平", "津原泰水", "宮部みゆき",
    "伊勢田", "日本", "東映", "スタジオジブリ", "ガイナックス", "プロダクションI.G",
    "シャフト", "京都アニメーション", "マリンポスト", "NHK", "フジテレビ",
    "小学館", "講談社", "集英社", "角川", "ハヤカワ文庫JA",
    "押井", "大友", "今敏", "細田守", "湯浅政明", "鶴田謙二", "弐瓶勉",
    "諫山", "諫山創", "荒川弘", "浦沢直樹", "浅野いにお", "五十嵐大介",
    "藤本弘", "富野由悠季", "河森正治", "庵野", "小島秀夫", "ヨコオタロウ",
    "横尾太郎", "遠藤浩輝", "武井宏之", "霧賀峰広", "久保帯人",
    "古橋秀之", "桜坂洋", "川原礫", "橙乃ままれ", "西旭川", "秋田禎信",
    "田中芳樹", "菅浩江", "山田正紀", "梶村", "藤田和日郎", "荒川",
    "樋口真嗣", "本広克行", "清水崇", "園子温", "黒沢清", "是枝裕和",
    "岩井俊二", "諏訪敦彦", "押井守", "りんたろう", "大友克洋",
    "石川光久", "神山健治", "荒牧伸志", "鎌田", "野村美月",
    "尼野ゆたか", "虚淵", "東出祐一郎", "成田良悟", "井上堅二",
    "涼宮", "谷川流", "伏瀬", "長月雨", "暁なつめ", "カントク",
    "日本沈没", "攻殻", "アトム", "ナウシカ", "エヴァンゲリオン", "ジブリ",
)
# These are checked as substrings against title+byline.


def text_of(src: str) -> str:
    src = re.sub(r"<br\s*/?>", " ", src or "", flags=re.I)
    src = re.sub(r"<[^>]+>", " ", src)
    return htmlmod.unescape(re.sub(r"\s+", " ", src)).strip()


def kana_fold(s: str) -> str:
    """Katakana -> hiragana, NFKC, lower, drop punctuation and spaces."""
    s = unicodedata.normalize("NFKC", s or "")
    s = s.casefold()
    out = []
    for ch in s:
        o = ord(ch)
        if 0x30A1 <= o <= 0x30F6:
            ch = chr(o - 0x60)
        if ch in "ーｰ‐―—–-−‾~〜…‥⋯":
            continue
        if ch in " 　\t・、。,.，．/／\\()（）[]「」『』【】〈〉《》『』“”\"'`!！?？:：;；&＆+＋=＝*＊#＃":
            continue
        out.append(ch)
    return "".join(out)


def alias_key(title: str, orig: str = "") -> str:
    # Prefer the Japanese title; also return checks against orig separately.
    return kana_fold(title)


def slugify(title: str, orig: str = "") -> str:
    """Stable ascii-ish id from title (or orig if title is non-latin only)."""
    base = unicodedata.normalize("NFKC", title or orig or "work")
    # If we have a latin orig, prefer it for a readable slug.
    latin = re.sub(r"[^A-Za-z0-9]+", "-", orig or "")
    latin = latin.strip("-").lower()
    if latin and re.search(r"[a-z]", latin) and len(latin) >= 3:
        slug = latin
    else:
        # romanize poorly: use kana_fold + hex fallback for CJK
        folded = kana_fold(base)
        ascii_part = re.sub(r"[^a-z0-9]+", "-", folded).strip("-")
        if ascii_part and re.search(r"[a-z0-9]", ascii_part) and len(ascii_part) >= 2:
            slug = ascii_part
        else:
            digest = hashlib.sha1(folded.encode("utf-8")).hexdigest()[:8]
            # keep a short readable hint if any ascii remains
            hint = re.sub(r"[^a-z0-9]+", "-", unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode()).strip("-").lower()
            slug = f"{hint}-{digest}" if hint else f"w-{digest}"
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug[:80] or "work"


def parse_year(year_text: str):
    """Return (sort_year: int|None, display)."""
    raw = text_of(year_text)
    if re.search(r"紀元前\s*\d+\s*世紀", raw):
        c = int(re.search(r"紀元前\s*(\d+)\s*世紀", raw).group(1))
        return -(c * 100 - 50), raw
    if re.search(r"紀元前\s*\d+", raw):
        n = int(re.search(r"紀元前\s*(\d+)", raw).group(1))
        return -n, raw
    if "伝説" in raw and not re.search(r"\d{3,4}", raw):
        return None, raw
    m = re.search(r"(\d{3,4})", raw)
    if m:
        return int(m.group(1)), raw
    return None, raw


def decade_of(sort_year):
    if sort_year is None:
        return "伝説・年代不詳"
    if sort_year < 1:
        return "古代"
    if sort_year < 1700:
        return "17世紀以前"
    if sort_year < 1800:
        return "18世紀"
    if sort_year < 1900:
        return "19世紀"
    century_head = (sort_year // 10) * 10
    return f"{century_head}年代"


def detect_media(small: str, byline: str, title: str, role: str) -> list[str]:
    blob = " ".join([small, byline, title])
    found = []

    def add(label):
        if label not in found:
            found.append(label)

    if role == "読み物" or re.search(r"経営書|社会批評|生産方式|生産管理|行動経済学|経営書|実務", blob):
        add("評論・実務")
    if re.search(r"伝承|伝説", blob) and not re.search(r"\d{4}", small):
        add("伝承")
    if re.search(r"戯曲|初演", blob):
        add("戯曲")
    if re.search(r"哲学|論文|思想実験|思想／|省察|方法序説", blob):
        add("哲学・思想")
    if re.search(r"テレビアニメ|アニメ映画|OVA|アニメ", blob):
        add("アニメ")
    if re.search(r"漫画", blob):
        add("漫画")
    if re.search(r"ゲーム", blob):
        add("ゲーム")
    if re.search(r"ドラマ", blob):
        add("ドラマ")
    # 「テレビ」alone (Star Trek style) is drama, unless already anime
    if re.search(r"テレビ", blob) and "アニメ" not in found and "ドラマ" not in found:
        add("ドラマ")
    if re.search(r"映画|監督|初映|劇場版", blob):
        add("映画")
    novel_blob = re.sub(r"短編映画", "", blob)
    if re.search(r"小説|長編|短編|短編集|中編|原作小説", novel_blob):
        add("小説")
    if re.search(r"プログラム|論文", blob) and "哲学・思想" not in found and not found:
        add("哲学・思想")
    if re.search(r"仮想世界サービス|オンライン世界|Second Life", blob):
        add("ゲーム")
    if re.search(r"ロボティクス|アンドロイド研究|ジェミノイド", blob):
        add("評論・実務")
    if re.search(r"LaMDA|ChatGPT|大規模言語モデル|Language Model", blob):
        add("評論・実務")
    if not found:
        add("その他")
    return found


def detect_regions(title: str, orig: str, byline: str) -> list[str]:
    blob = f"{title} {orig} {byline}"
    found = []

    def add(label):
        if label not in found:
            found.append(label)

    # Explicit markers first.
    if re.search(r"韓国|오징어|Squid Game|キム・チョヨプ|ソン・ジェジョン|アルハンブラ宮殿", blob):
        add("韓国")
    if re.search(r"ポーランド|レム|Lem|シュール|Stanisław|ソロヴィヨフ", blob):
        add("ポーランド")
    if re.search(r"チェコ|チャペック|Čapek|Karel", blob):
        add("チェコ")
    if re.search(r"ロシア|ソ連|Мы\b|ザミャーチン|トルストイ|メトロ2033", blob):
        add("ロシア")
    if re.search(r"ドイツ|ラング|フリッツ・ラング|Lang|Hitler|ドイツ表現", blob) or "Metropolis" in orig and "ラング" in byline:
        add("ドイツ")
    if re.search(r"フランス|ヴィリエ|ラ・メトリー|デカルト|ヴォルテール|ゴダール|ジェラール", blob):
        add("フランス")
    if re.search(r"イタリア|カリガリ", blob):
        add("イタリア")
    if re.search(r"オーストラリア|シュート|Nevil", blob):
        add("オーストラリア")
    if re.search(r"デンマーク|フォン・トリアー|Trier", blob):
        add("デンマーク")
    if re.search(r"スペイン|アメナーバル|Amenábar|Abre los ojos", blob):
        add("スペイン")
    if re.search(r"劉慈欣|郝景芳|北京折叠|折りたたみ北京", blob):
        add("中国")
    if re.search(r"イギリス|英国|ウェルズ|ウェルズ|クラーク|H\.G\.| Huxley|オーウェル|バラード|アダムズ|Pratchett|プラチェット|ゲイマン|Gaiman|莎士比亚", blob) or re.search(
        r"Wells|Clarke|Huxley|Orwell|Ballard|Shakespeare|Rowling|Doctor Who", blob
    ):
        add("イギリス")
    if re.search(r"カナダ|マンデル|Station Eleven|ステーション・イレブン", blob):
        add("カナダ")

    # Japanese only if we see kanji creator names or explicit Japanese studios/hints.
    # Do not treat katakana-only Western names (ジョセフ・ラスナック etc.) as Japanese.
    japan = any(h in blob for h in JAPAN_HINTS) or bool(
        re.search(r"(監督|原作|漫画)\s*[一-龯]{2,}", blob)
    )
    # "監督 ローランド・…" starts with kanji 監督 — strip role labels before name check.
    by = re.sub(r"^(監督|原作|漫画|脚本)\s*", "", byline or "")
    if re.match(r"[一-龯]{2,}", by):
        japan = True
    if japan:
        add("日本")

    # Creator / studio -> region (substring).
    creator_region = [
        ("イギリス", "シェリー|チューリング|ウェルズ|クラーク|オーウェル|ハクスリー|バージェス|キューブリック|"
                  "バラード|ギブスン(?! )|Gaiman|プラチェット|Aldiss|オールディス|チャーチ|"
                  "ノーラン|クリストファー・ノーラン|アレックス・ガーランド|ダンカン・ジョーンズ|"
                  "Doctor Who|H\.G\.|Huxley|Orwell|Ballard|Clarke|Turing"),
        ("アメリカ", "アシモフ|ディック|ハインライン|ブラッドベリ|ヴォネガット|ポール(?!・)|アンダースン|"
                  "ヴィンジ|スティーヴンスン|スピルバーグ|キャメロン|ウォシャウスキー|ビグロー|"
                  "シャマラン|コリンズ|ダシュナー|セイラー|ドラッカー|テイラー|"
                  "フォード・モーター|ヘンリー・フォード|ネーゲル|ワイゼンバウム|"
                  "テス|チャン|テッド・チャン|ズボフ|ホーガン|グリムウッド|"
                  "ガロイ|ラスナック|ジョーンズ ― 映画|スパイク・ジョーンズ|"
                  "レヴィ|ブラム|ジェームズ・ワン|アケラ・クーパー|Interplay|Black Isle|Maxis|"
                  "Rockstar|Linden Lab|Mobius|Netflix|HBO|PIXAR|ピクサー|"
                  "ディズニー|Disney|AMC|ハリウッド|"
                  "Star Trek|スタートレック|Fallout|The Sims"),  # shelley is UK; handled above first, both ok? I'll remove shelley from US
        ("フランス", "デカルト|ラ・メトリー|ヴィリエ|フーコー|クアンティック|ケイジ|ゴダール"),
        ("ドイツ", "ラング|ファスビンダー|フリッツ・ラング"),
        ("カナダ", "クローネンバーグ"),
        ("アメリカ", "ブラウン|バダム|ギブスン|マッカーシー|ブルックス|ロス|ダニエルズ|ウィル・ライト|サール"),
        ("イギリス", "BBC|ミック・ジャクソン|バリー・ハインズ"),
        ("オーストラリア", "プロヤス"),
        ("オーストラリア", "イーガン|グレッグ・イーガン|シュート|ウィアー"),
        ("スペイン", "アメナバル|Amenábar"),
        ("アルゼンチン", "ボルヘス"),
        ("ポーランド", "レム|CD Projekt"),
        ("チェコ", "チャペック"),
        ("オランダ", "Guerrilla"),
        ("イスラエル", "ゴールドラット"),
        ("ギリシャ", "プラトン"),
        ("中国", "荘子|胡蝶の夢|劉慈欣"),
        ("日本", "スクウェア|5pb|MAGES|ニトロプラス|かわぐちかいじ|乾くるみ|"
                "バンダイ|WIT STUDIO|小中千昭|長月達平|石黒浩|サンライズ|つくみず"),
    ]
    # Fix: Shelley is UK only. Remove from US pattern - I already listed シェリー under UK.
    for label, pat in creator_region:
        if re.search(pat, blob):
            add(label)

    if re.search(
        r"アメリカ|米国|ハリウッド|Disney|Netflix|Warner|HBO|A24|ピクサー|PIXAR|"
        r"ディズニー|Spielberg|スピルバーグ|Cameron|Nolan|"
        r"Asimov|アシモフ|Dick|ディック|Heinlein|ハインライン|"
        r"Stephenson|Sagan",
        blob,
    ):
        add("アメリカ")
    director_region = [
        ("アメリカ", "ロメロ|シャフナー|ゼメキス|ライミス|レイノルズ|ベイ|レダー|ホブリット|エメリッヒ|ブレス|ソダーバーグ|ニコルズ|マッケイ|ウォー"),
        ("イギリス", "ブリッグス|ギリアム|ボイル|カーティス|ライト|マッケンジー|P・D・ジェイムズ"),
        ("オーストラリア", "ジョージ・ミラー"),
        ("メキシコ", "キュアロン"),
        ("韓国", "ポン・ジュノ"),
        ("フランス", "ピエール・ブール"),
    ]
    for label, pat in director_region:
        if re.search(pat, blob):
            add(label)
    return found


def themes_from_text(*parts: str, volume: str, existing_tags: list[str]) -> list[str]:
    blob = " ".join(parts)
    found: list[str] = []

    def add(label):
        if label in THEME_LABELS and label not in found:
            found.append(label)

    for th in AXIS_THEMES.get(volume, []):
        add(th)

    for tag in existing_tags:
        for key, mapped in TAG_THEME_MAP.items():
            if key in tag:
                for m in mapped:
                    add(m)

    # Broader keyword pass on title + tags + description.
    rules = [
        (r"意識|心が|判定|チューリング|中国語の部屋|ハードプロブレム|クオリア|コウモリである", "意識の判定"),
        (r"ロボット|アンドロイド|ホスト|人造|ゴーレム|サイボーグ|AI\b|人工知能|機体|ヨルハ", "作られた存在"),
        (r"仮想|シミュレーション|模造|電脳|メタバース|マトリックス|楽園|VR\b|アップロード", "仮想世界"),
        (r"現実を判定|トーテム|本物か|世界は偽物", "現実の判定"),
        (r"夢|記憶|記憶の|インセプション|パプリカ", "夢・記憶"),
        (r"死後|死者|モラトリアム|あの世", "死後の世界"),
        (r"タイムマシン|時間旅行|時間移動|未来へ|過去へ|冷凍睡眠", "時間移動"),
        (r"ループ|繰り返し|同じ日|死に戻|リピート|Endless", "ループ"),
        (r"書き換|改変|歴史を変|過去を変", "時間改変"),
        (r"ずれ|時間の遅れ|ウラシマ|双子のパラドックス", "時間のずれ"),
        (r"ブートストラップ|因果|閉じた円|プリデスティネーション", "因果の輪"),
        (r"監視|パノプティコン|スコア|相互評価|ノーズダイブ|カメラ", "監視"),
        (r"ディストピア|管理社会|支配|全体主義|1984|Brave New", "管理と支配"),
        (r"階級|上層|地下|エリジウム|スノーピアサー|メトロポリス", "階級"),
        (r"身体|生殖|遺伝子|ガタカ|ハーモニー|臓器|改造手術", "身体の管理"),
        (r"検閲|情報統制|焚書|華氏451|図書館戦争", "情報統制"),
        (r"核|放射能|隕石|彗星|惑星衝突|沈没|気候変動|気候", "核／災害"),
        (r"感染|ウイルス|ゾンビ|パンデミック|コンテイジョン", "感染"),
        (r"家族|父|母|娘|息子", "家族"),
        (r"デスゲーム|遊戯|ゲーム化|ゲーム作品", "遊び・ゲーム"),
        (r"戦争|戦場|兵士|自衛隊", "戦争"),
        (r"コピー|複製|クローン|アップロードされた意識", "複製・コピー"),
        (r"哲学|思想実験|省察|比喩", "哲学"),
    ]
    for pat, label in rules:
        if re.search(pat, blob):
            add(label)
    return found


def extract_title_parts(heading_html: str) -> tuple[str, str, str]:
    """Return (title, orig, pair_note) from an h3/h4 inner HTML."""
    orig = ""
    pair = ""
    m = re.search(r'<span class="orig"[^>]*>(.*?)</span>', heading_html, re.S)
    if m:
        orig = text_of(m.group(1))
    m = re.search(r'<span class="pair"[^>]*>(.*?)</span>', heading_html, re.S)
    if m:
        pair = text_of(m.group(1))
    cleaned = re.sub(r'<span class="(?:orig|pair)"[^>]*>.*?</span>', "", heading_html, flags=re.S)
    title = text_of(cleaned)
    return title, orig, pair


# Folded alias table (built once).
_ALIAS_FOLDED = None

def alias_table():
    global _ALIAS_FOLDED
    if _ALIAS_FOLDED is None:
        _ALIAS_FOLDED = {kana_fold(k): v for k, v in MERGE_ALIASES.items()}
    return _ALIAS_FOLDED


def resolve_id(title: str, orig: str) -> str:
    table = alias_table()
    candidates = [title, orig, f"{title}{orig}"]
    short = re.split(r"[―—–]", title, maxsplit=1)[0].strip()
    if short and short not in candidates:
        candidates.append(short)
    for cand in candidates:
        key = kana_fold(cand)
        if key in table:
            return table[key]
    return slugify(title, orig)


def snippet_of(text: str, limit: int = 180) -> str:
    text = text_of(text)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


class Entry:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def parse_volume(slug: str, label: str, rel: str) -> list[Entry]:
    path = ROOT / rel
    raw = path.read_text(encoding="utf-8")
    entries: list[Entry] = []

    # ---- 本編 ----
    for attrs, body in re.findall(r"<article([^>]*)>(.*?)</article>", raw, re.S):
        cls = (re.search(r'class="([^"]+)"', attrs) or [None, ""])[1]
        if "slot" in cls.split():
            continue
        existing_id = (re.search(r'\bid="([^"]+)"', attrs) or [None, ""])[1]
        year_el = re.search(r'class="year"[^>]*>(.*?)</div>', body, re.S)
        year_html = year_el.group(1) if year_el else ""
        small = text_of(m.group(1)) if (m := re.search(r"<small>(.*?)</small>", year_html, re.S)) else ""
        year_disp_full = text_of(year_html)
        # display year: leading token(s) before small, already in text_of
        sort_year, year_display = parse_year(year_html)
        h3 = re.search(r"<h3[^>]*>(.*?)</h3>", body, re.S)
        title, orig, pair = extract_title_parts(h3.group(1) if h3 else "")
        byline = text_of(m.group(1) if (m := re.search(r'class="byline"[^>]*>(.*?)</p>', body, re.S)) else "")
        desc = text_of(m.group(1) if (m := re.search(r'class="desc"[^>]*>(.*?)</p>', body, re.S)) else "")
        tags = []
        tagul = re.search(r'class="tags"[^>]*>(.*?)</ul>', body, re.S)
        if tagul:
            tags = [text_of(x) for x in re.findall(r"<li\b[^>]*>(.*?)</li>", tagul.group(1))]
        opening = re.search(r"<article[^>]*>", raw[body and 0 :]).group(0) if False else None
        # capture exact opening tag for this article
        # We'll find it later by position; store a marker.
        entries.append(
            Entry(
                volume=slug,
                volume_label=label,
                role="本編",
                section="",
                title=title,
                orig=orig,
                pair=pair,
                byline=byline,
                year_display=year_display,
                sort_year=sort_year,
                small=small,
                desc=desc,
                tags=tags,
                core="core" in cls.split(),
                existing_id=existing_id,
                kind_open="article",
                raw_year_html=year_html,
            )
        )

    # ---- 付録 / 読み物 (app-item) ----
    # Locate each li.app-item and its enclosing section.
    for m in re.finditer(r"<li class=\"app-item\"([^>]*)>(.*?)</li>", raw, re.S):
        attrs, chunk = m.group(1), m.group(2)
        existing_id = (re.search(r'\bid="([^"]+)"', attrs) or [None, ""])[1]
        pre = raw[: m.start()]
        sec_id = ""
        sec_h2 = ""
        last_sec = pre.rfind("<section")
        if last_sec >= 0:
            sec_tag = pre[last_sec : pre.find(">", last_sec) + 1]
            sid = re.search(r'\bid="([^"]+)"', sec_tag)
            sec_id = sid.group(1) if sid else ""
            h2s = re.findall(r"<h2[^>]*>(.*?)</h2>", pre[last_sec:], re.S)
            if h2s:
                sec_h2 = text_of(h2s[-1])
        role = "読み物" if sec_id == "management" or "読み物" in sec_h2 or "ビジネス書" in sec_h2 else "付録"
        year_el = re.search(r'class="app-year"[^>]*>(.*?)</div>', chunk, re.S)
        year_html = year_el.group(1) if year_el else ""
        small = text_of(mm.group(1)) if (mm := re.search(r"<small>(.*?)</small>", year_html, re.S)) else ""
        sort_year, year_display = parse_year(year_html)
        h4 = re.search(r"<h4[^>]*>(.*?)</h4>", chunk, re.S)
        title, orig, pair = extract_title_parts(h4.group(1) if h4 else "")
        byline = text_of(mm.group(1) if (mm := re.search(r'class="byline"[^>]*>(.*?)</p>', chunk, re.S)) else "")
        desc = text_of(mm.group(1) if (mm := re.search(r'class="text"[^>]*>(.*?)</p>', chunk, re.S)) else "")
        tags = []
        tagul = re.search(r'class="tags"[^>]*>(.*?)</ul>', chunk, re.S)
        if tagul:
            tags = [text_of(x) for x in re.findall(r"<li\b[^>]*>(.*?)</li>", tagul.group(1))]
        entries.append(
            Entry(
                volume=slug,
                volume_label=label,
                role=role,
                section=sec_h2,
                title=title,
                orig=orig,
                pair=pair,
                byline=byline,
                year_display=year_display,
                sort_year=sort_year,
                small=small,
                desc=desc,
                tags=tags,
                core=False,
                existing_id=existing_id,
                kind_open="app-item",
                raw_year_html=year_html,
            )
        )

    return entries


def enrich(entry: Entry) -> None:
    entry.media = detect_media(entry.small, entry.byline, entry.title, entry.role)
    entry.regions = detect_regions(entry.title, entry.orig, entry.byline)
    entry.decade = decade_of(entry.sort_year)
    entry.themes = themes_from_text(
        entry.title, entry.orig, entry.byline, " ".join(entry.tags), entry.desc, entry.section,
        volume=entry.volume,
        existing_tags=entry.tags,
    )
    if "ゲーム" in entry.media and "遊び・ゲーム" not in entry.themes:
        entry.themes.append("遊び・ゲーム")
    entry.work_id = resolve_id(entry.title, entry.orig)
    if entry.work_id in THEME_OVERRIDES:
        entry.themes = list(THEME_OVERRIDES[entry.work_id])
    if entry.work_id in REGION_OVERRIDES:
        entry.regions = list(REGION_OVERRIDES[entry.work_id])


def merge_entries(entries: list[Entry]) -> list[dict]:
    groups: dict[str, list[Entry]] = defaultdict(list)
    for e in entries:
        groups[e.work_id].append(e)

    works = []
    for wid, items in groups.items():
        # Prefer a 本編 appearance for canonical title, then official CANON_TITLES.
        items_sorted = sorted(
            items,
            key=lambda e: (0 if e.role == "本編" else 1, e.volume),
        )
        title, orig = items_sorted[0].title, items_sorted[0].orig
        if wid in CANON_TITLES:
            title, orig = CANON_TITLES[wid]
        # earliest year among appearances
        years = [e.sort_year for e in items if e.sort_year is not None]
        sort_year = min(years) if years else None
        # prefer display from the appearance that supplied sort_year min
        year_display = next((e.year_display for e in items if e.sort_year == sort_year), items_sorted[0].year_display)
        # byline: join unique, prefer 本編
        bylines = []
        for e in items_sorted:
            if e.byline and e.byline not in bylines:
                bylines.append(e.byline)
        byline = bylines[0] if bylines else ""
        snippet = next((snippet_of(e.desc) for e in items_sorted if e.desc), "")
        media, regions, themes = [], [], []
        for e in items_sorted:
            for x, bucket in ((e.media, media), (e.regions, regions), (e.themes, themes)):
                for v in x:
                    if v not in bucket:
                        bucket.append(v)
        appearances = []
        for e in items_sorted:
            appearances.append({
                "volume": e.volume,
                "volumeLabel": e.volume_label,
                "role": e.role,
                "href": f"../{e.volume}/#work-{e.work_id}",
                "titleInVolume": e.title,
                "core": e.core,
            })
        works.append({
            "id": wid,
            "title": title,
            "orig": orig,
            "year": sort_year,
            "yearLabel": year_display,
            "decade": decade_of(sort_year),
            "byline": byline,
            "bylines": bylines,
            "snippet": snippet,
            "media": media,
            "regions": regions,
            "themes": themes,
            "appearances": appearances,
        })

    def sort_key(w):
        y = w["year"] if w["year"] is not None else 99999
        return (y, w["title"])

    works.sort(key=sort_key)
    return works


def patch_ids(entries: list[Entry]) -> None:
    """Inject id='work-...' into article / app-item opening tags, in document order."""
    by_vol: dict[str, list[Entry]] = defaultdict(list)
    for e in entries:
        by_vol[e.volume].append(e)

    vol_rel = {slug: rel for slug, _label, rel in VOLUMES}
    for slug, items in by_vol.items():
        path = ROOT / vol_rel[slug]
        raw = path.read_text(encoding="utf-8")
        main_items = [e for e in items if e.role == "本編"]
        app_items = [e for e in items if e.role != "本編"]

        def inject_article(m, queue=iter(main_items)):
            tag = m.group(0)
            try:
                e = next(queue)
            except StopIteration:
                return tag
            wid = f"work-{e.work_id}"
            if re.search(r'\bid="', tag):
                return re.sub(r'\bid="[^"]*"', f'id="{wid}"', tag, count=1)
            return tag[:-1] + f' id="{wid}">'

        # Only real entries, not slots: match article with class containing entry but we'll
        # skip slots by leaving them without consuming... actually slots are also <article class="entry slot">.
        # Consume only non-slot.
        main_iter = iter(main_items)

        def inject_article_smart(m):
            tag = m.group(0)
            if re.search(r'\bslot\b', tag):
                return tag
            try:
                e = next(main_iter)
            except StopIteration:
                return tag
            wid = f"work-{e.work_id}"
            if re.search(r'\bid="', tag):
                return re.sub(r'\bid="[^"]*"', f'id="{wid}"', tag, count=1)
            return tag[:-1] + f' id="{wid}">'

        raw2, n_main = re.subn(r"<article\b[^>]*>", inject_article_smart, raw)

        app_iter = iter(app_items)

        def inject_app(m):
            tag = m.group(0)
            try:
                e = next(app_iter)
            except StopIteration:
                return tag
            wid = f"work-{e.work_id}"
            if re.search(r'\bid="', tag):
                return re.sub(r'\bid="[^"]*"', f'id="{wid}"', tag, count=1)
            # <li class="app-item"> or <li class="app-item" ...>
            return tag[:-1] + f' id="{wid}">'

        raw3, n_app = re.subn(r"<li class=\"app-item\"[^>]*>", inject_app, raw2)
        leftover_main = list(main_iter)
        leftover_app = list(app_iter)
        if leftover_main or leftover_app:
            raise SystemExit(f"{slug}: unused ids after patch (main {len(leftover_main)}, app {len(leftover_app)})")
        if raw3 != raw:
            path.write_text(raw3, encoding="utf-8")
            print(f"  patched {slug}: article ids + app ids")
        else:
            print(f"  {slug}: already up to date")


def build():
    all_entries: list[Entry] = []
    for slug, label, rel in VOLUMES:
        items = parse_volume(slug, label, rel)
        for e in items:
            enrich(e)
        all_entries.extend(items)
        kinds = Counter(e.role for e in items)
        print(f"{slug}: " + ", ".join(f"{k} {v}" for k, v in sorted(kinds.items())) + f" (total {len(items)})")

    official = [e for e in all_entries if e.role != "読み物"]
    essays = [e for e in all_entries if e.role == "読み物"]
    print(f"\n公式収録（本編+付録）: {len(official)}  (expected 243)")
    print(f"読み物: {len(essays)}")

    if len(official) != 243:
        print("WARNING: official count is not 243", file=sys.stderr)

    works = merge_entries(all_entries)
    official_works = merge_entries(official)
    multi = [w for w in official_works if len(w["appearances"]) > 1]
    print(f"unique official works: {len(official_works)}")
    print(f"multi-volume official works: {len(multi)}")
    for w in multi:
        apps = ", ".join(f"{a['volumeLabel']}（{a['role']}）" for a in w["appearances"])
        print(f"  - {w['title']} [{w['id']}] — {apps}")
    print(f"unique including 読み物: {len(works)}")

    # Collision check: two different titles sharing an id unexpectedly is OK if aliased;
    # warn if two official entries in SAME volume share an id.
    seen_vol_id = {}
    for e in all_entries:
        key = (e.volume, e.work_id)
        if key in seen_vol_id:
            print(f"WARNING: duplicate id in {e.volume}: {e.work_id} ({seen_vol_id[key]} / {e.title})")
        else:
            seen_vol_id[key] = e.title

    patch_ids(all_entries)

    out = {
        "generatedBy": "tools/build-works.py",
        "counts": {
            "officialEntries": len(official),
            "essayEntries": len(essays),
            "allEntries": len(all_entries),
            "uniqueOfficialWorks": len(official_works),
            "uniqueAllWorks": len(works),
            "multiVolumeOfficial": len(multi),
        },
        "taxonomy": {
            "media": list(MEDIA_LABELS),
            "themes": list(THEME_LABELS),
            "roles": ["本編", "付録", "読み物"],
            "volumes": [{"id": s, "label": lab} for s, lab, _ in VOLUMES],
        },
        "works": works,
    }
    dest = ROOT / "works" / "works.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {dest.relative_to(ROOT)} ({dest.stat().st_size} bytes)")


if __name__ == "__main__":
    build()
