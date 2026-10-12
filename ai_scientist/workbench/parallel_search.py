"""Concurrent branches own separate SSH shells, provider jobs and workspaces."""
from concurrent.futures import ThreadPoolExecutor
import copy
import uuid

from .ssh_terminal import transfer_library_file


def execute_branch(owner, stage, task, parent, action, idea=None):
    branch = uuid.uuid4().hex
    child = copy.copy(owner)
    child.branch = branch
    child.workdir = owner.root / 'working-agent' / branch
    child.querydir = owner.root / 'query-agent' / branch
    child.workdir.mkdir(parents=True, exist_ok=True)
    child.querydir.mkdir(parents=True, exist_ok=True)
    child.descriptor = {**owner.descriptor, 'remote_directory': owner.descriptor['remote_directory'] + '/branches/' + branch}
    child.terminal = owner.service._run_donor(owner.key).open_branch(owner.key[1], branch,
        lambda text: owner.service.records.append_log(*owner.key, text))
    with owner.service.worker_lock:
        owner.service.branch_terminals[(*owner.key, branch)] = child.terminal
    try:
        for name, data in owner.service.store.library(owner.key[0]).selected_files(owner.approved['snapshot']):
            transfer_library_file(child.terminal, name, data)
        for name, data in owner.service.store.variant_stage_files(owner.approved['snapshot']).items():
            transfer_library_file(child.terminal, name, data)
        return child.execute_node(stage, task, parent, action, stage_idea=idea)
    finally:
        child.terminal.close()
        with owner.service.worker_lock:
            owner.service.branch_terminals.pop((*owner.key, branch), None)


def execute_batch(actor, selected):
    """Generate tuning/ablation plans centrally, then execute independent branches."""
    from ai_scientist.treesearch.parallel_agent import ParallelAgent
    jobs = []
    for chosen in selected:
        parent = actor.journal.get_node_by_id(chosen.id) if chosen else None
        if chosen and parent is None:
            raise ValueError('Selected baseline is missing from its stage journal')
        action = 'draft' if parent is None else 'debug' if parent.is_buggy else 'improve'
        idea = None
        if actor.owner.pipeline and action == 'improve':
            if actor.stage_name.startswith('2_'):
                proposal = ParallelAgent._generate_hyperparam_tuning_idea(actor)
                actor._hyperparam_tuning_state['tried_hyperparams'].add(proposal.name)
                idea = {'name': proposal.name, 'description': proposal.description}
            elif actor.stage_name.startswith('4_'):
                proposal = ParallelAgent._generate_ablation_idea(actor)
                actor._ablation_state['completed_ablations'].add(proposal.name)
                idea = {'name': proposal.name, 'description': proposal.description}
        jobs.append((parent, action, idea))
    with ThreadPoolExecutor(max_workers=len(jobs), thread_name_prefix='research-branch') as pool:
        futures = [pool.submit(execute_branch, actor.owner, actor.stage_name, actor.task_desc, *job) for job in jobs]
        for future, (_, _, idea) in zip(futures, jobs):
            node = future.result()
            if idea:
                if actor.stage_name.startswith('2_'):
                    node.hyperparam_name = idea['name']
                else:
                    node.ablation_name = idea['name']
            actor.journal.append(node)
