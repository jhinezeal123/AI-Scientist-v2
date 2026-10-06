from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from .kaggle import connect_mcp
from .runtime import load_runtime
from .worker import RuntimeWorker
from .api import library_router
from .store import ProjectStore
from .service import PlanningService


def create_app(config, *, bindings=None, mcp_connection=connect_mcp):
    @asynccontextmanager
    async def lifespan(app):
        loaded = bindings or load_runtime(config)
        worker = RuntimeWorker(loaded.runtime, config.workspace_root / ".workbench/runtime-state.json",
                               uncertain_error=getattr(loaded, "uncertain_error", None))
        app.state.worker = worker
        app.state.runtime = loaded
        store.recover_planning()
        service = PlanningService(store, loaded, worker, config.workspace_root)
        app.state.service = service
        try:
            async with mcp_connection(config) as (session, names):
                app.state.mcp = session
                app.state.mcp_tools = names
                try:
                    yield
                finally:
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
