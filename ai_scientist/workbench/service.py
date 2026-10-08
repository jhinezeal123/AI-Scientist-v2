"""Coordinate clarification and approval for user-directed remote work."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import uuid
from pydantic import ValidationError

from .models import WorkingProposal
from .prompts import planning_prompt
from .store import StoreConflict


class PlanningService:
    def __init__(self, store, bindings, worker, workspace_root: Path, *, view=None):
        self.store, self.bindings, self.worker = store, bindings, worker
        self.workspace_root = workspace_root
        self.view = view
        self.lock = asyncio.Lock()
        self.task = None
        self.closed = False
        self.idle_check = None

    async def start(self, project_id, idea_id, resource_ids):
        async with self.lock:
            if self.closed or (self.task is not None and not self.task.done()):
                raise StoreConflict("An agent job is active; wait before requesting another proposal")
            context = await asyncio.to_thread(self.store.context_snapshot, project_id, idea_id, resource_ids)
            await asyncio.to_thread(self.store.reserve_plan, project_id, idea_id)
            self.task = asyncio.create_task(self._plan(project_id, idea_id, context))
            return {"idea_id": idea_id, "state": "PLANNING"}

    async def create_variant(self, project_id, parent_run_id, request_id, title, purpose, change_summary):
        if self.view is None:
            raise RuntimeError('Run view is required to capture a safe variant baseline')
        baseline, texts = await asyncio.to_thread(self.view.variant_baseline, project_id, parent_run_id)
        return await asyncio.to_thread(self.store.create_variant_idea, project_id, parent_run_id, request_id,
                                       title, purpose, change_summary, baseline, texts)

    async def _plan(self, project_id, idea_id, context):
        try:
            request_id = uuid.uuid4().hex
            workdir = self.store.directory(project_id) / "planning" / request_id
            workdir.mkdir(parents=True, exist_ok=True)
            files = await asyncio.to_thread(self.store.variant_stage_files, context['snapshot'])
            await asyncio.to_thread(self.store.library(project_id).stage, context['snapshot'], workdir, files)
            (workdir / "context.json").write_text(json.dumps(context, ensure_ascii=False, indent=2), encoding="utf-8")
            request = self.bindings.request_type(request_id, "mvp0_plan", planning_prompt(context), workdir,
                                                 timeout_seconds=300, max_output_bytes=300_000)
            if os.name == 'nt' and len(subprocess.list2cmdline([request.prompt]).encode('utf-16-le')) // 2 > 29_000:
                raise ValueError("Selected context is too large for the Windows CLI argument limit")
            _, payload = await self.worker.run(request)
            body = payload.model_dump(exclude_none=True)
            if not payload.needs_clarification:
                ready = WorkingProposal.model_validate(body)
                allowed = {source["id"] for source in context["snapshot"]["resources"]}
                if any(ref not in allowed for ref in ready.data_refs):
                    raise ValueError("Planner cited a source outside the selected context")
                body = ready.model_dump(exclude_none=True)
            await asyncio.to_thread(self.store.save_proposal, project_id, idea_id, body, context)
        except asyncio.CancelledError:
            await asyncio.to_thread(self.store.plan_failed, project_id, idea_id, "Lập proposal bị gián đoạn. Trao đổi đã lưu vẫn còn; bấm tiếp tục để yêu cầu lượt mới.")
            raise
        except Exception as exc:
            # No unvalidated model output, prompts or stderr in an error shown to the user.
            error = "Nguồn/idea đã thay đổi; tạo proposal lại." if isinstance(exc, StoreConflict) else (
                f"Lập proposal thất bại ({type(exc).__name__}). Kiểm tra nguồn và thử lại rõ ràng; không tự retry.")
            if isinstance(exc, ValueError) and 'Windows CLI argument limit' in str(exc):
                error = "Context quá dài cho Codex CLI trên Windows. Chọn ít nguồn hơn hoặc rút gọn nội dung rồi thử lại."
            elif isinstance(exc, ValidationError):
                fields = [".".join(str(part) for part in item['loc']) or '$' for item in exc.errors(include_input=False)[:5]]
                error = "Codex trả payload không đúng schema tại: " + ", ".join(fields) + ". Chưa lưu proposal; thử lại rõ ràng."
            await asyncio.to_thread(self.store.plan_failed, project_id, idea_id, error)

    async def answer(self, project_id, idea_id, proposal_id, version, text):
        async with self.lock:
            return await asyncio.to_thread(self.store.answer, project_id, idea_id, proposal_id, version, text)

    async def approve(self, project_id, proposal_id, version, context_sha256):
        async with self.lock:
            proposals = await asyncio.to_thread(self.store.proposals, project_id)
            proposal = next((item for item in proposals if item['id'] == proposal_id), None)
            if proposal is None:
                raise KeyError('Proposal not found in this project')
            if proposal['version'] != version or proposal['context_sha256'] != context_sha256:
                raise StoreConflict('Approval version/hash is stale')
            if proposal['state'] == 'STALE':
                raise StoreConflict('Proposal cần xem lại. Kiểm tra idea/nguồn hiện hành và lập proposal mới trước khi duyệt.')
            # Serialize across all project DBs in this single-process app.
            unknown_ids = []
            for project in await asyncio.to_thread(self.store.list_projects):
                history = await asyncio.to_thread(self.store.history, project["id"])
                # An idempotent repeat approval returns its existing run.
                candidates = [run for run in history['runs'] if not (project['id'] == project_id and run['proposal_id'] == proposal_id)]
                unknown_ids.extend(run['id'] for run in candidates if run['state'] == 'UNKNOWN')
                allowed = {'COMPLETED','FAILED','CANCELLED','REMOTE_SUCCEEDED','REMOTE_FAILED','COLLECTING'}
                if self.idle_check is not None:
                    allowed.add('UNKNOWN')
                unstarted = await asyncio.to_thread(self.store.unstarted_run_ids, project['id'])
                blocking = next((run for run in candidates if run['state'] not in allowed and run['id'] not in unstarted), None)
                if blocking:
                    raise StoreConflict(f"Run {blocking['id'][:8]} ({blocking['state']}) của project {project['name']} đang chặn lượt mới.")
            if unknown_ids:
                evidence = await self.idle_check()
                # Record the read permitting this new approval; old runs stay unchanged.
                directory = self.store.directory(project_id) / 'approval-idle-checks'
                directory.mkdir(parents=True,exist_ok=True)
                destination = directory/(proposal['id']+'.json')
                if directory.is_symlink() or destination.is_symlink():
                    raise StoreConflict('Linked approval evidence path refused')
                destination.write_text(json.dumps({**evidence,'unknown_run_ids':unknown_ids},indent=2),encoding='utf-8')
            return await asyncio.to_thread(self.store.approve_proposal, project_id, proposal_id, version, context_sha256, tuple(unknown_ids))

    async def implementation_context(self, project_id, run_id):
        return await asyncio.to_thread(self.store.approved_context, project_id, run_id)

    async def close(self):
        self.closed = True
        if self.task is not None and not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
