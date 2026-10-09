"""Library, approval and remote Working endpoints."""
from typing import Literal
import asyncio
import json
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import Field, field_validator

from .models import StrictModel
from .modes import RunMode
from .log_window import read_log_window
from .resources import readiness_sources
from .store import StoreConflict


class ProjectInput(StrictModel):
    name: str = Field(min_length=1, max_length=120)


class ResourceInput(StrictModel):
    kind: Literal["text", "url", "dataset"] | None = None
    title: str = Field(min_length=1, max_length=240)
    url: str | None = Field(default=None, max_length=2000)
    content: str = Field(default="", max_length=60_000)

    @field_validator("url")
    @classmethod
    def valid_url(cls, value):
        if value:
            from urllib.parse import urlsplit
            parsed = urlsplit(value)
            if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError("Source URL must be HTTP(S) without credentials")
        return value


class ResourceUpdate(ResourceInput):
    expected_version: int = Field(ge=1)


class IdeaInput(StrictModel):
    text: str = Field(min_length=1, max_length=20_000)
    title: str | None = Field(default=None, min_length=1, max_length=80)
    mode: RunMode = 'training_research'
    desired_output: str = Field(default='', max_length=20_000)


class ContextInput(StrictModel):
    idea_id: str
    resource_ids: list[str] = Field(default_factory=list, max_length=30)


class IdeaUpdate(IdeaInput):
    mode: RunMode | None = None
    desired_output: str | None = Field(default=None, max_length=20_000)
    expected_text: str = Field(max_length=20_000)
    expected_title: str | None = Field(default=None, max_length=80)
    expected_mode: RunMode | None = None
    expected_desired_output: str | None = Field(default=None, max_length=20_000)


class IdeaTitleUpdate(StrictModel):
    title: str = Field(min_length=1, max_length=80)
    expected_title: str = Field(max_length=80)


class AnswerInput(StrictModel):
    proposal_id: str
    version: int = Field(ge=1)
    text: str = Field(min_length=1, max_length=20_000)


class ApprovalInput(StrictModel):
    version: int = Field(ge=1)
    context_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class RetryInput(StrictModel):
    request_id: str = Field(pattern=r'^[0-9a-f]{32}$')


class OutputCopyInput(StrictModel):
    kind: Literal['file', 'text']
    title: str = Field(min_length=1, max_length=240)
    sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    path: str | None = Field(default=None, min_length=1, max_length=2000)


class VariantInput(StrictModel):
    request_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    title: str = Field(min_length=1, max_length=80)
    purpose: str = Field(min_length=1, max_length=20_000)
    change_summary: str = Field(min_length=1, max_length=20_000)
    mode: RunMode | None = None
    desired_output: str | None = Field(default=None, max_length=20_000)


class WorkingInput(StrictModel):
    accelerator: Literal['cpu', 'NvidiaT4', 'TpuV5E8', 'TpuV6E8'] = 'cpu'
    ttl_seconds: int = Field(default=1800, ge=60, le=43200)
    search: dict | None = None


def library_router(store, workspace_root):
    router = APIRouter(prefix="/api")

    def call(operation, *args, **kwargs):
        try:
            return operation(*args, **kwargs)
        except KeyError as exc:
            raise HTTPException(404, str(exc.args[0])) from exc
        except StoreConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(422, str(exc)) from exc

    async def async_call(operation, *args):
        try:
            return await operation(*args)
        except KeyError as exc:
            raise HTTPException(404, str(exc.args[0])) from exc
        except StoreConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except (RuntimeError, TimeoutError) as exc:
            raise HTTPException(503, 'MCP readiness unavailable; no new push authorized') from exc

    @router.get("/projects")
    def projects():
        return call(store.list_projects)

    @router.post("/projects", status_code=201)
    def create_project(body: ProjectInput):
        if not body.name.strip():
            raise HTTPException(422, "Project name must contain text")
        return call(store.create_project, body.name)

    @router.delete('/projects/{project_id}')
    async def delete_project(project_id: str, body: ProjectInput, request: Request):
        service = getattr(request.app.state, 'service', None)
        if service:
            async with service.lock:
                if (service.worker.future is not None and not service.worker.future.done()
                        or service.worker.state.get('status') == 'unknown'
                        or service.task is not None and not service.task.done()):
                    raise HTTPException(409, 'Chờ agent kết thúc và xác nhận trạng thái trước khi xóa project')
                working = getattr(request.app.state, 'working', None)
                if working and any(key[0] == project_id and not task.done() for key, task in working.tasks.items()):
                    raise HTTPException(409, 'Working của project chưa kết thúc; chờ xác nhận Kaggle dừng trước khi xóa')
                return await asyncio.to_thread(call, store.delete_project, project_id, body.name)
        return await asyncio.to_thread(call, store.delete_project, project_id, body.name)

    @router.get("/projects/{project_id}/resources")
    def resources(project_id: str):
        return call(store.resources, project_id)

    @router.post("/projects/{project_id}/resources", status_code=201)
    def add_resource(project_id: str, body: ResourceInput):
        return call(store.save_resource, project_id, body.model_dump())

    @router.put("/projects/{project_id}/resources/{resource_id}")
    def update_resource(project_id: str, resource_id: str, body: ResourceUpdate):
        return call(store.save_resource, project_id, body.model_dump(exclude={"expected_version"}),
                    resource_id, body.expected_version)

    async def receive_file(project_id, file, title, resource_id=None, expected_version=None):
        from .ingestion import MAX_FILE_BYTES
        call(store.project, project_id)
        data = bytearray()
        try:
            while chunk := await file.read(64_000):
                data.extend(chunk)
                if len(data) > MAX_FILE_BYTES:
                    raise HTTPException(413, 'File vượt quá 25 MB; dùng dataset reference cho dữ liệu lớn')
        finally:
            await file.close()
        return await asyncio.to_thread(call, store.import_file, project_id, title, file.filename or 'document',
                                       bytes(data), resource_id, expected_version)

    @router.post('/projects/{project_id}/resources/import', status_code=201)
    async def import_file(project_id: str, file: UploadFile = File(...), title: str = Form('', max_length=240)):
        return await receive_file(project_id, file, title)

    @router.put('/projects/{project_id}/resources/{resource_id}/import')
    async def replace_file(project_id: str, resource_id: str, file: UploadFile = File(...),
                           title: str = Form('', max_length=240), expected_version: int = Form(..., ge=1)):
        return await receive_file(project_id, file, title, resource_id, expected_version)

    @router.post("/projects/{project_id}/import-readiness")
    def import_readiness(project_id: str):
        call(store.project, project_id)
        sources = call(readiness_sources, workspace_root)
        existing = call(store.resources, project_id)
        imported = []
        for source in sources:
            # Repeated click is idempotent for an unchanged imported source.
            match = next((item for item in existing if all(item[key] == source[key]
                         for key in ("kind", "title", "url", "content"))), None)
            imported.append(match or call(store.save_resource, project_id, source))
        return imported

    @router.get("/projects/{project_id}/ideas")
    def ideas(project_id: str, include_deleted: bool = False):
        return call(store.ideas, project_id, include_deleted=include_deleted)

    @router.get('/projects/{project_id}/library/{resource_id}/versions/{version}')
    def source_file(project_id: str, resource_id: str, version: int):
        from fastapi.responses import PlainTextResponse
        call(store.project, project_id)
        if not call(store.source_available, project_id, resource_id):
            raise HTTPException(404, 'Source was deleted or is being deleted')
        path = call(store.library(project_id).source_path, resource_id, version)
        if not path.is_file():
            raise HTTPException(404, 'Source version not found')
        return PlainTextResponse(path.read_text(encoding='utf-8'))

    def imported_path(project_id, resource_id, version, kind, page=None):
        call(store.project, project_id)
        if not call(store.source_available, project_id, resource_id):
            raise HTTPException(404, 'Source was deleted or is being deleted')
        metadata = call(store.ingestion, project_id, resource_id, version)
        if metadata is None:
            raise HTTPException(404, 'Imported source version not found')
        info = metadata['original'] if kind == 'original' else metadata.get('text') if kind == 'text' else next(
            (item for item in metadata['pages'] if item['page'] == page), None)
        if info is None:
            raise HTTPException(404, 'Source text/page not found')
        library = store.library(project_id)
        prefix = library.source_name(resource_id, version).rsplit('/', 1)[0] + '/'
        path = call(library.path, prefix + info['path'])
        import hashlib
        if not path.is_file() or path.stat().st_size != info['bytes']:
            raise HTTPException(409, 'Imported file changed; restore the original version')
        with path.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != info['sha256']:
                raise HTTPException(409, 'Imported file hash mismatch')
        return path, metadata

    @router.get('/projects/{project_id}/library/{resource_id}/versions/{version}/original')
    def original_file(project_id: str, resource_id: str, version: int):
        from fastapi.responses import FileResponse
        path, metadata = imported_path(project_id, resource_id, version, 'original')
        return FileResponse(path, media_type='application/octet-stream', filename=metadata['filename'])

    @router.get('/projects/{project_id}/library/{resource_id}/versions/{version}/text')
    def extracted_text(project_id: str, resource_id: str, version: int):
        from fastapi.responses import PlainTextResponse
        path, _ = imported_path(project_id, resource_id, version, 'text')
        return PlainTextResponse(path.read_text(encoding='utf-8'))

    @router.get('/projects/{project_id}/library/{resource_id}/versions/{version}/pages/{page}')
    def pdf_page(project_id: str, resource_id: str, version: int, page: int):
        from fastapi.responses import PlainTextResponse
        path, _ = imported_path(project_id, resource_id, version, 'page', page)
        return PlainTextResponse(path.read_text(encoding='utf-8'))

    async def change_deleted(request, project_id, kind, item_id, deleted):
        service = getattr(request.app.state, 'service', None)
        if service:
            async with service.lock:
                return call(store.set_deleted, project_id, kind, item_id, deleted)
        return call(store.set_deleted, project_id, kind, item_id, deleted)

    @router.delete('/projects/{project_id}/resources/{resource_id}')
    async def delete_source(project_id: str, resource_id: str, request: Request):
        service = getattr(request.app.state, 'service', None)
        if service:
            async with service.lock:
                if service.worker.future is not None and not service.worker.future.done():
                    raise HTTPException(409, 'Chờ agent kết thúc trước khi xóa nguồn')
                return await asyncio.to_thread(call, store.delete_resource, project_id, resource_id)
        return await asyncio.to_thread(call, store.delete_resource, project_id, resource_id)

    @router.delete('/projects/{project_id}/ideas/{idea_id}')
    async def delete_idea(project_id: str, idea_id: str, request: Request):
        return await change_deleted(request, project_id, 'ideas', idea_id, True)

    @router.post('/projects/{project_id}/ideas/{idea_id}/restore')
    async def restore_idea(project_id: str, idea_id: str, request: Request):
        return await change_deleted(request, project_id, 'ideas', idea_id, False)

    @router.delete('/projects/{project_id}/runs/{run_id}')
    async def delete_run(project_id: str, run_id: str, request: Request):
        return await change_deleted(request, project_id, 'runs', run_id, True)

    @router.post('/projects/{project_id}/runs/{run_id}/restore')
    async def restore_run(project_id: str, run_id: str, request: Request):
        return await change_deleted(request, project_id, 'runs', run_id, False)

    @router.post("/projects/{project_id}/ideas", status_code=201)
    def add_idea(project_id: str, body: IdeaInput):
        return call(store.save_idea, project_id, body.text, body.title, body.mode, body.desired_output)

    @router.put("/projects/{project_id}/ideas/{idea_id}")
    def update_idea(project_id: str, idea_id: str, body: IdeaUpdate):
        return call(store.update_idea, project_id, idea_id, body.text, body.expected_text,
                    body.title, body.expected_title, body.mode, body.desired_output,
                    body.expected_mode, body.expected_desired_output)

    @router.patch("/projects/{project_id}/ideas/{idea_id}/title")
    def rename_idea(project_id: str, idea_id: str, body: IdeaTitleUpdate):
        return call(store.rename_idea, project_id, idea_id, body.title, body.expected_title)

    @router.post("/projects/{project_id}/plan", status_code=202)
    async def plan(project_id: str, body: ContextInput, request: Request):
        return await async_call(request.app.state.service.start, project_id, body.idea_id, body.resource_ids)

    @router.post("/projects/{project_id}/ideas/{idea_id}/answer")
    async def answer(project_id: str, idea_id: str, body: AnswerInput, request: Request):
        return await async_call(request.app.state.service.answer, project_id, idea_id, body.proposal_id, body.version, body.text)

    @router.get("/projects/{project_id}/proposals")
    def proposals(project_id: str, idea_id: str | None = None):
        return call(store.proposals, project_id, idea_id)

    @router.post("/projects/{project_id}/proposals/{proposal_id}/approve")
    async def approve(project_id: str, proposal_id: str, body: ApprovalInput, request: Request):
        return await async_call(request.app.state.service.approve, project_id, proposal_id, body.version, body.context_sha256)

    @router.post("/projects/{project_id}/context")
    def context(project_id: str, body: ContextInput):
        return call(store.context_snapshot, project_id, body.idea_id, body.resource_ids)

    @router.get("/projects/{project_id}/history")
    def history(project_id: str, request: Request, include_deleted: bool = False):
        working = getattr(request.app.state, 'working', None)
        return call(working.history if working else store.history, project_id, include_deleted=include_deleted)

    @router.post('/projects/{project_id}/runs/{run_id}/implement', status_code=202)
    async def implement(project_id: str, run_id: str, request: Request):
        call(store.run, project_id, run_id)
        raise HTTPException(410, 'Luồng code riêng đã ngừng sử dụng. Bắt đầu Working trong tab Run.')

    @router.post('/projects/{project_id}/runs/{run_id}/working', status_code=202)
    async def working(project_id: str, run_id: str, body: WorkingInput, request: Request):
        return await async_call(request.app.state.working.start, project_id, run_id, body.accelerator, body.ttl_seconds, body.search)

    @router.post('/projects/{project_id}/runs/{run_id}/stop', status_code=202)
    async def stop_working(project_id: str, run_id: str, request: Request):
        return await async_call(request.app.state.working.stop, project_id, run_id)

    @router.get('/projects/{project_id}/runs/{run_id}')
    def run_detail(project_id: str, run_id: str, request: Request):
        return call(request.app.state.working.detail, project_id, run_id)

    @router.post('/projects/{project_id}/runs/{run_id}/retry', status_code=201)
    async def retry_run(project_id: str, run_id: str, body: RetryInput, request: Request):
        return await async_call(request.app.state.working.retry, project_id, run_id, body.request_id)

    @router.post('/projects/{project_id}/runs/{run_id}/variants', status_code=201)
    async def create_variant(project_id: str, run_id: str, body: VariantInput, request: Request):
        return await async_call(request.app.state.service.create_variant, project_id, run_id,
                                body.request_id, body.title, body.purpose, body.change_summary, body.mode, body.desired_output)

    @router.get('/projects/{project_id}/runs/{run_id}/logs')
    def run_logs(project_id: str, run_id: str, request: Request, cursor: str | None = None, limit: int = 100):
        if call(request.app.state.working.record, project_id, run_id):
            return call(request.app.state.working.records.logs, project_id, run_id, cursor, limit)
        return call(request.app.state.logs.delta, project_id, run_id, cursor, limit)

    @router.post('/projects/{project_id}/runs/{run_id}/output/library', status_code=201)
    def copy_output(project_id: str, run_id: str, body: OutputCopyInput, request: Request):
        return call(request.app.state.working.copy_output, project_id, run_id, **body.model_dump())

    @router.get('/projects/{project_id}/runs/{run_id}/log-window')
    def log_window(project_id: str, run_id: str, request: Request, offset: int = 0,
                   limit: int = 80, generation: int | None = None):
        record = call(request.app.state.working.record, project_id, run_id)
        reader = request.app.state.working.records.logs if record else request.app.state.logs.delta
        status = call(reader, project_id, run_id, None, 1)
        status['entries'] = []
        window = call(read_log_window, store, project_id, run_id, status['generation'], offset, limit, generation)
        return {**status, **window}

    @router.post('/projects/{project_id}/runs/{run_id}/submit', status_code=202)
    async def submit(project_id: str, run_id: str, request: Request):
        call(store.run, project_id, run_id)
        raise HTTPException(410, 'Luồng submit riêng đã ngừng sử dụng. Bắt đầu Working trong tab Run.')

    @router.post('/projects/{project_id}/runs/{run_id}/reconcile')
    async def reconcile(project_id: str, run_id: str, request: Request):
        return await async_call(request.app.state.working.reconcile, project_id, run_id)

    @router.api_route('/projects/{project_id}/runs/{run_id}/artifacts/{name:path}', methods=['GET', 'HEAD'])
    def artifact(project_id: str, run_id: str, name: str, request: Request, download: bool = True):
        from fastapi.responses import FileResponse, PlainTextResponse
        detail = call(request.app.state.working.detail, project_id, run_id)
        if name not in detail['artifacts']:
            raise HTTPException(404, 'Artifact not found')
        root = call(request.app.state.view.root, project_id, run_id)
        path = root / name
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise HTTPException(404, 'Artifact not found')
        if name == 'report.md':
            if path.stat().st_size > 100_000:
                raise HTTPException(404, 'Artifact not found')
            return PlainTextResponse(path.read_text(encoding='utf-8'), media_type='text/markdown; charset=utf-8')
        if name.startswith('logs/0-run/') and path.suffix in {'.html', '.json'}:
            # Relative tree_data.json requests remain behind the same ownership allowlist.
            from fastapi.responses import Response
            from email.utils import formatdate
            media = 'text/html' if path.suffix == '.html' else 'application/json'
            content = path.read_bytes()
            modified = path.stat().st_mtime
            if name == 'logs/0-run/unified_tree_viz.html' and 'logs/0-run/search-state.json' in detail['artifacts']:
                # Apply the current viewer to saved runs without rewriting their
                # historical artifacts or evaluating/selecting nodes again.
                from ai_scientist.treesearch.utils.run_tree import render_search_state
                state_path = root / 'logs/0-run/search-state.json'
                if state_path.is_symlink() or state_path.is_junction() or not state_path.resolve().is_relative_to(root.resolve()):
                    raise HTTPException(404, 'Artifact not found')
                content = call(render_search_state, json.loads(state_path.read_text(encoding='utf-8')), root.name)
                modified = max(modified, state_path.stat().st_mtime)
            return Response(content, media_type=media,
                headers={'Cache-Control': 'no-cache', 'Access-Control-Allow-Origin': '*', 'Access-Control-Expose-Headers': 'Last-Modified', 'Last-Modified': formatdate(modified, usegmt=True), 'Content-Security-Policy': "sandbox allow-scripts allow-downloads; default-src 'self' https://cdnjs.cloudflare.com; script-src 'unsafe-inline' https://cdnjs.cloudflare.com; style-src 'unsafe-inline' https://cdnjs.cloudflare.com; img-src 'self' data:; connect-src 'self'; frame-ancestors 'self'"})
        preview_types = {'.txt': 'text/plain', '.md': 'text/plain', '.csv': 'text/plain',
                         '.json': 'application/json', '.py': 'text/plain', '.ipynb': 'text/plain',
                         '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                         '.gif': 'image/gif', '.webp': 'image/webp', '.pdf': 'application/pdf'}
        if not download and path.suffix.lower() in preview_types:
            return FileResponse(path, filename=path.name, media_type=preview_types[path.suffix.lower()],
                content_disposition_type='inline',
                headers={'Content-Security-Policy': "sandbox; default-src 'none'; frame-ancestors 'self'", 'X-Content-Type-Options': 'nosniff'})
        return FileResponse(path, filename=path.name)

    return router
