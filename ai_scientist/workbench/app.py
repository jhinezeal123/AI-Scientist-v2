"""Compose the GUI, planning worker, independent run workers and Kaggle backend."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .kaggle import connect_kaggle
from .runtime import load_runtime, _agent_gateway_class
from .worker import RuntimeWorker
from .api import library_router
from .store import ProjectStore
from .service import PlanningService
from .run_view import RunView
from .monitor_store import MonitorStore
from .working import WorkingService
from .kaggle_settings import KaggleProxySettings
from .settings_api import settings_router


def create_app(config, *, bindings=None, kaggle_connection=connect_kaggle):
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
        app.state.view = RunView(store, config.workspace_root, lambda: service.idle_check is not None)
        service.view = app.state.view
        app.state.logs = MonitorStore(store)
        try:
            async with kaggle_connection(config) as session:
                app.state.kaggle_backend = 'cli'
                app.state.working = WorkingService(service, config, app.state.view, donor=session)
                app.state.kaggle_settings = KaggleProxySettings(app.state.working)
                if getattr(config, 'allow_new_run_after_idle_check', False):
                    service.idle_check = app.state.working.check_idle
                await app.state.working.recover()
                try:
                    yield
                finally:
                    await app.state.kaggle_settings.close()
                    await app.state.working.close(config.shutdown_seconds)
                    await service.close()
                    await worker.close(config.shutdown_seconds)
        finally:
            if not worker.closed:
                await service.close()
                await worker.close(config.shutdown_seconds)

    app = FastAPI(title="AI Scientist Workbench", lifespan=lifespan)
    store = ProjectStore(config.workspace_root / ".workbench/projects", config.workspace_root)
    app.state.store = store
    app.include_router(library_router(store, config.workspace_root))
    app.include_router(settings_router())
    _agent_gateway_class()
    from _ai_scientist_agent_management.http_api import create_router
    app.include_router(create_router())

    @app.get("/health")
    async def health():
        return {"status": "ok", "runtime_job": app.state.worker.state["status"],
                "kaggle_backend": app.state.kaggle_backend}

    frontend = config.workspace_root / "workbench-ui/dist"
    if frontend.is_dir():
        app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
    return app
