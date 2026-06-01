# Local ChatGPT Archive Reader

A small offline search app for ChatGPT exports. It turns a ChatGPT export ZIP, or an extracted export folder containing `conversations.json`, into a local searchable reader.

The reader is designed for private and work chats:

- It serves only on loopback (`127.0.0.1` by default).
- It loads no external scripts, fonts, CDNs, or network assets.
- It keeps the generated search index on your machine.
- Its local server only serves the app files and generated index, not raw exports or `.git/`.
- Export ZIPs, extracted exports, PDFs, and generated indexes are ignored by git.

## Privacy Note

Never commit real ChatGPT exports, generated private indexes, transcripts, screenshots, or fixtures based on real chats. Use local files only, use synthetic samples for development and testing, and keep private backups outside this repository.

The generated `data/search-index.json` contains searchable chat text and is private. Do not commit it, upload it, or share it. Deleting files from `exports/` is not enough if `data/search-index.json` still exists, because the generated index can retain searchable copies of chat and PDF text. See `PRIVACY.md` for cleanup and incident steps.

## Quick Start

1. Put a ChatGPT export ZIP or extracted export folder in `exports/`. This folder is ignored by git.

2. Build the local search index.

Windows:

```powershell
.\build-index.cmd
```

macOS/Linux:

```sh
./build-index.sh
```

You can also point at a specific export:

Windows:

```powershell
.\build-index.cmd --zip "exports\chatgpt-export.zip"
.\build-index.cmd --export-dir "exports\chatgpt-export"
```

macOS/Linux:

```sh
./build-index.sh --zip "exports/chatgpt-export.zip"
./build-index.sh --export-dir "exports/chatgpt-export"
```

3. Start the local reader.

Windows:

```powershell
.\start-reader.cmd
```

macOS/Linux:

```sh
./start-reader.sh
```

4. Open:

```text
http://127.0.0.1:8765
```

## Optional PDF Indexing

Loose PDFs can also be indexed:

Windows:

```powershell
.\build-index.cmd --include-pdfs
```

macOS/Linux:

```sh
./build-index.sh --include-pdfs
```

For very large PDFs, cap the page count while testing:

Windows:

```powershell
.\build-index.cmd --include-pdfs --max-pdf-pages 50
```

macOS/Linux:

```sh
./build-index.sh --include-pdfs --max-pdf-pages 50
```

## Sharing This Tool

Share the app files, scripts, and `tools/` directory. Do not share `exports/`, `data/search-index.json`, ZIPs, PDFs, or extracted export folders unless you intentionally want to share private chat data.

PowerShell versions of the launchers are also included as `build-index.ps1` and `start-reader.ps1`, but the `.cmd` files avoid PowerShell execution-policy issues on Windows.

## Development Checks

Run the standard-library smoke tests with:

```sh
python3 -m unittest discover -s tests
```
