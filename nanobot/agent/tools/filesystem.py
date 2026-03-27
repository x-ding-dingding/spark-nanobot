"""File system tools: read, write, edit."""

from pathlib import Path
from typing import Any

from nanobot.agent.tools.base import Tool


"""File system tools: read, write, edit."""

from pathlib import Path
from typing import Any

from nanobot.agent.tools.base import Tool

def _resolve_path(
    path: str,
    allowed_dirs: list[Path] | None = None,
    protected_paths: list[Path] | None = None,
) -> Path:
    """Resolve path and optionally enforce directory and protection restrictions.

    Args:
        path: The raw path string to resolve.
        allowed_dirs: If provided, the resolved path must fall under at
            least one of these directories.
        protected_paths: If provided, the resolved path must not match any
            of these absolute file paths (used to prevent writes to security-
            critical files within the nanobot project).
    """
    resolved = Path(path).expanduser().resolve()
    if allowed_dirs:
        resolved_str = str(resolved)
        if not any(resolved_str.startswith(str(d.resolve())) for d in allowed_dirs):
            dirs_display = ", ".join(str(d) for d in allowed_dirs)
            raise PermissionError(f"Path {path} is outside allowed directories: [{dirs_display}]")
    if protected_paths:
        for protected in protected_paths:
            if resolved == protected:
                raise PermissionError(
                    f"Access denied: {path} is a protected security file and cannot be modified"
                )
    return resolved

# File extensions that are known to be very large or not useful to read in full
_BLOCKED_EXTENSIONS: set[str] = {
    ".lock", ".lockb",          # lock files (package-lock.json handled by name)
    ".min.js", ".min.css",      # minified bundles
    ".map",                     # source maps
    ".wasm",                    # WebAssembly
    ".pyc", ".pyo",             # compiled Python
    ".so", ".dylib", ".dll",    # native libraries
    ".exe", ".bin",             # binaries
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",  # archives
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".svg",  # images
    ".mp3", ".mp4", ".wav", ".avi", ".mov", ".mkv",  # media
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",  # documents
    ".sqlite", ".db",          # databases
}

_BLOCKED_FILENAMES: set[str] = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "composer.lock",
    "Cargo.lock",
    "Gemfile.lock",
    "poetry.lock",
    "Pipfile.lock",
}

# Default limits
_DEFAULT_MAX_LINES = 2000
_MAX_RESULT_CHARS = 120_000  # ~30K tokens


class ReadFileTool(Tool):
    """Tool to read file contents with output protection."""

    def __init__(self, allowed_dirs: list[Path] | None = None):
        self._allowed_dirs = allowed_dirs

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return (
            "Read the contents of a file. By default reads up to 2000 lines. "
            "Use offset and limit to paginate through large files. "
            "Known large/binary file types are blocked."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The file path to read",
                },
                "offset": {
                    "type": "integer",
                    "description": "Starting line number (0-based). Defaults to 0.",
                    "default": 0,
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of lines to return. Defaults to 2000.",
                    "default": _DEFAULT_MAX_LINES,
                },
            },
            "required": ["path"],
        }

    async def execute(
        self,
        path: str,
        offset: int = 0,
        limit: int = _DEFAULT_MAX_LINES,
        **kwargs: Any,
    ) -> str:
        try:
            file_path = _resolve_path(path, self._allowed_dirs)
            if not file_path.exists():
                return f"Error: File not found: {path}"
            if not file_path.is_file():
                return f"Error: Not a file: {path}"

            # Block known large / binary file types
            if file_path.name in _BLOCKED_FILENAMES:
                size = file_path.stat().st_size
                return (
                    f"Blocked: {file_path.name} is a lock/generated file "
                    f"({size:,} bytes). Use exec with grep/head/tail to inspect it."
                )

            suffix = file_path.suffix.lower()
            # Handle compound extensions like .min.js
            if suffix == ".js" and file_path.stem.endswith(".min"):
                suffix = ".min.js"
            elif suffix == ".css" and file_path.stem.endswith(".min"):
                suffix = ".min.css"

            if suffix in _BLOCKED_EXTENSIONS:
                size = file_path.stat().st_size
                return (
                    f"Blocked: {file_path.name} appears to be a binary or "
                    f"generated file ({size:,} bytes). "
                    f"Use exec with appropriate commands to inspect it."
                )

            # Read the file
            content = file_path.read_text(encoding="utf-8")
            lines = content.splitlines(keepends=True)
            total_lines = len(lines)

            # Clamp offset
            if offset < 0:
                offset = 0
            if offset >= total_lines:
                return (
                    f"File {path} has {total_lines} lines. "
                    f"Offset {offset} is beyond the end of the file."
                )

            # Clamp limit
            if limit <= 0:
                limit = _DEFAULT_MAX_LINES

            end = min(offset + limit, total_lines)
            selected = lines[offset:end]
            result = "".join(selected)

            # Hard cap on character count (~30K tokens)
            truncated_by_chars = False
            if len(result) > _MAX_RESULT_CHARS:
                result = result[:_MAX_RESULT_CHARS]
                truncated_by_chars = True

            # Build footer with pagination info
            shown_lines = end - offset
            remaining = total_lines - end
            footer_parts: list[str] = []

            if remaining > 0 or truncated_by_chars:
                if truncated_by_chars:
                    footer_parts.append(
                        f"[Content truncated at {_MAX_RESULT_CHARS:,} chars for context safety]"
                    )
                footer_parts.append(
                    f"[Showing lines {offset + 1}-{end} of {total_lines} total]"
                )
                if remaining > 0:
                    footer_parts.append(
                        f"[Use offset={end} to view the next {min(remaining, limit)} lines]"
                    )

            if footer_parts:
                result = result.rstrip("\n") + "\n\n" + "\n".join(footer_parts)

            return result
        except PermissionError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error reading file: {str(e)}"

class WriteFileTool(Tool):
    """Tool to write content to a file."""
    
    def __init__(self, allowed_dirs: list[Path] | None = None, protected_paths: list[Path] | None = None):
        self._allowed_dirs = allowed_dirs
        self._protected_paths = protected_paths

    @property
    def name(self) -> str:
        return "write_file"
    
    @property
    def description(self) -> str:
        return "Write content to a file at the given path. Creates parent directories if needed. Supports append mode to add content to the end of existing files."
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The file path to write to"
                },
                "content": {
                    "type": "string",
                    "description": "The content to write"
                },
                "append": {
                    "type": "boolean",
                    "description": "If true, append content to the end of the file instead of overwriting. Defaults to false.",
                    "default": False
                }
            },
            "required": ["path", "content"]
        }
    
    async def execute(self, path: str, content: str, append: bool = False, **kwargs: Any) -> str:
        try:
            file_path = _resolve_path(path, self._allowed_dirs, self._protected_paths)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            if append:
                # Append mode: read existing content and append new content
                existing_content = ""
                if file_path.exists():
                    existing_content = file_path.read_text(encoding="utf-8")
                file_path.write_text(existing_content + content, encoding="utf-8")
                return f"Successfully appended {len(content)} bytes to {path}"
            else:
                # Overwrite mode (default)
                file_path.write_text(content, encoding="utf-8")
                return f"Successfully wrote {len(content)} bytes to {path}"
        except PermissionError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error writing file: {str(e)}"

class EditFileTool(Tool):
    """Tool to edit a file by replacing text."""
    
    def __init__(self, allowed_dirs: list[Path] | None = None, protected_paths: list[Path] | None = None):
        self._allowed_dirs = allowed_dirs
        self._protected_paths = protected_paths

    @property
    def name(self) -> str:
        return "edit_file"
    
    @property
    def description(self) -> str:
        return "Edit a file by replacing old_text with new_text. The old_text must exist exactly in the file."
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The file path to edit"
                },
                "old_text": {
                    "type": "string",
                    "description": "The exact text to find and replace"
                },
                "new_text": {
                    "type": "string",
                    "description": "The text to replace with"
                }
            },
            "required": ["path", "old_text", "new_text"]
        }
    
    async def execute(self, path: str, old_text: str, new_text: str, **kwargs: Any) -> str:
        try:
            file_path = _resolve_path(path, self._allowed_dirs, self._protected_paths)
            if not file_path.exists():
                return f"Error: File not found: {path}"
            
            content = file_path.read_text(encoding="utf-8")
            
            if old_text not in content:
                return f"Error: old_text not found in file. Make sure it matches exactly."
            
            # Count occurrences
            count = content.count(old_text)
            if count > 1:
                return f"Warning: old_text appears {count} times. Please provide more context to make it unique."
            
            new_content = content.replace(old_text, new_text, 1)
            file_path.write_text(new_content, encoding="utf-8")
            
            return f"Successfully edited {path}"
        except PermissionError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error editing file: {str(e)}"


_DEFAULT_LIST_LIMIT = 200


class ListDirTool(Tool):
    """Tool to list directory contents with a result limit."""

    def __init__(self, allowed_dirs: list[Path] | None = None):
        self._allowed_dirs = allowed_dirs

    @property
    def name(self) -> str:
        return "list_dir"

    @property
    def description(self) -> str:
        return (
            "List the contents of a directory. "
            "Returns up to 200 entries by default. "
            "Use limit to control the number of results."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The directory path to list",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of entries to return. Defaults to 200.",
                    "default": _DEFAULT_LIST_LIMIT,
                },
            },
            "required": ["path"],
        }

    async def execute(self, path: str, limit: int = _DEFAULT_LIST_LIMIT, **kwargs: Any) -> str:
        try:
            dir_path = _resolve_path(path, self._allowed_dirs)
            if not dir_path.exists():
                return f"Error: Directory not found: {path}"
            if not dir_path.is_dir():
                return f"Error: Not a directory: {path}"

            if limit <= 0:
                limit = _DEFAULT_LIST_LIMIT

            all_items = sorted(dir_path.iterdir())
            total = len(all_items)

            if total == 0:
                return f"Directory {path} is empty"

            shown = all_items[:limit]
            lines: list[str] = []
            for item in shown:
                prefix = "📁 " if item.is_dir() else "📄 "
                lines.append(f"{prefix}{item.name}")

            if total > limit:
                lines.append(
                    f"\n[Showing {limit} of {total} entries. "
                    f"Use exec with ls/find for the full listing.]"
                )

            return "\n".join(lines)
        except PermissionError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error listing directory: {str(e)}"
