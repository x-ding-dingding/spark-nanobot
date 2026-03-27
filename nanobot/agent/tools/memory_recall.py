"""Memory recall tool for searching event memories from conversation history."""

from typing import Any

from nanobot.agent.tools.base import Tool


class MemoryRecallTool(Tool):
    """Tool that allows the agent to recall relevant events from past conversations.

    Searches the SQLite event memory store by keyword matching and returns
    the most relevant QA pairs.
    """

    def __init__(self, compressor: "Compressor"):
        self._compressor = compressor

    @property
    def name(self) -> str:
        return "memory_recall"

    @property
    def description(self) -> str:
        return (
            "Recall relevant events from conversation history. "
            "Use when you need to reference previous analyses, conclusions, "
            "or information the user mentioned before."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Keywords to search for in memory",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Max number of memories to return (default 5)",
                },
            },
            "required": ["keywords"],
        }

    async def execute(self, **kwargs: Any) -> str:
        """Search event memories by keywords and return formatted results."""
        keywords = kwargs.get("keywords", [])
        top_k = kwargs.get("top_k", 5)

        if not keywords:
            return "No keywords provided. Please specify keywords to search for."

        results = await self._compressor.search_event_memories(
            keywords=keywords, top_k=top_k
        )

        if not results:
            return f"No memories found matching keywords: {', '.join(keywords)}"

        lines = [f"Found {len(results)} relevant memories:\n"]
        for i, mem in enumerate(results, 1):
            lines.append(
                f"[{i}] Q: {mem['question']}\n"
                f"    A: {mem['conclusion']}\n"
                f"    (from {mem['created_at']}, relevance: {mem['match_count']} keyword matches)"
            )

        return "\n".join(lines)
