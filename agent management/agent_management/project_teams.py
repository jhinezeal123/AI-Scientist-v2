"""Project-owned team lifecycle; accepts a copied agent/model pair."""
from .models import RigSpec, AgentSpec


def default_team(project, pair):
    stages = ('ideation', 'proposal', 'approval', 'execution', 'draft', 'tuning', 'research', 'ablation',
              'analysis', 'summary', 'report', 'plots', 'writeup', 'review')
    return RigSpec(name=project['name'], project_id=project['id'], template='default', max_parallel=2,
                   seats=[AgentSpec(id=stage, harness=pair['harness'], model=pair['model']) for stage in stages])


class ProjectTeams:
    def __init__(self, gateway):
        self.gateway = gateway

    def get(self, project_id):
        control = self.gateway.project_platform(project_id)
        teams = control.store.rigs()
        return control.store.snapshot(teams[0]['id']) if teams else None

    def setup(self, project_id, pair):
        existing = self.get(project_id)
        if existing:
            return existing
        project = self.gateway.projects.project(project_id)
        return self.gateway.project_platform(project_id).create('project-' + project_id, default_team(project, pair))
