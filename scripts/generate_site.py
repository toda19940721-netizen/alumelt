#!/usr/bin/env python3
"""
generate_site.py
=================
data/news.json と data/price_log.csv を読み込み、templates/index.html.j2 を
レンダリングして docs/index.html を書き出す。

使い方:
  python scripts/generate_site.py

GitHub Pages を "docs/" フォルダから配信する設定にしておけば、
このスクリプトの出力がそのまま公開サイトになる。
"""

import csv
import json
from datetime import date, datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parent.parent
NEWS_JSON = ROOT / "data" / "news.json"
PRICE_LOG = ROOT / "data" / "price_log.csv"
VOLUME_FILE = ROOT / "data" / "volume.txt"
TEMPLATE_DIR = ROOT / "templates"
OUT_DIR = ROOT / "docs"

CATEGORIES = ["相場", "設備投資", "イベント", "地政学", "サステナビリティ"]

CATEGORY_SLUG = {
    "相場": "market",
    "設備投資": "invest",
    "イベント": "event",
    "地政学": "geo",
    "サステナビリティ": "sustain",
}


def load_articles():
    if not NEWS_JSON.exists():
        return []
    with open(NEWS_JSON, "r", encoding="utf-8") as f:
        articles = json.load(f)
    for a in articles:
        a["category_slug"] = CATEGORY_SLUG.get(a.get("category"), "other")
    return articles


def load_price_points():
    """(date_str, value) のリストを日付昇順で返す。壊れた行は無視する。"""
    if not PRICE_LOG.exists():
        return []
    points = []
    with open(PRICE_LOG, "r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        next(reader, None)  # header
        for row in reader:
            if len(row) < 2:
                continue
            try:
                d = date.fromisoformat(row[0])
                v = float(row[1])
            except ValueError:
                continue
            points.append((row[0], d, v))
    points.sort(key=lambda p: p[1])
    return [(d_str, v) for d_str, _d, v in points]


def format_date_ja(d_str):
    d = date.fromisoformat(d_str)
    return f"{d.year}年{d.month}月{d.day}日"


def build_chart(points, width=760, height=200, pad_left=52, pad_right=16, pad_top=24, pad_bottom=28):
    """
    日付を実際の経過日数に比例させたx座標で折れ線を作る。
    面塗り(グレーの塗りつぶし)はSaaS的な装飾でブランドの「罫線で語る」原則と
    ズレるため使わない。代わりに横の目盛線(min/mid/max)と全記録点のドットで
    「実データが積み上がっている」ことを見せる。
    """
    if len(points) < 2:
        return None

    dates = [date.fromisoformat(d) for d, _ in points]
    values = [v for _, v in points]

    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    t0, t1 = dates[0], dates[-1]
    tspan = (t1 - t0).days or 1

    def to_xy(d, v):
        x = pad_left + (width - pad_left - pad_right) * ((d - t0).days / tspan)
        y = height - pad_bottom - (height - pad_top - pad_bottom) * ((v - lo) / span)
        return x, y

    coords = [to_xy(d, v) for d, v in zip(dates, values)]
    line_points = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)

    dots = [{"x": x, "y": y} for x, y in coords]

    min_i = values.index(lo)
    max_i = values.index(hi)
    mid_val = (lo + hi) / 2
    mid_y = height - pad_bottom - (height - pad_top - pad_bottom) * 0.5

    gridlines = [
        {"y": height - pad_bottom, "label": f"${lo:,.0f}"},
        {"y": mid_y, "label": f"${mid_val:,.0f}"},
        {"y": pad_top, "label": f"${hi:,.0f}"},
    ]

    return {
        "width": width,
        "height": height,
        "pad_left": pad_left,
        "pad_right": pad_right,
        "line_points": line_points,
        "dots": dots,
        "gridlines": gridlines,
        "min_x": coords[min_i][0], "min_y": coords[min_i][1],
        "max_x": coords[max_i][0], "max_y": coords[max_i][1],
        "min_label": f"${lo:,.0f}",
        "max_label": f"${hi:,.0f}",
        "start_date": points[0][0],
        "end_date": points[-1][0],
        "start_date_ja": format_date_ja(points[0][0]),
        "end_date_ja": format_date_ja(points[-1][0]),
    }


def next_volume():
    n = 1
    if VOLUME_FILE.exists():
        try:
            n = int(VOLUME_FILE.read_text().strip()) + 1
        except ValueError:
            n = 1
    VOLUME_FILE.parent.mkdir(parents=True, exist_ok=True)
    VOLUME_FILE.write_text(str(n))
    return f"{n:03d}"


def pick_lead(articles):
    """地政学・相場カテゴリを優先しつつ、その中で最新のものをリードに選ぶ。"""
    if not articles:
        return None, []
    priority = {"地政学": 0, "相場": 1}
    top_priority = min(priority.get(a.get("category"), 2) for a in articles)
    candidates = [a for a in articles if priority.get(a.get("category"), 2) == top_priority]
    candidates.sort(key=lambda a: a.get("date") or "", reverse=True)
    lead = candidates[0]
    others = [a for a in articles if a is not lead]
    return lead, others


def main():
    articles = load_articles()
    lead, others = pick_lead(articles)
    price_points = load_price_points()

    price_delta = None
    if len(price_points) >= 2:
        prev, latest = price_points[-2][1], price_points[-1][1]
        if prev:
            price_delta = (latest - prev) / prev * 100

    chart = build_chart(price_points)

    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    template = env.get_template("index.html.j2")

    html = template.render(
        generated_date=datetime.now(timezone.utc).strftime("%Y.%m.%d"),
        volume=next_volume(),
        categories=CATEGORIES,
        lead=lead,
        others=others,
        price_points=price_points,
        price_delta=price_delta,
        chart=chart,
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "index.html").write_text(html, encoding="utf-8")
    print(f"[generate_site] docs/index.html を書き出しました(記事{len(articles)}件, 価格ログ{len(price_points)}件)。")


if __name__ == "__main__":
    main()
