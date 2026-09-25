#!/usr/bin/env python3
"""
fetch_news.py
=============
Anthropic API (Claude + web_search tool) を使って、アルミニウム業界の
最新ニュースを収集・要約し、data/news.json に追記する。

必要な環境変数:
  ANTHROPIC_API_KEY   Anthropicコンソールで発行したAPIキー

使い方:
  python scripts/fetch_news.py

このスクリプトが書き込むファイル:
  data/news.json        記事データ(蓄積・重複除去)
  data/price_log.csv     LMEアルミ現物価格の継続ログ(取れた日のみ追記)
"""

import os
import sys
import json
import csv
from datetime import datetime, timezone
from pathlib import Path

import anthropic

ROOT = Path(__file__).resolve().parent.parent
NEWS_JSON = ROOT / "data" / "news.json"
PRICE_LOG = ROOT / "data" / "price_log.csv"

# 使用モデル。最新の推奨モデルは https://docs.claude.com を参照して
# 必要なら差し替えてください。
MODEL = "claude-sonnet-5"

CATEGORIES = ["相場", "設備投資", "イベント", "地政学", "サステナビリティ"]

SYSTEM_PROMPT = f"""あなたはアルミニウム産業(製錬・地金・リサイクル・アルミ製品の川上〜川下)専門の
リサーチアシスタントです。web_search ツールを使って、直近7日以内に公開された
アルミニウム業界の一次情報(ニュース・プレスリリース・市況)を探してください。

対象カテゴリ: {", ".join(CATEGORIES)}

見つけたニュースのうち、重要度・話題性の高いものを最大5件選び、
以下のJSON配列だけを出力してください。JSON以外のテキスト(前置き、説明、
コードフェンス)は一切含めないこと。

各要素のフィールド:
- "category": 上記カテゴリのいずれか
- "date": 記事の公開日、または言及されている出来事の日付 (YYYY-MM-DD形式。不明な場合はnull)
- "title_ja": 日本語の見出し(30文字前後、記事内容を正確に要約すること。誇張しない)
- "summary_ja": 日本語の要約(2〜3文、120〜200文字程度。事実のみ、意見を混ぜない)
- "comment_ja": AIによる一言コメント(1文、40〜80文字程度。
  アルミ調達実務者の視点で「何が実務上のポイントか」を添える。
  「〜と考えられる」「〜に注意したい」など、推測は推測とわかる書き方にすること)
- "source_name": 情報源の媒体名
- "source_url": 情報源の実際のURL(必ずweb_searchで得た本物のURLを使うこと。捏造禁止)

加えて、可能であれば以下の "market_snapshot" オブジェクトも
JSON全体の中に含めてください(見つからない場合は null):
- "lme_cash_bid_usd_per_t": LMEアルミニウム現物(cash bid)価格の直近値(数値のみ)
- "date": その価格の日付 (YYYY-MM-DD)

出力全体は必ず以下の形の単一のJSONオブジェクトにすること:
{{
  "articles": [ ... ],
  "market_snapshot": {{ ... }} または null
}}
"""


def call_claude():
    client = anthropic.Anthropic()  # ANTHROPIC_API_KEY を環境変数から自動取得
    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": "今日時点でのアルミニウム業界ニュースを集めて、指定のJSON形式で出力してください。",
            }
        ],
        tools=[
            {
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": 8,
            }
        ],
    )

    # text ブロックだけを連結する(tool_use / web_search_tool_result は無視)
    text_parts = [b.text for b in response.content if getattr(b, "type", None) == "text"]
    raw = "\n".join(text_parts).strip()

    # 万一コードフェンスが付いていた場合に備えて除去
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
        if raw.lower().startswith("json"):
            raw = raw.split("\n", 1)[1]

    return json.loads(raw)


def load_json(path, default):
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def merge_articles(existing, new_articles):
    by_url = {a.get("source_url"): a for a in existing if a.get("source_url")}
    for a in new_articles:
        url = a.get("source_url")
        if not url:
            continue
        a["fetched_at"] = datetime.now(timezone.utc).isoformat()
        by_url[url] = a  # 同じURLなら上書き(最新の要約で更新)

    merged = list(by_url.values())
    merged.sort(key=lambda a: a.get("date") or "", reverse=True)
    return merged[:60]  # 直近60件だけ保持。増やしたい場合はここを調整


def append_price_log(snapshot):
    if not snapshot or snapshot.get("lme_cash_bid_usd_per_t") is None:
        return

    date = snapshot.get("date")
    price = snapshot.get("lme_cash_bid_usd_per_t")
    if not date:
        return

    PRICE_LOG.parent.mkdir(parents=True, exist_ok=True)
    existing_dates = set()
    if PRICE_LOG.exists():
        with open(PRICE_LOG, "r", encoding="utf-8", newline="") as f:
            for row in csv.reader(f):
                if row:
                    existing_dates.add(row[0])

    if date in existing_dates:
        return  # 同じ日はすでに記録済み

    write_header = not PRICE_LOG.exists()
    with open(PRICE_LOG, "a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(["date", "lme_cash_bid_usd_per_t"])
        writer.writerow([date, price])


def main():
    try:
        result = call_claude()
    except Exception as e:  # noqa: BLE001
        print(f"[fetch_news] Claude APIの呼び出しまたはJSON解析に失敗しました: {e}", file=sys.stderr)
        sys.exit(1)

    new_articles = result.get("articles", [])
    market_snapshot = result.get("market_snapshot")

    existing = load_json(NEWS_JSON, [])
    merged = merge_articles(existing, new_articles)
    save_json(NEWS_JSON, merged)
    append_price_log(market_snapshot)

    print(f"[fetch_news] {len(new_articles)}件取得 / 合計{len(merged)}件を保存しました。")


if __name__ == "__main__":
    main()
