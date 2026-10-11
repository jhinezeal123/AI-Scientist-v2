"""Reusable agent/model pairs, independent of project workflow state."""
import json
from pydantic import Field
from .models import StrictModel, ID


class AgentPreset(StrictModel):
    id: str = Field(pattern=ID)
    name: str = Field(min_length=1, max_length=120)
    harness: str = Field(pattern=ID)
    model: str | None = Field(default=None, min_length=1, max_length=256)


class Presets:
    def __init__(self, store, *, default_model=None):
        self.store = store
        with store.connect(True) as con:
            con.execute('CREATE TABLE IF NOT EXISTS agent_presets(id TEXT PRIMARY KEY,spec_json TEXT NOT NULL)')
            if not con.execute('SELECT 1 FROM agent_presets').fetchone():
                default = AgentPreset(id='default', name='Codex mặc định', harness='codex',
                                      model=default_model)
                con.execute('INSERT INTO agent_presets VALUES(?,?)', (default.id, default.model_dump_json()))

    def list(self):
        with self.store.connect() as con:
            return [json.loads(r['spec_json']) for r in con.execute('SELECT * FROM agent_presets ORDER BY rowid')]

    def put(self, preset):
        harness = next((h for h in self.store.harnesses() if h.id == preset.harness), None)
        if harness is None or not harness.enabled or harness.archived:
            raise ValueError('Choose an enabled configured agent')
        # Catalog entries are picker suggestions. ACP checks negotiated session options.
        with self.store.connect(True) as con:
            con.execute('INSERT INTO agent_presets VALUES(?,?) ON CONFLICT(id) DO UPDATE SET spec_json=excluded.spec_json',
                        (preset.id, preset.model_dump_json()))
        return preset.model_dump()

    def delete(self, identity):
        with self.store.connect(True) as con:
            if con.execute('SELECT COUNT(*) FROM agent_presets').fetchone()[0] <= 1:
                raise ValueError('Keep at least one agent preset')
            if not con.execute('DELETE FROM agent_presets WHERE id=?', (identity,)).rowcount:
                raise KeyError(identity)
