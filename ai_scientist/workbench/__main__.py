"""Launch the local app or an explicitly requested read-only runtime smoke."""
import argparse
import asyncio
import json
from pathlib import Path
import uuid

from .app import create_app
from .models import WorkbenchConfig


async def smoke(app, config):
    async with app.router.lifespan_context(app):
        prompt = json.dumps({"needs_clarification": False, "questions": [],
            "paraphrase": "runtime readiness", "objective": "Confirm JSON transport only",
            "data_refs": [], "split": "not applicable", "metric": "not applicable",
            "implementation_steps": ["Confirm JSON transport"], "budget": {}, "expected_outputs": []})
        request = app.state.runtime.request_type(uuid.uuid4().hex, "mvp0_plan",
            "Return this exact JSON as role result text. No tools or files: " + prompt,
            config.workspace_root, timeout_seconds=120)
        result, payload = await app.state.worker.run(request)
        print(json.dumps({"status": "ready", "payload": payload.model_dump(),
                          "session_id": result.session_id, "mcp_tools": app.state.mcp_tools}))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path(".workbench/config.local.json"))
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    config = WorkbenchConfig.load(args.config)
    app = create_app(config)
    if args.smoke:
        asyncio.run(smoke(app, config))
    else:
        import uvicorn
        uvicorn.run(app, host="127.0.0.1", port=args.port, workers=1)


if __name__ == "__main__":
    main()
