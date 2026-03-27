"""Mini-compaction: rule-based history cleanup before each LLM request.

Runs purely on rules (no LLM calls, zero cost) to reduce context size:
1. Old tool results: only keep full text for the most recent N turns,
   replace older ones with a short placeholder.
2. Image/document placeholders: replace inline image and document content
   blocks with lightweight text placeholders.
3. Large output truncation: head+tail truncate any single tool output
   that still exceeds a character threshold.
"""

from __future__ import annotations

import copy
from typing import Any

# How many recent "tool-call turns" keep their full tool results.
# A turn = one assistant message with tool_calls + the subsequent tool messages.
RECENT_TURNS_TO_KEEP = 3

# Character threshold for per-message truncation (applied to all turns).
LARGE_OUTPUT_THRESHOLD = 10_000
LARGE_OUTPUT_HEAD = 4_000
LARGE_OUTPUT_TAIL = 2_000

_TOOL_TRUNCATED_PLACEHOLDER = "[tool result omitted for brevity]"


def mini_compact(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply mini-compaction to a history message list.

    Returns a *new* list (the original is not mutated).
    """
    if not history:
        return history

    compacted = copy.deepcopy(history)

    # --- Step 1 & 2: identify tool-call turns and compact old ones ---
    turn_boundaries = _find_tool_turn_boundaries(compacted)
    recent_cutoff = len(turn_boundaries) - RECENT_TURNS_TO_KEEP

    for turn_index, (assistant_idx, tool_indices) in enumerate(turn_boundaries):
        is_old_turn = turn_index < recent_cutoff

        for tool_idx in tool_indices:
            msg = compacted[tool_idx]
            content = msg.get("content", "")

            if is_old_turn:
                # Replace old tool results with placeholder
                msg["content"] = _TOOL_TRUNCATED_PLACEHOLDER
            elif isinstance(content, str) and len(content) > LARGE_OUTPUT_THRESHOLD:
                # Step 3: head+tail truncate large outputs in recent turns
                msg["content"] = _truncate_head_tail(content)

    # --- Step 2: replace image/document content blocks everywhere ---
    for msg in compacted:
        content = msg.get("content")
        if isinstance(content, list):
            msg["content"] = _compact_content_blocks(content)

    return compacted


def _find_tool_turn_boundaries(
    messages: list[dict[str, Any]],
) -> list[tuple[int, list[int]]]:
    """Find (assistant_index, [tool_message_indices]) pairs.

    A "tool turn" is an assistant message that has tool_calls, followed by
    one or more tool-role messages.
    """
    turns: list[tuple[int, list[int]]] = []
    idx = 0
    while idx < len(messages):
        msg = messages[idx]
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            assistant_idx = idx
            tool_indices: list[int] = []
            idx += 1
            while idx < len(messages) and messages[idx].get("role") == "tool":
                tool_indices.append(idx)
                idx += 1
            if tool_indices:
                turns.append((assistant_idx, tool_indices))
        else:
            idx += 1
    return turns


def _truncate_head_tail(text: str) -> str:
    """Keep head + tail of a large string, omitting the middle."""
    total = len(text)
    head = text[:LARGE_OUTPUT_HEAD]
    tail = text[-LARGE_OUTPUT_TAIL:]
    omitted = total - LARGE_OUTPUT_HEAD - LARGE_OUTPUT_TAIL
    return (
        f"{head}\n"
        f"... [{omitted:,} chars omitted] ...\n"
        f"{tail}"
    )


def _compact_content_blocks(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Replace image_url and document blocks with lightweight placeholders."""
    compacted: list[dict[str, Any]] = []
    for block in blocks:
        block_type = block.get("type", "")
        if block_type == "image_url":
            compacted.append({"type": "text", "text": "[image]"})
        elif block_type == "document":
            compacted.append({"type": "text", "text": "[document]"})
        else:
            compacted.append(block)
    return compacted
