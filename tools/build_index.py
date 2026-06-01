#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EXPORT_CONVERSATIONS = "conversations.json"
DEFAULT_OUTPUT = Path("data/search-index.json")
VISIBLE_ROLES = {"user", "assistant"}
VISIBLE_CONTENT_TYPES = {"text", "multimodal_text", "code", "execution_output"}
HIDDEN_METADATA_FLAGS = {
    "hidden",
    "is_hidden",
    "is_user_system_message",
    "is_visually_hidden_from_conversation",
}
HIDDEN_MESSAGE_TYPES = {"hidden", "system"}
IGNORED_SEARCH_DIRS = {".git", "data", "tools", "__pycache__"}
DEFAULT_EXPORTS_DIR = Path("exports")
DEFAULT_MAX_JSON_MB = 500
DEFAULT_MAX_PDF_PAGES = 500
INDEX_VERSION = 2


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def iso_from_timestamp(value: Any) -> str | None:
    if not isinstance(value, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(value, timezone.utc).isoformat().replace("+00:00", "Z")
    except (OverflowError, OSError, ValueError):
        return None


def clean_text(value: str) -> str:
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"[ \t]+\n", "\n", value)
    value = re.sub(r"\n{4,}", "\n\n\n", value)
    return value.strip()


def text_from_part(part: Any) -> str:
    if isinstance(part, str):
        return part
    if not isinstance(part, dict):
        return ""

    content_type = part.get("content_type") or part.get("type")
    if content_type in {None, "text"} and isinstance(part.get("text"), str):
        return part.get("text") or ""
    if content_type == "image_asset_pointer":
        return "[image]"
    if content_type == "audio_asset_pointer":
        return "[audio]"
    if content_type == "real_time_user_audio_video_asset_pointer":
        return "[audio/video]"
    return ""


def content_to_text(content: dict[str, Any]) -> str:
    content_type = content.get("content_type")

    if content_type in {"text", "multimodal_text"}:
        parts = content.get("parts") or []
        if isinstance(parts, str):
            parts = [parts]
        elif not isinstance(parts, list):
            parts = []
        return clean_text("\n".join(text for text in (text_from_part(part) for part in parts) if text))

    if content_type == "code":
        language = content.get("language")
        text = content.get("text") or ""
        if language and text:
            return clean_text(f"```{language}\n{text}\n```")
        return clean_text(text)

    if content_type == "execution_output":
        return clean_text(content.get("text") or "")

    return ""


def safe_basename(value: Any) -> str | None:
    name = clean_text(str(value or "").replace("\\", "/").rstrip("/"))
    if not name:
        return None
    name = name.rsplit("/", 1)[-1]
    if name in {"", ".", ".."}:
        return None
    return name


def extract_attachments(metadata: dict[str, Any]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for attachment in metadata.get("attachments") or []:
        if not isinstance(attachment, dict):
            continue
        name = safe_basename(attachment.get("name") or attachment.get("file_name") or attachment.get("id"))
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return names


def is_hidden_metadata(metadata: dict[str, Any]) -> bool:
    for flag in HIDDEN_METADATA_FLAGS:
        if metadata.get(flag) is True:
            return True
    message_type = str(metadata.get("message_type") or "").lower()
    return message_type in HIDDEN_MESSAGE_TYPES


def ordered_mapping_nodes(conversation: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    mapping = conversation.get("mapping") or {}
    current = conversation.get("current_node")
    ordered: list[tuple[str, dict[str, Any]]] = []
    seen: set[str] = set()

    while current and current in mapping and current not in seen:
        seen.add(current)
        node = mapping[current]
        ordered.append((current, node))
        current = node.get("parent")

    if ordered:
        ordered.reverse()
        return ordered

    def sort_key(item: tuple[str, dict[str, Any]]) -> tuple[float, str]:
        _, node = item
        message = node.get("message") or {}
        created = message.get("create_time")
        return (created if isinstance(created, (int, float)) else 0.0, item[0])

    return sorted(mapping.items(), key=sort_key)


def message_from_node(node_id: str, node: dict[str, Any]) -> dict[str, Any] | None:
    message = node.get("message")
    if not isinstance(message, dict):
        return None

    author = message.get("author") or {}
    if not isinstance(author, dict):
        author = {}
    raw_role = author.get("role")
    role = raw_role if isinstance(raw_role, str) and raw_role else "unknown"
    content = message.get("content") or {}
    if not isinstance(content, dict):
        content = {}
    metadata = message.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}

    raw_content_type = content.get("content_type")
    content_type = raw_content_type if isinstance(raw_content_type, str) and raw_content_type else "unknown"
    visible = role in VISIBLE_ROLES and content_type in VISIBLE_CONTENT_TYPES and not is_hidden_metadata(metadata)
    text = content_to_text(content) if visible else ""
    attachments = extract_attachments(metadata) if visible else []

    record: dict[str, Any] = {
        "role": role,
        "createTime": iso_from_timestamp(message.get("create_time")),
        "contentType": content_type,
        "text": text,
        "visible": visible,
    }
    if attachments:
        record["attachments"] = attachments
    model = metadata.get("model_slug")
    if isinstance(model, str) and model:
        record["model"] = model
    return record


def first_visible_snippet(messages: list[dict[str, Any]]) -> str:
    for message in messages:
        if is_visible_message(message) and message["role"] == "user" and message["text"]:
            return clean_text(message["text"])[:240]
    for message in messages:
        if is_visible_message(message) and message["text"]:
            return clean_text(message["text"])[:240]
    return ""


def is_visible_message(message: dict[str, Any]) -> bool:
    if message.get("visible") is False:
        return False
    return message["role"] in VISIBLE_ROLES and message["contentType"] in VISIBLE_CONTENT_TYPES


def build_conversations(raw_conversations: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    conversations: list[dict[str, Any]] = []
    global_roles: Counter[str] = Counter()
    global_content_types: Counter[str] = Counter()
    total_messages = 0
    total_visible_messages = 0
    date_values: list[str] = []

    for index, conversation in enumerate(raw_conversations):
        messages: list[dict[str, Any]] = []
        for node_id, node in ordered_mapping_nodes(conversation):
            message = message_from_node(node_id, node)
            if message:
                messages.append(message)

        role_counts = Counter(message["role"] for message in messages)
        content_counts = Counter(message["contentType"] for message in messages)
        visible_count = sum(1 for message in messages if is_visible_message(message))
        global_roles.update(role_counts)
        global_content_types.update(content_counts)
        total_messages += len(messages)
        total_visible_messages += visible_count

        created = iso_from_timestamp(conversation.get("create_time"))
        updated = iso_from_timestamp(conversation.get("update_time"))
        if created:
            date_values.append(created)
        if updated:
            date_values.append(updated)

        conversation_id = f"conversation-{index + 1}"
        title = clean_text(str(conversation.get("title") or "Untitled conversation"))

        model = conversation.get("default_model_slug")
        conversations.append(
            {
                "id": conversation_id,
                "title": title,
                "createTime": created,
                "updateTime": updated,
                "model": model if isinstance(model, str) and model else None,
                "isArchived": bool(conversation.get("is_archived")),
                "isStarred": bool(conversation.get("is_starred")),
                "messageCount": len(messages),
                "visibleMessageCount": visible_count,
                "roleCounts": dict(sorted(role_counts.items())),
                "contentTypes": dict(sorted(content_counts.items())),
                "snippet": first_visible_snippet(messages),
                "messages": messages,
            }
        )

    stats = {
        "conversationCount": len(conversations),
        "messageCount": total_messages,
        "visibleMessageCount": total_visible_messages,
        "roleCounts": dict(sorted(global_roles.items())),
        "contentTypes": dict(sorted(global_content_types.items())),
        "oldestTime": min(date_values) if date_values else None,
        "newestTime": max(date_values) if date_values else None,
    }
    return conversations, stats


def is_private_search_candidate(path: Path) -> bool:
    return not any(part in IGNORED_SEARCH_DIRS for part in path.parts)


def find_conversations_entry(zip_path: Path) -> str:
    with zipfile.ZipFile(zip_path) as archive:
        matches = [name for name in archive.namelist() if name.endswith("/" + EXPORT_CONVERSATIONS) or name == EXPORT_CONVERSATIONS]
    if not matches:
        raise FileNotFoundError(f"Selected ZIP does not contain {EXPORT_CONVERSATIONS}.")
    return sorted(matches, key=len)[0]


def find_export_zip(root: Path) -> Path:
    if not root.exists():
        raise FileNotFoundError("exports/ does not exist.")
    candidates = sorted(
        (path for path in root.rglob("*.zip") if is_private_search_candidate(path)),
        key=lambda path: (0 if "exports" in path.parts else 1, len(path.parts), str(path).lower()),
    )
    if not candidates:
        raise FileNotFoundError("No ChatGPT export ZIP was found.")

    for candidate in candidates:
        try:
            find_conversations_entry(candidate)
            return candidate
        except Exception:
            continue
    raise FileNotFoundError("No ZIP in this folder contains conversations.json.")


def find_export_dir(root: Path) -> Path | None:
    if not root.exists():
        return None
    candidates = sorted(
        (path for path in root.rglob(EXPORT_CONVERSATIONS) if is_private_search_candidate(path)),
        key=lambda path: (0 if "exports" in path.parts else 1, len(path.parts), str(path).lower()),
    )
    for candidate in candidates:
        return candidate.parent
    return None


def validate_json_size(size: int, max_json_mb: int) -> None:
    if max_json_mb <= 0:
        return
    max_bytes = max_json_mb * 1024 * 1024
    if size > max_bytes:
        raise ValueError(f"conversations.json is {size / (1024 * 1024):.1f} MB, above --max-json-mb {max_json_mb}.")


def load_export_from_zip(zip_path: Path, max_json_mb: int) -> list[dict[str, Any]]:
    entry = find_conversations_entry(zip_path)
    with zipfile.ZipFile(zip_path) as archive:
        validate_json_size(archive.getinfo(entry).file_size, max_json_mb)
        with archive.open(entry) as handle:
            data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError("conversations.json did not contain the expected list.")
    return data


def load_export_from_dir(export_dir: Path, max_json_mb: int) -> list[dict[str, Any]]:
    conversations_path = export_dir / EXPORT_CONVERSATIONS
    if not conversations_path.exists():
        raise FileNotFoundError(f"Selected export folder does not contain {EXPORT_CONVERSATIONS}.")
    validate_json_size(conversations_path.stat().st_size, max_json_mb)
    with conversations_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError("conversations.json did not contain the expected list.")
    return data


def build_pdf_documents(root: Path, pdf_dir: Path, max_pages: int | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    try:
        from pypdf import PdfReader
    except Exception as exc:
        print(f"PDF indexing skipped because pypdf is unavailable: {exc}", file=sys.stderr)
        return [], {"pdfCount": 0, "pdfPageCount": 0}

    documents: list[dict[str, Any]] = []
    pdf_count = 0
    page_count = 0

    pdf_paths = sorted(path for path in pdf_dir.rglob("*.pdf") if is_private_search_candidate(path))
    for pdf_index, pdf_path in enumerate(pdf_paths, start=1):
        pdf_count += 1
        pdf_label = safe_basename(pdf_path) or f"document-{pdf_index}.pdf"
        pdf_title = Path(pdf_label).stem
        reader = PdfReader(str(pdf_path))
        total_pages = len(reader.pages)
        limit = min(total_pages, max_pages) if max_pages else total_pages
        for page_index in range(limit):
            text = clean_text(reader.pages[page_index].extract_text() or "")
            if not text:
                continue
            page_number = page_index + 1
            page_count += 1
            documents.append(
                {
                    "id": f"pdf-{pdf_index}-page-{page_number}",
                    "kind": "pdf",
                    "title": f"{pdf_title} page {page_number}",
                    "source": pdf_label,
                    "page": page_number,
                    "pageCount": total_pages,
                    "text": text,
                }
            )

    return documents, {"pdfCount": pdf_count, "pdfPageCount": page_count}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a local search index for a ChatGPT export.")
    parser.add_argument("--zip", dest="zip_path", type=Path, help="Path to the ChatGPT export ZIP.")
    parser.add_argument("--export-dir", type=Path, help="Path to an unzipped ChatGPT export folder.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output JSON path.")
    parser.add_argument("--include-pdfs", action="store_true", help="Also index loose PDFs in this folder.")
    parser.add_argument("--pdf-dir", type=Path, help="Directory to scan for PDFs. Defaults to exports/.")
    parser.add_argument("--max-json-mb", type=int, default=DEFAULT_MAX_JSON_MB, help="Maximum conversations.json size in MB. Use 0 for no cap.")
    parser.add_argument("--max-pdf-pages", type=int, default=DEFAULT_MAX_PDF_PAGES, help="Maximum pages per PDF when --include-pdfs is used. Use 0 for no cap.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path.cwd()

    source: dict[str, Any]
    default_import_root = root / DEFAULT_EXPORTS_DIR
    try:
        if args.export_dir:
            export_dir = args.export_dir if args.export_dir.is_absolute() else root / args.export_dir
            print("Reading export folder...")
            raw_conversations = load_export_from_dir(export_dir, args.max_json_mb)
            source = {"type": "exportDir"}
        elif args.zip_path:
            zip_path = args.zip_path if args.zip_path.is_absolute() else root / args.zip_path
            print("Reading export ZIP...")
            raw_conversations = load_export_from_zip(zip_path, args.max_json_mb)
            source = {"type": "zip"}
        else:
            export_dir = find_export_dir(default_import_root)
            if export_dir:
                print("Reading export folder...")
                raw_conversations = load_export_from_dir(export_dir, args.max_json_mb)
                source = {"type": "exportDir"}
            else:
                zip_path = find_export_zip(default_import_root)
                print("Reading export ZIP...")
                raw_conversations = load_export_from_zip(zip_path, args.max_json_mb)
                source = {"type": "zip"}
    except (FileNotFoundError, ValueError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        print("Put a ChatGPT export ZIP or extracted folder containing conversations.json in exports/,", file=sys.stderr)
        print("or pass --zip / --export-dir explicitly.", file=sys.stderr)
        return 1

    conversations, stats = build_conversations(raw_conversations)

    documents: list[dict[str, Any]] = []
    pdf_stats = {"pdfCount": 0, "pdfPageCount": 0}
    if args.include_pdfs:
        print("Indexing PDFs...")
        pdf_dir = args.pdf_dir if args.pdf_dir and args.pdf_dir.is_absolute() else root / (args.pdf_dir or DEFAULT_EXPORTS_DIR)
        max_pdf_pages = None if args.max_pdf_pages == 0 else args.max_pdf_pages
        documents, pdf_stats = build_pdf_documents(root, pdf_dir, max_pdf_pages)

    payload = {
        "version": INDEX_VERSION,
        "generatedAt": utc_now(),
        "source": {
            **source,
            "pdfsIncluded": bool(args.include_pdfs),
        },
        "stats": {**stats, **pdf_stats},
        "conversations": conversations,
        "documents": documents,
    }

    output_path = args.output
    if not output_path.is_absolute():
        output_path = root / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"Wrote {safe_basename(output_path) or 'search-index.json'} ({size_mb:.1f} MB)")
    print(f"Indexed {stats['conversationCount']} conversations and {stats['messageCount']} messages.")
    if args.include_pdfs:
        print(f"Indexed {pdf_stats['pdfPageCount']} PDF pages.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
