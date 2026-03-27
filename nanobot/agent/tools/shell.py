"""Shell execution tool."""

import asyncio
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from nanobot.agent.tools.base import Tool

# Output limits
_MAX_OUTPUT_CHARS = 10_000
_HEAD_CHARS = 5_000
_TAIL_CHARS = 3_000
# Threshold above which output is offloaded to a temp file instead of truncated
_OFFLOAD_THRESHOLD = 50_000


class ExecTool(Tool):
    """Tool to execute shell commands."""
    
    def __init__(
        self,
        timeout: int = 60,
        working_dir: str | None = None,
        deny_patterns: list[str] | None = None,
        allow_patterns: list[str] | None = None,
        restrict_to_workspace: bool = False,
        allowed_dirs: list[Path] | None = None,
        protected_paths: list[Path] | None = None,
    ):
        self.timeout = timeout
        self.working_dir = working_dir
        self.deny_patterns = deny_patterns or [
            r"\brm\s+-[rf]{1,2}\b",          # rm -r, rm -rf, rm -fr
            r"\bdel\s+/[fq]\b",              # del /f, del /q
            r"\brmdir\s+/s\b",               # rmdir /s
            r"\b(format|mkfs|diskpart)\b",   # disk operations
            r"\bdd\s+if=",                   # dd
            r">\s*/dev/sd",                  # write to disk
            r"\b(shutdown|reboot|poweroff)\b",  # system power
            r":\(\)\s*\{.*\};\s*:",          # fork bomb
        ]
        self.allow_patterns = allow_patterns or []
        self.restrict_to_workspace = restrict_to_workspace
        self.allowed_dirs = allowed_dirs or []
        self.protected_paths = [p.resolve() for p in (protected_paths or [])]
    
    @property
    def name(self) -> str:
        return "exec"
    
    @property
    def description(self) -> str:
        return "Execute a shell command and return its output. Use with caution."
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute"
                },
                "working_dir": {
                    "type": "string",
                    "description": "Optional working directory for the command"
                }
            },
            "required": ["command"]
        }
    
    async def execute(self, command: str, working_dir: str | None = None, **kwargs: Any) -> str:
        cwd = working_dir or self.working_dir or os.getcwd()
        guard_error = self._guard_command(command, cwd)
        if guard_error:
            return guard_error
        
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                return f"Error: Command timed out after {self.timeout} seconds"
            
            output_parts = []
            
            if stdout:
                output_parts.append(stdout.decode("utf-8", errors="replace"))
            
            if stderr:
                stderr_text = stderr.decode("utf-8", errors="replace")
                if stderr_text.strip():
                    output_parts.append(f"STDERR:\n{stderr_text}")
            
            if process.returncode != 0:
                output_parts.append(f"\nExit code: {process.returncode}")
            
            result = "\n".join(output_parts) if output_parts else "(no output)"

            # Handle very long output
            if len(result) > _OFFLOAD_THRESHOLD:
                # Offload to temp file and return a summary reference
                result = self._offload_to_file(result, command)
            elif len(result) > _MAX_OUTPUT_CHARS:
                # Head + tail truncation (preserves errors that usually appear at the end)
                result = self._truncate_head_tail(result)

            return result
            
        except Exception as e:
            return f"Error executing command: {str(e)}"

    @staticmethod
    def _truncate_head_tail(result: str) -> str:
        """Truncate output keeping both head and tail for context."""
        total = len(result)
        head = result[:_HEAD_CHARS]
        tail = result[-_TAIL_CHARS:]
        omitted = total - _HEAD_CHARS - _TAIL_CHARS
        return (
            f"{head}\n\n"
            f"... [{omitted:,} chars omitted] ...\n\n"
            f"{tail}\n\n"
            f"[Output truncated: {total:,} chars total. "
            f"Use head/tail/grep for more precise inspection.]"
        )

    @staticmethod
    def _offload_to_file(result: str, command: str) -> str:
        """Write large output to a temp file and return a summary reference."""
        total_lines = result.count("\n") + 1
        suffix = ".txt"
        tmp = tempfile.NamedTemporaryFile(
            mode="w",
            suffix=suffix,
            prefix="nanobot-exec-",
            delete=False,
            encoding="utf-8",
        )
        tmp.write(result)
        tmp.close()

        # Build a short preview: first 5 lines + last 5 lines
        lines = result.splitlines()
        preview_parts: list[str] = []
        if len(lines) <= 10:
            preview_parts.append("\n".join(lines))
        else:
            preview_parts.append("\n".join(lines[:5]))
            preview_parts.append("...")
            preview_parts.append("\n".join(lines[-5:]))
        preview = "\n".join(preview_parts)

        return (
            f"Output too large for context ({len(result):,} chars, {total_lines:,} lines).\n"
            f"Full output saved to: {tmp.name}\n\n"
            f"Preview (first/last 5 lines):\n{preview}\n\n"
            f"[Use read_file to inspect the full output, or exec with "
            f"head/tail/grep for targeted inspection.]"
        )

    def _guard_command(self, command: str, cwd: str) -> str | None:
        """Best-effort safety guard for potentially destructive commands."""
        cmd = command.strip()
        lower = cmd.lower()

        for pattern in self.deny_patterns:
            if re.search(pattern, lower):
                return "Error: Command blocked by safety guard (dangerous pattern detected)"

        if self.allow_patterns:
            if not any(re.search(p, lower) for p in self.allow_patterns):
                return "Error: Command blocked by safety guard (not in allowlist)"

        if self.restrict_to_workspace:
            if "..\\" in cmd or "../" in cmd:
                return "Error: Command blocked by safety guard (path traversal detected)"

            cwd_path = Path(cwd).resolve()
            check_dirs = [cwd_path] + [d.resolve() for d in self.allowed_dirs]

            win_paths = re.findall(r"[A-Za-z]:\\[^\\\"']+", cmd)
            # Only match absolute paths — avoid false positives on relative
            # paths like ".venv/bin/python" where "/bin/python" would be
            # incorrectly extracted by the old pattern.
            posix_paths = re.findall(r"(?:^|[\s|>])(/[^\s\"'>]+)", cmd)

            for raw in win_paths + posix_paths:
                try:
                    p = Path(raw.strip()).resolve()
                except Exception:
                    continue
                if p.is_absolute():
                    path_str = str(p)
                    if not any(path_str.startswith(str(d)) for d in check_dirs):
                        return "Error: Command blocked by safety guard (path outside allowed directories)"

        # Check protected files: block write/delete/move operations targeting them
        if self.protected_paths:
            protected_error = self._guard_protected_files(cmd, cwd)
            if protected_error:
                return protected_error

        return None

    def _guard_protected_files(self, command: str, cwd: str) -> str | None:
        """Block shell commands that would modify or delete protected files."""
        protected_strs = [str(p) for p in self.protected_paths]

        # Check if any protected file path appears in the command
        for protected_path in protected_strs:
            if protected_path not in command:
                continue

            # Patterns that indicate destructive/write operations on a file
            write_patterns = [
                rf"rm\s+.*{re.escape(protected_path)}",
                rf"mv\s+.*{re.escape(protected_path)}",
                rf"cp\s+.*\s+{re.escape(protected_path)}",
                rf">\s*{re.escape(protected_path)}",
                rf">>\s*{re.escape(protected_path)}",
                rf"tee\s+.*{re.escape(protected_path)}",
                rf"sed\s+-i.*{re.escape(protected_path)}",
                rf"chmod\s+.*{re.escape(protected_path)}",
                rf"chown\s+.*{re.escape(protected_path)}",
                rf"truncate\s+.*{re.escape(protected_path)}",
                rf"perl\s+-[pi].*{re.escape(protected_path)}",
            ]
            for pattern in write_patterns:
                if re.search(pattern, command):
                    return (
                        f"Error: Command blocked by safety guard "
                        f"(targets protected file: {protected_path})"
                    )

        # Also check relative paths resolved against cwd
        cwd_path = Path(cwd).resolve()
        for protected in self.protected_paths:
            try:
                relative = protected.relative_to(cwd_path)
                rel_str = str(relative)
            except ValueError:
                continue

            if rel_str not in command:
                continue

            write_patterns = [
                rf"rm\s+.*{re.escape(rel_str)}",
                rf"mv\s+.*{re.escape(rel_str)}",
                rf"cp\s+.*\s+{re.escape(rel_str)}",
                rf">\s*{re.escape(rel_str)}",
                rf">>\s*{re.escape(rel_str)}",
                rf"tee\s+.*{re.escape(rel_str)}",
                rf"sed\s+-i.*{re.escape(rel_str)}",
                rf"chmod\s+.*{re.escape(rel_str)}",
                rf"chown\s+.*{re.escape(rel_str)}",
                rf"truncate\s+.*{re.escape(rel_str)}",
                rf"perl\s+-[pi].*{re.escape(rel_str)}",
            ]
            for pattern in write_patterns:
                if re.search(pattern, command):
                    return (
                        f"Error: Command blocked by safety guard "
                        f"(targets protected file: {rel_str})"
                    )

        return None
