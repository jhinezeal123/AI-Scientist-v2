"""Compose the local GUI, project store, shared Codex worker and MCP lifetime."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .kaggle import connect_mcp
from .runtime import load_runtime
from .worker import RuntimeWorker
from .api import library_router
from .store import ProjectStore
from .service import PlanningService
from .implementation import ImplementationService
from .submission import SubmissionService
from .monitor import RunMonitor
from .collection import RunResultsService


def create_app(config, *, bindings=None, mcp_connection=connect_mcp):
    @asynccontextmanager
    async def lifespan(app):
        loaded = bindings or load_runtime(config)
        worker = RuntimeWorker(loaded.runtime, config.workspace_root / ".workbench/runtime-state.json",
                               uncertain_error=getattr(loaded, "uncertain_error", None))
        app.state.worker = worker
        app.state.runtime = loaded
        store.recover_planning()
        store.recover_implementation()
        store.recover_submission()
        service = PlanningService(store, loaded, worker, config.workspace_root)
        app.state.service = service
        app.state.implementation = ImplementationService(service, config)
        try:
            async with mcp_connection(config) as (session, names):
                app.state.mcp = session
                app.state.mcp_tools = names
                app.state.submission = SubmissionService(app.state.implementation, config, session)
                app.state.results = RunResultsService(app.state.submission, worker, loaded)
                if getattr(config, 'allow_new_run_after_idle_check', False):
                    service.idle_check = app.state.submission.check_idle
                app.state.monitor = RunMonitor(app.state.submission, app.state.results)
                app.state.monitor.start()
                try:
                    yield
                finally:
                    await app.state.monitor.close()
                    await app.state.submission.close()
                    await service.close()
                    await worker.close(config.shutdown_seconds)
        finally:
            if not worker.closed:
                await service.close()
                await worker.close(config.shutdown_seconds)

    app = FastAPI(title="AI Scientist Workbench", lifespan=lifespan)
    store = ProjectStore(config.workspace_root / ".workbench/projects")
    app.state.store = store
    app.include_router(library_router(store, config.workspace_root))

    @app.get("/health")
    async def health():
        return {"status": "ok", "runtime_job": app.state.worker.state["status"],
                "mcp_tools": app.state.mcp_tools}

    frontend = config.workspace_root / "workbench-ui/dist"
    if frontend.is_dir():
        app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
    return app
