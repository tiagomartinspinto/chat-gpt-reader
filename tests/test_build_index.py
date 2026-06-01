from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_index


def sample_conversation() -> dict:
    return {
        "id": "private-export-id",
        "title": "Search Notes",
        "create_time": 1700000000,
        "update_time": 1700000300,
        "default_model_slug": "demo-model",
        "is_starred": True,
        "mapping": {
            "root": {"parent": None, "message": None},
            "user-1": {
                "parent": "root",
                "message": {
                    "id": "message-user-1",
                    "author": {"role": "user"},
                    "create_time": 1700000000,
                    "content": {
                        "content_type": "multimodal_text",
                        "parts": ["Please keep these project notes searchable."],
                    },
                    "metadata": {
                        "attachments": [{"name": r"C:\Users\person\private\brief.pdf"}],
                    },
                },
            },
            "assistant-1": {
                "parent": "user-1",
                "message": {
                    "id": "message-assistant-1",
                    "author": {"role": "assistant"},
                    "create_time": 1700000300,
                    "content": {
                        "content_type": "text",
                        "parts": ["Use clear titles and concise summaries."],
                    },
                    "metadata": {
                        "model_slug": "gpt-demo",
                    },
                },
            },
        },
        "current_node": "assistant-1",
    }


def privacy_conversation() -> dict:
    return {
        "id": "export-id-that-should-not-persist",
        "title": "Privacy Sample",
        "mapping": {
            "root": {"parent": None, "message": None},
            "visible": {
                "parent": "root",
                "message": {
                    "author": {"role": "user", "name": "Private Person"},
                    "content": {"content_type": "text", "parts": ["Visible searchable text."]},
                    "metadata": {},
                },
            },
            "hidden-text": {
                "parent": "visible",
                "message": {
                    "author": {"role": "assistant"},
                    "content": {"content_type": "text", "parts": ["HIDDEN_TEXT_SHOULD_NOT_BE_INDEXED"]},
                    "metadata": {"is_visually_hidden_from_conversation": True},
                },
            },
            "profile": {
                "parent": "hidden-text",
                "message": {
                    "author": {"role": "system"},
                    "content": {
                        "content_type": "user_editable_context",
                        "user_profile": "PRIVATE_PROFILE_SHOULD_NOT_BE_INDEXED",
                    },
                    "metadata": {},
                },
            },
            "thoughts": {
                "parent": "profile",
                "message": {
                    "author": {"role": "assistant"},
                    "content": {
                        "content_type": "thoughts",
                        "thoughts": [{"summary": "THOUGHTS_SHOULD_NOT_BE_INDEXED"}],
                    },
                    "metadata": {},
                },
            },
            "unknown": {
                "parent": "thoughts",
                "message": {
                    "author": {"role": "assistant"},
                    "content": {
                        "content_type": "unknown_private_type",
                        "payload": {"secret": "UNKNOWN_JSON_SHOULD_NOT_BE_INDEXED"},
                    },
                    "metadata": {},
                },
            },
            "quote": {
                "parent": "unknown",
                "message": {
                    "author": {"role": "assistant"},
                    "content": {
                        "content_type": "tether_quote",
                        "text": "TETHER_QUOTE_SHOULD_NOT_BE_INDEXED",
                    },
                    "metadata": {},
                },
            },
            "error": {
                "parent": "quote",
                "message": {
                    "author": {"role": "assistant"},
                    "content": {
                        "content_type": "system_error",
                        "text": "SYSTEM_ERROR_SHOULD_NOT_BE_INDEXED",
                    },
                    "metadata": {},
                },
            },
        },
        "current_node": "error",
    }


class BuildIndexTests(unittest.TestCase):
    def test_build_conversations_extracts_visible_messages_and_stats(self) -> None:
        conversations, stats = build_index.build_conversations([sample_conversation()])

        self.assertEqual(stats["conversationCount"], 1)
        self.assertEqual(stats["messageCount"], 2)
        self.assertEqual(stats["visibleMessageCount"], 2)
        self.assertEqual(stats["roleCounts"], {"assistant": 1, "user": 1})

        conversation = conversations[0]
        self.assertEqual(conversation["id"], "conversation-1")
        self.assertEqual(conversation["title"], "Search Notes")
        self.assertTrue(conversation["isStarred"])
        self.assertEqual(conversation["snippet"], "Please keep these project notes searchable.")
        self.assertEqual(conversation["messages"][0]["attachments"], ["brief.pdf"])
        self.assertEqual(conversation["messages"][1]["model"], "gpt-demo")

    def test_main_writes_index_from_default_exports_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            export_dir = root / "exports" / "chatgpt-export"
            export_dir.mkdir(parents=True)
            (export_dir / "conversations.json").write_text(
                json.dumps([sample_conversation()]),
                encoding="utf-8",
            )

            original_cwd = Path.cwd()
            try:
                os.chdir(root)
                with mock.patch.object(sys, "argv", ["build_index.py"]):
                    with redirect_stdout(StringIO()):
                        self.assertEqual(build_index.main(), 0)
            finally:
                os.chdir(original_cwd)

            output = root / "data" / "search-index.json"
            self.assertTrue(output.exists())
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["version"], 2)
            self.assertEqual(payload["source"]["type"], "exportDir")
            self.assertEqual(payload["stats"]["conversationCount"], 1)
            self.assertEqual(payload["conversations"][0]["messages"][0]["role"], "user")

    def test_private_and_unknown_content_is_metadata_only(self) -> None:
        conversations, stats = build_index.build_conversations([privacy_conversation()])

        self.assertEqual(stats["messageCount"], 7)
        self.assertEqual(stats["visibleMessageCount"], 1)
        self.assertEqual(conversations[0]["id"], "conversation-1")

        payload_text = json.dumps(conversations, ensure_ascii=False)
        for sentinel in (
            "export-id-that-should-not-persist",
            "Private Person",
            "HIDDEN_TEXT_SHOULD_NOT_BE_INDEXED",
            "PRIVATE_PROFILE_SHOULD_NOT_BE_INDEXED",
            "THOUGHTS_SHOULD_NOT_BE_INDEXED",
            "UNKNOWN_JSON_SHOULD_NOT_BE_INDEXED",
            "TETHER_QUOTE_SHOULD_NOT_BE_INDEXED",
            "SYSTEM_ERROR_SHOULD_NOT_BE_INDEXED",
        ):
            self.assertNotIn(sentinel, payload_text)

        metadata_only = [message for message in conversations[0]["messages"] if not message["visible"]]
        self.assertTrue(metadata_only)
        self.assertTrue(all(message["text"] == "" for message in metadata_only))

    def test_attachment_names_are_reduced_to_basenames(self) -> None:
        conversations, _ = build_index.build_conversations([sample_conversation()])
        payload_text = json.dumps(conversations, ensure_ascii=False)

        self.assertEqual(conversations[0]["messages"][0]["attachments"], ["brief.pdf"])
        self.assertIn("brief.pdf", payload_text)
        self.assertNotIn("C:", payload_text)
        self.assertNotIn("Users", payload_text)


if __name__ == "__main__":
    unittest.main()
