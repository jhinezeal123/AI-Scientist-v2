"""Private first-run import file. Never print its data or commit it."""
import json
from pathlib import Path
import sys

workspace = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(workspace))
from ai_scientist.workbench.n8n_client import N8nClient

client = N8nClient(workspace)
target = workspace / '.workbench/n8n/credentials-import.json'
target.write_text(json.dumps([{'id': 'workbenchBridge', 'name': 'Local Workbench bridge',
    'type': 'httpHeaderAuth', 'data': {'name': 'X-Workbench-N8n', 'value': client.token}}]), encoding='utf-8')
