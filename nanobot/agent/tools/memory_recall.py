"""Memory recall tool for searching event memories from conversation history.

Two-step recall flow (zero main-context pollution):
  1. Fetch all composite keys from SQLite → fire an isolated LLM call with
     recent dialogue turns so the model can pick relevant keys from real data.
  2. Exact-match the selected keys in SQLite → inject only the final results
     as a tool result into the main conversation context.
"""

from typing import TYPE_CHECKING, Any

from loguru import logger

from nanobot.agent.tools.base import Tool

if TYPE_CHECKING:
    from nanobot.agent.compressor import Compressor
    from nanobot.providers.base import LLMProvider
    from nanobot.session.manager import Session

# Maximum number of recent user/assistant turns to include in the isolated
# LLM call for context. Tool-call turns are skipped to keep the prompt short.
_CONTEXT_TURNS = 5

_KEY_SELECTION_SYSTEM = (
    "You are a memory retrieval assistant. "
    "Given a list of memory keys and recent conversation context, "
    "select the keys most relevant to the user's current query. "
    "Return ONLY the selected keys, one per line, no explanation."
)


class MemoryRecallTool(Tool):
    """Recall relevant events from past conversations via two-step composite-key lookup.

    Step 1 — Key selection (isolated LLM call, not added to main context):
        - Retrieve all composite keys from SQLite
        - Build a short prompt: lightweight system + recent N dialogue turns + key list
        - Ask the LLM to select the most relevant keys

    Step 2 — Exact retrieval:
        - Fetch matching events from SQLite by exact composite key
        - Return formatted results as the tool result (injected into main context)
    """

    def __init__(
        self,
        compressor: "Compressor",
        provider: "LLMProvider",
    ) -> None:
        self._compressor = compressor
        self._provider = provider
        self._session: "Session | None" = None

    def set_session(self, session: "Session") -> None:
        """Update the current session reference before each message is processed."""
        self._session = session

    @property
    def name(self) -> str:
        return "memory_recall"

    @property
    def description(self) -> str:
        return (
            "Recall relevant events from conversation history. "
            "Use when you need to reference previous analyses, conclusions, "
            "or information the user mentioned before. "
            "Describe what you are looking for in natural language."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Natural language description of what you want to recall. "
                        "E.g. '上次关于 nanobot 配置迁移的讨论结果'"
                    ),
                },
                "top_k": {
                    "type": "integer",
                    "description": "Max number of memories to return (default 5)",
                },
            },
            "required": ["query"],
        }

    async def execute(self, **kwargs: Any) -> str:
        """Two-step recall: isolated LLM key selection → exact SQLite lookup."""
        query = kwargs.get("query", "").strip()
        top_k = int(kwargs.get("top_k", 5))

        if not query:
            return "Please describe what you want to recall."

        if self._session is None:
            return "Memory recall is not available yet (session not initialized)."

        # Step 1: get all composite keys
        all_keys = await self._compressor.get_all_composite_keys()
        if not all_keys:
            return "No memories available yet — memory index is empty."

        # Step 2: isolated LLM call to select relevant keys
        selected_keys = await self._select_keys_via_llm(all_keys, query)
        if not selected_keys:
            return f"No relevant memories found for: {query}"

        # Step 3: exact SQLite lookup
        results = await self._compressor.search_by_composite_keys(selected_keys, top_k=top_k)
        if not results:
            return f"No memories found for selected keys: {', '.join(selected_keys)}"

        return self._format_results(results)

    # -- Private helpers ----------------------------------------------------

    async def _select_keys_via_llm(
        self, all_keys: list[str], query: str
    ) -> list[str]:
        """Fire an isolated LLM call to select relevant composite keys.

        The messages sent here are NOT added to the main conversation context.
        """
        recent_turns = self._get_recent_dialogue_turns(_CONTEXT_TURNS)
        keys_block = "\n".join(f"- {key}" for key in all_keys)

        selection_prompt = (
            f"User query: {query}\n\n"
            f"Available memory keys:\n{keys_block}\n\n"
            "Select the keys most relevant to the query above. "
            "Return only the selected keys, one per line. "
            "If none are relevant, return an empty response."
        )

        messages = (
            [{"role": "system", "content": _KEY_SELECTION_SYSTEM}]
            + recent_turns
            + [{"role": "user", "content": selection_prompt}]
        )

        try:
            response = await self._provider.chat(
                messages=messages,
                tools=None,
                model=self._compressor.model,
                max_tokens=256,
                temperature=0.0,
            )
        except Exception as exc:
            logger.warning(f"[MemoryRecallTool] Key selection LLM call failed: {exc}")
            return []

        raw = (response.content or "").strip()
        if not raw:
            return []

        # Parse: check if any known key appears in LLM output (substring match)
        # This is more robust than exact line matching since LLM may add extra text
        raw_lower = raw.lower()
        selected = []
        for key in all_keys:
            key_lower = key.lower()
            if key_lower in raw_lower:
                selected.append(key_lower)

        return selected

    def _get_recent_dialogue_turns(self, max_turns: int) -> list[dict[str, Any]]:
        """Extract the most recent N user/assistant turns from session.

        Skips tool_calls assistant messages and tool result messages to keep
        the isolated LLM prompt short and focused on dialogue content.
        """
        messages = self._session.messages
        dialogue = []

        for msg in reversed(messages):
            role = msg.get("role", "")
            # Skip tool results and assistant messages that only contain tool_calls
            if role == "tool":
                continue
            if role == "assistant" and msg.get("tool_calls") and not msg.get("content"):
                continue
            if role in ("user", "assistant"):
                dialogue.append({"role": role, "content": msg.get("content", "")})
            if len(dialogue) >= max_turns * 2:
                break

        return list(reversed(dialogue))

    @staticmethod
    def _format_results(results: list[dict[str, Any]]) -> str:
        lines = [f"Found {len(results)} relevant memories:\n"]
        for i, mem in enumerate(results, 1):
            lines.append(
                f"[{i}] Q: {mem['question']}\n"
                f"    A: {mem['conclusion']}\n"
                f"    (key: {mem['composite_key']}, recorded: {mem['created_at'][:10]})"
            )
        return "\n".join(lines)