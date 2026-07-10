# OneNote to Obsidian

[中文](README.md) | [English](README.en.md)

クラウドに同期された OneNote ノートブックを、Obsidian で使いやすい Markdown に移行する小さな Python ツールです。

## 主な機能

- Microsoft OAuth Device Code Flow を使い、読み取り専用の `Notes.Read` 権限だけを要求します。
- ノートブック、セクション、入れ子のセクション グループ、ページを出力します。
- 画像、PDF、Office 文書、一般的な音声・動画添付を `attachments/` に保存します。
- タイトル、太字、斜体、ハイライト、タスク、リンク、単純な表を Markdown に変換します。
- 作成・更新時刻と OneNote ページ ID を frontmatter に保存し、安全に再実行できます。
- Microsoft Graph のレート制限と一時的な 5xx エラーを再試行します。

## インストールと実行

```bash
git clone https://github.com/YOUR_USERNAME/onenote-to-obsidian.git
cd onenote-to-obsidian
pip3 install -r requirements.txt
brew install pandoc # macOS
python3 onenote_to_obsidian.py --output ~/Documents/MyVault/OneNote
```

初回実行時には Microsoft のサインイン URL と一回限りのコードが表示されます。小さく検証する場合は次のように実行します。

```bash
python3 onenote_to_obsidian.py --output ~/Documents/MyVault/OneNote --notebook "テスト ノートブック"
```

職場・学校アカウントでは `--tenant common` を使用できます。トークンはローカルの `~/.onenote_migrate_token.json` にのみ保存され、Git には含まれません。

## 仕組み

Microsoft Graph で OneNote を列挙し、各ページを HTML として取得します。Graph リソースをローカル添付へ置き換え、認識できる書式を変換してから Pandoc で Markdown を生成します。OneNote ページ ID により再実行時は既存ファイルを更新します。

## 実データでの検証

実アカウントで 88/88 ページの移行に成功しました。PDF、Word、画像、MP4 音声、表、タスク、書式を含む検証ノートブックも 2/2 ページ成功しています。

## 制限事項

OneNote の自由配置キャンバスは Markdown に完全には表現できません。位置、フォント、文字色、背景、テンプレート、罫線、履歴、ページ パスワード、ネイティブ タグ、複雑な表は失われるか簡略化されます。Graph HTML に明示された意味だけを確実に変換できます。OneNote 内部リンクは Obsidian の wikilink には変換されません。

移行後もしばらくは OneNote の原本を残し、重要なノートを確認してください。

## テスト

```bash
python3 -m unittest -v test_onenote_to_obsidian.py
```

## License

[MIT](LICENSE)
