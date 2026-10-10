"""Isolated Git worktrees and validated file transactions, never the user's checkout."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import threading

from .models import PermissionPolicy, TaskResult

_DENIED = {".git", ".workbench", ".env", "profiles", "credentials.json", "kaggle.json",
           "cookies.json", "secrets", "node_modules", ".venv", "AGENTS.md"}


def safe_path(root: Path, value: str, *, allow_missing=True) -> Path:
    relative = PurePosixPath(value)
    if not value or "\\" in value or ":" in value or "\x00" in value or relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Path must stay inside the seat workspace")
    if any(p in _DENIED or p.startswith(".") for p in relative.parts):
        raise ValueError("Hidden, secret and runtime paths are outside the agent scope")
    target = root.joinpath(*relative.parts)
    root = root.resolve(strict=True)
    cursor = target
    while cursor != root:
        if cursor.is_symlink() or (cursor.exists() and getattr(cursor, "is_junction", lambda: False)()):
            raise ValueError("Symlink/junction paths are outside the agent scope")
        if cursor.parent == cursor:
            raise ValueError("Invalid workspace root")
        cursor = cursor.parent
    if not target.resolve().is_relative_to(root):
        raise ValueError("Path escapes the seat workspace")
    if not allow_missing and not target.is_file():
        raise ValueError("Workspace file not found")
    return target


class Workspaces:
    def __init__(self, repository: Path):
        self.repository = repository.resolve()
        self.root = self.repository / ".workbench" / "agents" / "worktrees"
        self._lock = threading.RLock()

    def git(self, directory: Path, *args, timeout=30) -> str:
        command = ["git", "-c", "core.hooksPath=" + str(self.repository / ".workbench" / "agents" / "no-hooks"),
                   "-c", "core.autocrlf=false", "-c", "core.quotePath=false", "-C", str(directory), *args]
        result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=timeout, text=True, encoding="utf-8", errors="replace",
                                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        if result.returncode:
            raise ValueError("Git operation failed: " + result.stderr.strip()[:1000])
        if len(result.stdout.encode("utf-8")) > 2_000_000:
            raise ValueError("Git result exceeds the display limit")
        return result.stdout.rstrip("\r\n")

    def revision(self, reference: str) -> str:
        if reference.startswith("-") or any(c in reference for c in "\x00\r\n"):
            raise ValueError("Invalid Git reference")
        return self.git(self.repository, "rev-parse", "--verify", reference + "^{commit}")

    def path(self, rig_id, seat_id):
        from .spec import _id
        _id(rig_id, "rig ID")
        _id(seat_id, "seat ID")
        target = self.root / rig_id / seat_id
        cursor = target
        while cursor != self.repository:
            if cursor.is_symlink() or (cursor.exists() and getattr(cursor, "is_junction", lambda: False)()):
                raise ValueError("Refusing redirected worktree storage")
            cursor = cursor.parent
        return target

    def ensure(self, rig_id, seat_id, base_ref):
        with self._lock:
            target = self.path(rig_id, seat_id)
            if target.exists():
                if not (target / ".git").is_file():
                    raise ValueError("Seat workspace is not a managed worktree")
                common = Path(self.git(target, "rev-parse", "--path-format=absolute", "--git-common-dir")).resolve()
                expected = Path(self.git(self.repository, "rev-parse", "--path-format=absolute", "--git-common-dir")).resolve()
                if common != expected:
                    raise ValueError("Workspace belongs to a different repository")
            else:
                revision = self.revision(base_ref)
                target.parent.mkdir(parents=True, exist_ok=True)
                self.git(self.repository, "worktree", "add", "--detach", str(target), revision)
            return target, self.git(target, "rev-parse", "HEAD")

    def discover(self):
        records = self.git(self.repository, "worktree", "list", "--porcelain").split("\n\n")
        result = []
        for record in records:
            fields = [line.partition(" ") for line in record.splitlines()]
            data = {key: value for key, _, value in fields}
            if "worktree" in data:
                candidate = Path(data["worktree"]).resolve()
                if candidate.is_relative_to(self.root.resolve()):
                    result.append({"path": str(candidate), "checkpoint": data.get("HEAD"),
                                   "rig_id": candidate.parent.name, "seat_id": candidate.name})
        return result

    def files(self, path):
        names = self.git(path, "ls-files", "-z").split("\x00")
        result = []
        for name in names:
            if not name:
                continue
            try:
                candidate = safe_path(path, name, allow_missing=False)
                if candidate.stat().st_size <= 1_000_000:
                    result.append({"path": name, "bytes": candidate.stat().st_size})
            except ValueError:
                continue
            if len(result) >= 1000:
                break
        return result

    def read(self, path, name):
        file = safe_path(path, name, allow_missing=False)
        if file.stat().st_size > 1_000_000:
            raise ValueError("File is too large for the editor")
        body = file.read_text(encoding="utf-8")
        return {"path": name, "content": body, "sha256": hashlib.sha256(body.encode()).hexdigest()}

    def apply(self, path, result: TaskResult, policy: PermissionPolicy):
        if not result.files:
            return
        if not policy.file_edits or len(result.files) > policy.max_files:
            raise ValueError("Seat policy does not authorize these file edits")
        prepared = []
        seen = set()
        for edit in result.files:
            if edit.path in seen:
                raise ValueError("Duplicate file edit")
            seen.add(edit.path)
            file = safe_path(path, edit.path)
            if not any(edit.path == prefix.rstrip("/") or edit.path.startswith(prefix.rstrip("/") + "/") for prefix in policy.allowed_paths):
                raise ValueError("File edit is outside the seat's allowed paths")
            if len(edit.content.encode("utf-8")) > policy.max_file_bytes or (file.exists() and not file.is_file()):
                raise ValueError("Invalid file edit size or destination")
            prepared.append((file, edit.content, file.read_bytes() if file.exists() else None))
        try:
            for file, content, _ in prepared:
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text(content, encoding="utf-8", newline="\n")
        except BaseException:
            for file, _, before in prepared:
                if before is None:
                    file.unlink(missing_ok=True)
                else:
                    file.write_bytes(before)
            raise

    def edit(self, path, name, content, expected_sha256, policy):
        current = self.read(path, name)["sha256"] if safe_path(path, name).exists() else None
        if current != expected_sha256:
            raise ValueError("File changed; refresh the editor before saving")
        self.apply(path, TaskResult(summary="Manual edit", files=[{"path": name, "content": content}]), policy)

    def checkpoint(self, path, *, task_id):
        # Only scoped file edits enter the index. No broad `git add .` of runtime resources.
        changed = self.git(path, "status", "--porcelain", "--untracked-files=all").splitlines()
        names = []
        for row in changed:
            name = row[3:]
            if " -> " in name:
                raise ValueError("Renames need manual review before checkpointing")
            safe_path(path, name)
            names.append(name)
        if names:
            self.git(path, "add", "--", *names)
            self.git(path, "-c", "user.name=AI Scientist", "-c", "user.email=agents@localhost",
                     "commit", "-m", "Agent checkpoint " + task_id)
        return self.git(path, "rev-parse", "HEAD")

    def review(self, path, base_ref):
        base = self.revision(base_ref)
        return {"head": self.git(path, "rev-parse", "HEAD"), "base": base,
                "status": self.git(path, "status", "--porcelain"),
                "diff": self.git(path, "diff", "--no-ext-diff", "--no-textconv", base, "--"),
                "log": self.git(path, "log", "-10", "--oneline")}

    def restore_checkpoint(self, path, revision):
        revision = self.revision(revision)
        if self.git(path, "status", "--porcelain"):
            raise ValueError("Checkpoint restore requires a clean seat worktree")
        self.git(path, "checkout", "--detach", revision)
        return revision

    def remove(self, rig_id, seat_id):
        path = self.path(rig_id, seat_id)
        if path.exists():
            if self.git(path, "status", "--porcelain"):
                raise ValueError("Save a checkpoint before removing a worktree")
            self.git(self.repository, "worktree", "remove", str(path))
