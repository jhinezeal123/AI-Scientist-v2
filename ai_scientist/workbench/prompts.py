"""Select the editable planner prompt using the pinned idea mode."""
import json

from .models import WorkingProposal
from .modes import snapshot_settings
from .system_prompt import load_prompt


def planning_prompt(context):
    mode, _ = snapshot_settings(context['snapshot'], require_output=True)
    snapshot = {**context['snapshot'], 'idea': {key: value for key, value in context['snapshot']['idea'].items() if key != 'tags'}}
    return load_prompt(f'planner.{mode}',
                       ready_schema=json.dumps(WorkingProposal.model_json_schema(), ensure_ascii=False, separators=(',', ':')),
                       context=json.dumps(snapshot, ensure_ascii=False, separators=(',', ':')))
