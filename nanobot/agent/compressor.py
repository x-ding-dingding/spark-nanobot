"""Background context compressor for memory management.

Replaces the simple Summarizer with a structured compression system that
extracts QA pairs (event memories) and long-term memories from conversations.
"""

import asyncio
import copy
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiosqlite
from loguru import logger

from nanobot.providers.base import LLMProvider
from nanobot.utils.helpers import get_data_path

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class LongTermMemoryItem:
    """A long-term memory extracted from conversation (preference/convention/lesson)."""
    category: str  # preference | convention | lesson
    content: str


@dataclass(frozen=True, slots=True)
class EventMemoryItem:
    """A completed event extracted as a QA pair with keyword index."""
    question: str
    conclusion: str
    keywords: list[str]


@dataclass(slots=True)
class CompressionResult:
    """Result of a compression pass."""
    qa_pairs: list[EventMemoryItem]
    long_term_memories: list[LongTermMemoryItem]

    @property
    def reconstructed_summary(self) -> str:
        """Build a summary string from QA pairs for session.summary storage."""
        lines = []
        for i, qa in enumerate(self.qa_pairs, 1):
            lines.append(f"[Event {i}] Q: {qa.question}\nA: {qa.conclusion}")
        return "\n\n".join(lines)


# ---------------------------------------------------------------------------
# Compression prompts
# ---------------------------------------------------------------------------

COMPRESSION_INSTRUCTION = """Please analyze our conversation above and extract the following in JSON format:

{
  "qa_pairs": [
    {
      "question": "concise question describing the task/topic",
      "conclusion": "concise conclusion/answer/outcome",
      "keywords": ["keyword1", "keyword2"]
    }
  ],
  "long_term_memories": [
    {
      "category": "preference|convention|lesson",
      "content": "memory content"
    }
  ]
}

Rules:
1. qa_pairs: Extract completed events/tasks as Q&A pairs. Skip any incomplete events (question asked but no conclusion yet).
2. long_term_memories: Extract user preferences, conventions, or lessons learned that should be remembered long-term.
3. keywords: Include key entities and topic tags for each Q&A pair.
4. Only output valid JSON, no other text."""

COMPRESSION_INSTRUCTION_WITH_PREVIOUS = """Please analyze our conversation above and extract the following in JSON format.

There is a previous summary from earlier conversation that has already been compressed:
--- Previous Summary ---
{previous_summary}
--- End Previous Summary ---

Now extract NEW events from the conversation above (do not re-extract events already in the previous summary):

{{
  "qa_pairs": [
    {{
      "question": "concise question describing the task/topic",
      "conclusion": "concise conclusion/answer/outcome",
      "keywords": ["keyword1", "keyword2"]
    }}
  ],
  "long_term_memories": [
    {{
      "category": "preference|convention|lesson",
      "content": "memory content"
    }}
  ]
}}

Rules:
1. qa_pairs: Extract completed events/tasks as Q&A pairs. Skip any incomplete events (question asked but no conclusion yet).
2. long_term_memories: Extract user preferences, conventions, or lessons learned that should be remembered long-term.
3. keywords: Include key entities and topic tags for each Q&A pair.
4. Only extract NEW information not already covered in the previous summary.
5. Only output valid JSON, no other text."""


# ---------------------------------------------------------------------------
# SQLite schema
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS event_memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_key TEXT NOT NULL,
    question TEXT NOT NULL,
    conclusion TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS event_keywords (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    keyword TEXT NOT NULL,
    FOREIGN KEY (event_id) REFERENCES event_memories(id)
);

CREATE INDEX IF NOT EXISTS idx_event_keywords_keyword
    ON event_keywords(keyword);
"""


# ---------------------------------------------------------------------------
# Compressor
# ---------------------------------------------------------------------------

class Compressor:
    """Background context compressor that replaces Summarizer.

    When triggered, it:
    1. Appends a compression instruction to the current messages (reusing KV cache)
    2. Calls the LLM to extract QA pairs + long-term memories
    3. Stores event memories in SQLite via aiosqlite
    4. Appends long-term memories to MEMORY.md
    5. Updates session.summary with reconstructed_summary
    6. Trims session.messages to keep only the most recent N turns
    """

    RECENT_TURNS_TO_KEEP = 3

    def __init__(self, provider: LLMProvider, model: str, workspace: Path):
        self.provider = provider
        self.model = model
        self.workspace = workspace
        self._db_path = get_data_path() / "memory.db"
        self._db_initialized = False

    # -- Public API (matches Summarizer interface) --------------------------

    def fire_and_forget(
        self,
        session: "Session",
        session_manager: "SessionManager",
        messages_snapshot: list[dict[str, Any]],
        previous_summary: str,
        min_keep: int,
    ) -> None:
        """Launch a background compression task.

        Args:
            session: The live Session object (will be mutated on completion).
            session_manager: Used to persist the session after compression.
            messages_snapshot: A copy of session.messages at trigger time.
            previous_summary: The existing summary to incorporate.
            min_keep: Number of recent messages to retain (unused — we use turn-based keeping).
        """
        task = asyncio.create_task(
            self._do_compress(
                session, session_manager, messages_snapshot, previous_summary
            )
        )
        task.add_done_callback(self._on_task_done)

    # -- Internal -----------------------------------------------------------

    def _on_task_done(self, task: asyncio.Task) -> None:
        """Log any unhandled exception from the background task."""
        if task.cancelled():
            return
        exception = task.exception()
        if exception:
            logger.warning(f"Background compression failed: {exception}")

    async def _do_compress(
        self,
        session: "Session",
        session_manager: "SessionManager",
        messages_snapshot: list[dict[str, Any]],
        previous_summary: str,
    ) -> None:
        """Core compression logic."""
        try:
            logger.info(
                f"[Compressor] Starting compression for {session.key}: "
                f"{len(messages_snapshot)} messages in snapshot"
            )

            # 1. Build compression messages: append instruction to snapshot (reuse KV cache)
            compress_messages = copy.deepcopy(messages_snapshot)
            if previous_summary:
                instruction = COMPRESSION_INSTRUCTION_WITH_PREVIOUS.format(
                    previous_summary=previous_summary
                )
            else:
                instruction = COMPRESSION_INSTRUCTION
            compress_messages.append({"role": "user", "content": instruction})

            # 2. Call LLM
            logger.info(f"[Compressor] Calling LLM for compression (model: {self.model})...")
            response = await self.provider.chat(
                messages=compress_messages,
                tools=None,
                model=self.model,
                max_tokens=2048,
                temperature=0.3,
            )

            # 3. Parse JSON response (with fallback)
            result = self._parse_compression_response(response.content or "")
            if result is None:
                logger.warning("[Compressor] Failed to parse LLM response, skipping compression")
                return

            logger.info(
                f"[Compressor] Parsed {len(result.qa_pairs)} QA pairs, "
                f"{len(result.long_term_memories)} long-term memories"
            )

            # 4. Store event memories + keyword index → SQLite
            if result.qa_pairs:
                await self._save_event_memories(session.key, result.qa_pairs)

            # 5. Append long-term memories → MEMORY.md
            if result.long_term_memories:
                self._append_long_term_memories(result.long_term_memories)

            # 6. Build new summary: previous + new QA pairs
            if previous_summary and result.qa_pairs:
                session.summary = previous_summary + "\n\n" + result.reconstructed_summary
            elif result.qa_pairs:
                session.summary = result.reconstructed_summary
            # If no qa_pairs extracted, keep previous summary unchanged

            # 7. Trim session.messages: keep recent N turns
            #    Read from session.messages CURRENT state (not snapshot) to handle
            #    new messages that arrived during compression.
            messages_before = len(session.messages)
            kept = self._keep_recent_turns(session.messages, self.RECENT_TURNS_TO_KEEP)
            session.messages = kept
            messages_after = len(session.messages)

            # 8. Persist
            session.summary_in_progress = False
            session_manager.save(session)

            logger.info(
                f"[Compressor] ✓ Compression completed for {session.key}\n"
                f"  Messages: {messages_before} → {messages_after} "
                f"(trimmed {messages_before - messages_after})\n"
                f"  QA pairs stored: {len(result.qa_pairs)}\n"
                f"  Long-term memories: {len(result.long_term_memories)}"
            )

        except Exception as exc:
            logger.warning(f"Compression error for {session.key}: {exc}")
        finally:
            session.summary_in_progress = False

    # -- JSON parsing -------------------------------------------------------

    @staticmethod
    def _parse_compression_response(content: str) -> CompressionResult | None:
        """Parse the LLM JSON response with fallback to code-block extraction."""
        if not content:
            return None

        # Try direct JSON parse
        data = None
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            pass

        # Fallback: extract from markdown code block
        if data is None:
            match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(1))
                except json.JSONDecodeError:
                    return None
            else:
                return None

        qa_pairs = [
            EventMemoryItem(
                question=qa.get("question", ""),
                conclusion=qa.get("conclusion", ""),
                keywords=qa.get("keywords", []),
            )
            for qa in data.get("qa_pairs", [])
            if qa.get("question") and qa.get("conclusion")
        ]

        long_term = [
            LongTermMemoryItem(
                category=m.get("category", "general"),
                content=m.get("content", ""),
            )
            for m in data.get("long_term_memories", [])
            if m.get("content")
        ]

        return CompressionResult(qa_pairs=qa_pairs, long_term_memories=long_term)

    # -- Turn-based trimming ------------------------------------------------

    @staticmethod
    def _keep_recent_turns(messages: list[dict[str, Any]], turns_to_keep: int = 3) -> list[dict[str, Any]]:
        """Keep the most recent N turns of messages.

        A turn starts at a ``role=user`` message and includes all subsequent
        assistant / tool messages until the next user message.  Cutting at
        user-message boundaries guarantees we never orphan tool-result
        messages.
        """
        user_indices = [i for i, msg in enumerate(messages) if msg.get("role") == "user"]

        if len(user_indices) <= turns_to_keep:
            return list(messages)  # Not enough turns, keep all

        keep_from = user_indices[-turns_to_keep]
        return list(messages[keep_from:])

    # -- SQLite storage -----------------------------------------------------

    async def _ensure_db(self) -> None:
        """Create tables if they don't exist yet."""
        if self._db_initialized:
            return
        async with aiosqlite.connect(self._db_path) as db:
            await db.executescript(_SCHEMA_SQL)
            await db.commit()
        self._db_initialized = True

    async def _save_event_memories(
        self, session_key: str, qa_pairs: list[EventMemoryItem]
    ) -> None:
        """Persist QA pairs and their keyword indices to SQLite."""
        await self._ensure_db()

        from datetime import datetime

        async with aiosqlite.connect(self._db_path) as db:
            for qa in qa_pairs:
                cursor = await db.execute(
                    "INSERT INTO event_memories (session_key, question, conclusion, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    (session_key, qa.question, qa.conclusion, datetime.now().isoformat()),
                )
                event_id = cursor.lastrowid

                for keyword in qa.keywords:
                    normalized = keyword.strip().lower()
                    if normalized:
                        await db.execute(
                            "INSERT INTO event_keywords (event_id, keyword) VALUES (?, ?)",
                            (event_id, normalized),
                        )

            await db.commit()

        logger.debug(
            f"[Compressor] Saved {len(qa_pairs)} event memories for {session_key}"
        )

    # -- Long-term memory ---------------------------------------------------

    def _append_long_term_memories(self, items: list[LongTermMemoryItem]) -> None:
        """Append extracted long-term memories to MEMORY.md via MemoryStore."""
        from nanobot.agent.memory import MemoryStore

        memory = MemoryStore(self.workspace)
        memory.append_long_term([
            {"category": item.category, "content": item.content}
            for item in items
        ])
        logger.debug(f"[Compressor] Appended {len(items)} long-term memories to MEMORY.md")

    # -- Query API (used by MemoryRecallTool) -------------------------------

    async def search_event_memories(
        self, keywords: list[str], top_k: int = 5
    ) -> list[dict[str, Any]]:
        """Search event memories by keyword matching.

        Returns the top_k events with the most keyword matches, ordered by
        match count descending, then by recency.
        """
        await self._ensure_db()

        if not keywords:
            return []

        normalized = [kw.strip().lower() for kw in keywords if kw.strip()]
        if not normalized:
            return []

        placeholders = ",".join("?" for _ in normalized)
        query = f"""
            SELECT em.id, em.session_key, em.question, em.conclusion, em.created_at,
                   COUNT(ek.id) AS match_count
            FROM event_memories em
            JOIN event_keywords ek ON ek.event_id = em.id
            WHERE ek.keyword IN ({placeholders})
            GROUP BY em.id
            ORDER BY match_count DESC, em.created_at DESC
            LIMIT ?
        """

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, (*normalized, top_k)) as cursor:
                rows = await cursor.fetchall()

        return [
            {
                "id": row["id"],
                "session_key": row["session_key"],
                "question": row["question"],
                "conclusion": row["conclusion"],
                "created_at": row["created_at"],
                "match_count": row["match_count"],
            }
            for row in rows
        ]
