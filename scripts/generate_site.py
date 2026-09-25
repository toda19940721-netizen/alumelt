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
from datetime import datetime, timezone
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
    if not PRICE_LOG.exists():
        return []
    points = []
    with open(PRICE_LOG, "r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        next(reader, None)  # header
        for row in reader:
            if len(row) >= 2:
                try:
                    points.append((row[0], float(row[1])))
                except ValueError:
                    continue
    points.sort(key=lambda p: p[0])
    return points


def build_sparkline(points, width=300, height=60, pad=4):
    if len(points) < 2:
        return None
    values = [p[1] for p in points]
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    n = len(points)
    coords = []
    for i, v in enumerate(values):
        x = pad + (width - 2 * pad) * (i / (n - 1))
        y = height - pad - (height - 2 * pad) * ((v - lo) / span)
        coords.append(f"{x:.1f},{y:.1f}")
    return " ".join(coords)


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
        sparkline_points=build_sparkline(price_points),
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "index.html").write_text(html, encoding="utf-8")
    print(f"[generate_site] docs/index.html を書き出しました(記事{len(articles)}件, 価格ログ{len(price_points)}件)。")


if __name__ == "__main__":
    main()
