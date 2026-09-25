# アルミノート — 自動更新パイプライン

アルミニウム業界ニュースを AI(Claude API + web検索)が自動収集・要約し、
静的サイト(GitHub Pages)として毎日更新する仕組み。

```
[GitHub Actions: 毎朝7時JST]
        │
        ▼
scripts/fetch_news.py  … Claude + web_search でニュース収集・要約
        │
        ▼
data/news.json          … 記事の蓄積(重複除去・最大60件保持)
data/price_log.csv       … LMEアルミ価格の継続ログ
        │
        ▼
scripts/generate_site.py … Jinja2テンプレートからサイトを再生成
        │
        ▼
docs/index.html          … GitHub Pagesがこのフォルダを配信
```

## セットアップ手順

### 1. GitHubリポジトリを作る
このフォルダの中身をそのまま新しいGitHubリポジトリにpushする。

```bash
cd alumi-note-pipeline
git init
git add .
git commit -m "init"
git remote add origin https://github.com/<あなたのアカウント>/alumi-note.git
git push -u origin main
```

### 2. Anthropic APIキーを取得する
https://console.anthropic.com でAPIキーを発行する(claude.aiのログインとは別のアカウント/課金)。

### 3. GitHub Secretsに登録する
リポジトリの **Settings → Secrets and variables → Actions → New repository secret** で

- Name: `ANTHROPIC_API_KEY`
- Value: 取得したAPIキー

を登録する。

### 4. GitHub Pagesを有効化する
**Settings → Pages** で、Source を「Deploy from a branch」、Branch を
`main` / `docs` フォルダに設定する。数分後に
`https://<あなたのアカウント>.github.io/alumi-note/` で公開される。

### 5. 動作確認
**Actions** タブから `Update Alumi Note` ワークフローを選び、
`Run workflow` で手動実行して、`docs/index.html` が更新されるか確認する。
以降は毎日 JST 7:00 に自動実行される(`.github/workflows/update.yml` の
cron設定で変更可能)。

## ローカルで試す場合

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
python scripts/fetch_news.py
python scripts/generate_site.py
open docs/index.html   # Macの場合。Windowsはstart docs/index.html
```

## カスタマイズのポイント

- **カテゴリを増やす**: `scripts/fetch_news.py` の `CATEGORIES` と
  `scripts/generate_site.py` の `CATEGORY_SLUG`、`templates/index.html.j2`
  の `.cat-*` のCSSを対応させて追加する。
- **記事の保持件数**: `fetch_news.py` の `merge_articles()` 内 `merged[:60]`。
- **リード記事の選び方**: `generate_site.py` の `pick_lead()` の
  `priority` 辞書で、優先したいカテゴリを調整できる。
- **使用モデル**: `fetch_news.py` の `MODEL` 定数。最新モデル名は
  https://docs.claude.com のドキュメントで確認してから差し替えること。
- **用語集ページなどの追加**: 今回は「最新ニュース」1ページ構成。
  ページを増やす場合は `templates/` に新しいテンプレートを足し、
  `generate_site.py` に生成処理を追加する形になる。

## 現時点でまだ自動化していないこと(次にやるなら)

- 用語集ページ(業界用語の解説) — 検索流入・雑学系動画のネタ元として有効
- 記事本文からの動画台本の自動生成
- X(旧Twitter)やLINE通知などへの新着プッシュ

## 設計上の注意

- `comment_ja`(一言コメント)は完全にAI生成です。「現場の人間が書いた視点」
  としての価値ではなく、「継続して蓄積されたデータと要約の網羅性」の方が
  長期的な資産になる、という前提で設計しています。人間の一次情報としての
  重みを出したい場合は、このフィールドだけ手動で上書きする運用に切り替える
  こともできます(`data/news.json` を直接編集すればOK)。
