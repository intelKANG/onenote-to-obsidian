# OneNote to Obsidian

[中文](README.zh-CN.md) | [日本語](README.ja.md)

A small Python tool that exports cloud-synced OneNote notebooks to local Markdown files compatible with Obsidian. It does not import into, open, or modify an Obsidian vault.

## What it does

- Uses Microsoft OAuth Device Code Flow with read-only `Notes.Read` access.
- Exports notebooks, sections, nested section groups, and pages.
- Downloads accessible images and attachments, including PDF, Office files, and common audio/video files.
- Preserves page metadata and timestamps; macOS also attempts to restore file creation time.
- Converts supported titles, bold/italic text, highlights, tasks, links, and simple tables to Markdown.
- Safely resumes runs by updating files matched by their OneNote page ID.
- Retries Microsoft Graph throttling and transient 5xx failures.

## Install and run

```bash
git clone https://github.com/YOUR_USERNAME/onenote-to-obsidian.git
cd onenote-to-obsidian
pip3 install -r requirements.txt
brew install pandoc # macOS
python3 onenote_to_obsidian.py --output ~/Documents/MyVault/OneNote
```

The first run prints a Microsoft sign-in URL and a one-time code. For a small validation run:

```bash
python3 onenote_to_obsidian.py --output ~/Documents/MyVault/OneNote --notebook "Test notebook"
```

Use `--tenant common` for work or school accounts. Tokens stay locally in `~/.onenote_migrate_token.json` and are excluded from Git.

## How it works

The script lists OneNote content through Microsoft Graph, fetches each page as HTML, localizes Graph resources into `attachments/`, applies small semantic conversions, then calls Pandoc to create Markdown. Each note stores its OneNote ID in frontmatter, which makes reruns idempotent.

## Verified with real data

A real-account migration completed 88/88 pages. A focused acceptance notebook containing PDF, Word, image, MP4 audio, table, tasks, and formatted text completed 2/2 pages after compatibility fixes.

## Limits

OneNote's free-form canvas cannot be represented exactly in Markdown: positioning, fonts, colors, backgrounds, templates, grid lines, revision history, page passwords, native tags, and some complex tables will be lost or reduced. Only semantics explicitly present in the Graph HTML can be recognized; plain paragraphs that merely look like code or quotes cannot be inferred safely. OneNote-internal links are kept as URLs, not converted to Obsidian wikilinks.

Keep the OneNote original and sample-check important notes before deleting anything.

## Test

```bash
python3 -m unittest -v test_onenote_to_obsidian.py
```

## License

[MIT](LICENSE)
