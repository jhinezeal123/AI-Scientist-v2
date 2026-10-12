"""Build importable n8n workflows. Credentials contain references only."""
import json
from pathlib import Path

CREDENTIAL = {'httpHeaderAuth': {'id': 'workbenchBridge', 'name': 'Local Workbench bridge'}}
BASE = 'http://127.0.0.1:8000/api/agent-management/n8n'


class Graph:
    def __init__(self, identity, name):
        self.body = {'id': identity, 'name': name, 'active': False, 'nodes': [], 'connections': {},
                     'settings': {'executionOrder': 'v1', 'saveDataSuccessExecution': 'all',
                                  'saveDataErrorExecution': 'all', 'saveExecutionProgress': True}}

    def node(self, name, kind, parameters, x, y, version=1, **extra):
        self.body['nodes'].append({'id': name.replace(' ', '_'), 'name': name,
            'type': 'n8n-nodes-base.'+kind, 'typeVersion': version, 'position': [x, y],
            'parameters': parameters, **extra})
        return name

    def connect(self, source, target, output=0):
        outputs = self.body['connections'].setdefault(source, {'main': []})['main']
        while len(outputs) <= output:
            outputs.append([])
        outputs[output].append({'node': target, 'type': 'main', 'index': 0})

    def webhook(self, name, path, x=0, y=0):
        return self.node(name, 'webhook', {'httpMethod': 'POST', 'path': path,
            'authentication': 'headerAuth', 'responseMode': 'onReceived', 'options': {}},
            x, y, version=2, webhookId=path, credentials=CREDENTIAL)

    def http(self, name, url, body, x, y):
        return self.node(name, 'httpRequest', {'method': 'POST', 'url': url,
            'authentication': 'genericCredentialType', 'genericAuthType': 'httpHeaderAuth',
            'sendBody': True, 'specifyBody': 'json', 'jsonBody': body,
            'options': {'timeout': 10000}}, x, y, version=4.2, credentials=CREDENTIAL)

    def condition(self, name, field, x, y):
        return self.node(name, 'if', {'conditions': {'options': {'caseSensitive': True,
            'leftValue': '', 'typeValidation': 'strict', 'version': 2}, 'conditions': [{
            'id': name, 'leftValue': '={{ $json.'+field+' }}', 'rightValue': '',
            'operator': {'type': 'boolean', 'operation': 'true', 'singleValue': True}}],
            'combinator': 'and'}, 'options': {}}, x, y, version=2.2)

    def wait(self, name, x, y):
        return self.node(name, 'wait', {'resume': 'timeInterval', 'amount': 2, 'unit': 'seconds'},
                         x, y, version=1.1, webhookId=name.replace(' ', '-'))

    def stop(self, name, x, y):
        return self.node(name, 'stopAndError', {'errorMessage': '={{ $json.error || "Review this request in Workbench before resuming" }}'}, x, y)

    def note(self, text, x, y, width=450, height=170):
        self.node('Note '+str(len(self.body['nodes'])), 'stickyNote',
                  {'content': text, 'width': width, 'height': height, 'color': 4}, x, y)

    def group(self, identity, name, members, description):
        self.body.setdefault('nodeGroups', []).append({'id': identity, 'name': name,
            'nodeIds': [node['id'] for node in self.body['nodes'] if node['name'] in members],
            'description': description})


def research():
    g = Graph('workbenchResearch', 'Workbench · Project autoresearch')
    trigger = g.webhook('Research request', 'workbench-research', 0, -240)
    previous = trigger
    groups = []
    for index, (step, label) in enumerate((('ideation', 'Ideathon + literature and novelty'),
        ('proposal', 'Lập proposal'), ('approval', 'Trao đổi / duyệt proposal'),
        ('run_approval', 'Configured run approval'), ('execution', 'Start approved Kaggle run'),
        ('collect', 'Observe run and collect result'))):
        x = 280 + index*700 + (700 if index>=3 else 0)
        body = '={{ {project_id: $("Research request").first().json.body.project_id, workflow_id: $("Research request").first().json.body.workflow_id, generation: $("Research request").first().json.body.generation, iteration: $json.iteration ?? $("Research request").first().json.body.iteration, step: "'+step+'", execution_id: $execution.id} }}'
        resume_url = '$execution.resumeUrl.split("?")[0] + "/'+step+'" + ($execution.resumeUrl.includes("?") ? "?" + $execution.resumeUrl.split("?")[1] + "&" : "?") + "wb_generation=" + $("Research request").first().json.body.generation + "&wb_iteration=" + ($json.iteration ?? $("Research request").first().json.body.iteration)'
        resume_url += ' + "&wb_round=" + ($json.proposal_round ?? 0)'
        body = body.replace('execution_id: $execution.id', 'execution_id: $execution.id, resume_url: '+resume_url)
        body = body.replace('execution_id: $execution.id', 'proposal_round: $json.proposal_round ?? 0, execution_id: $execution.id')
        if step=='approval':
            unclear=g.condition('Agent yêu cầu làm rõ?', 'needs_clarification', x, 0)
            clarification=g.http('Khóa duyệt · Yêu cầu bạn làm rõ', BASE+'/step', body, x+220,-160)
            op=g.http(label,BASE+'/step',body,x+220,160)
            g.connect(previous,unclear)
            g.connect(unclear,clarification)
            g.connect(unclear,op,1)
            x+=220
        else:
            op = g.http(label, BASE+'/step', body, x, 0)
            g.connect(previous,op)
        wait_name='Chờ bạn nhắn / quyết định duyệt' if step=='approval' else step+' · chờ webhook'
        wait = g.node(wait_name, 'wait', {'resume': 'webhook',
            'incomingAuthentication': 'headerAuth', 'httpMethod': 'POST', 'responseMode': 'onReceived',
            'options': {'webhookSuffix': step}},
            x+220, 0, version=1.1, webhookId='research-'+step, credentials=CREDENTIAL)
        # Wait emits the HTTP envelope. Validate and unwrap the result; throwing
        # uses n8n's standard failed-execution handling without extra IF branches.
        code = f'''const started = $({json.dumps(label)}).first().json;
return $input.all().map(item => {{
  const result = item.json.body;
  const query = item.json.query || {{}};
  if (String(query.wb_generation) !== String(started.generation)
      || String(query.wb_iteration) !== String(started.iteration))
    throw new Error('Completion notification belongs to another research iteration');
  if (String(query.wb_round ?? '0') !== String(started.request_round)
      || result?.request_round !== started.request_round)
    throw new Error('Completion notification belongs to another proposal discussion round');
  if (!result || result.project_id !== started.project_id || result.workflow_id !== started.workflow_id
      || result.generation !== started.generation || result.step !== started.step)
    throw new Error('Completion notification does not match this research step');
  if (result.status === 'FAILED') throw new Error(result.error || 'Research step failed');
  if (result.status !== 'DONE' || result.pending || result.failed)
    throw new Error('Research step has not completed');
  if (result.iteration !== started.iteration + (started.step === 'collect' ? 1 : 0))
    throw new Error('Completion notification belongs to another research iteration');
  return {{json: result}};
}});'''
        if step=='approval':
            code=code.replace('const started = '+f'$({json.dumps(label)}).first().json;',
                'const decision = $("Agent yêu cầu làm rõ?").first(0, $runIndex)'
                ' ?? $("Agent yêu cầu làm rõ?").first(1, $runIndex);\n'
                'const started = {...decision.json, step: "approval"};')
        complete = g.node(step+' · complete', 'code', {'jsCode': code}, x+440, 0, version=2)
        groups.append((step, [op, wait, complete]))
        if step=='approval':
            g.connect(clarification,wait)
            groups[-1][1].extend([unclear,clarification])
        g.connect(op, wait)
        g.connect(wait, complete)
        previous = complete
        if step=='approval':
            revise=g.condition('Bạn nhắn lại?', 'revise_proposal', x+660, 0)
            accepted=g.node('Proposal đã chốt','noOp',{},x+880,80)
            g.connect(complete,revise)
            g.connect(revise,'Lập proposal')
            g.connect(revise,accepted,1)
            groups[-1][1].extend([revise,accepted])
            previous=accepted
    again = g.condition('Another approved iteration?', 'continue', 5180, 0)
    g.connect(previous, again)
    restart = g.node('Continue research', 'noOp', {}, 5400, -96)
    g.connect(again, restart)
    g.connect(restart, 'Ideathon + literature and novelty')
    done = g.node('Project workflow complete', 'noOp', {}, 5400, 96)
    g.connect(again, done, 1)
    groups[-1][1].extend([again, restart, done])
    groups[1][1].extend(groups[2][1])
    del groups[2]
    titles = ['Ideathon / Novelty', 'Thiết kế proposal', 'Cấu hình run', 'Thực thi', 'Kết quả / Lặp']
    descriptions = ['Tạo idea, tìm tài liệu và phản biện độ mới.',
        'Lập và duyệt proposal từ mục tiêu, context và phạm vi đã lưu.', 'Cấu hình và duyệt bắt đầu run theo Hybrid / Full agent.',
        'Bắt đầu run Kaggle với preset và budget đã lưu.', 'Thu kết quả, hoàn tất hoặc chuyển sang vòng tiếp theo.']
    for i, ((stage, members), title, description) in enumerate(zip(groups, titles, descriptions), 1):
        g.group('stage-'+stage, f'{i:02} · {title}', members, description)
    g.note('## Project autoresearch\nConfigured ideathon → literature / novelty reflection → proposal → configured approvals → approved Kaggle run.\nHybrid and full-agent settings come from the saved project grant.\nSet goal, presets, Library context and limits in the project Workflow tab. Start there to issue a saved grant.', -80, -400, 1100)
    g.note('## Every agent request uses the Agent loop workflow\nThe model chooses one action; Workbench executes it in the approved SSH session and verifies its receipt.\nLiterature search/reflection, citation gathering, VLM images and paper reviews use dedicated stage presets through this loop.\nRun finishing: summaries → references → plots → LaTeX with visual reflections → image/caption/reference and duplicate checks → text review.', 2800, -400, 1100)
    return g.body


def agent():
    g = Graph('workbenchAgent', 'Workbench · Agent and remote action loop')
    start = g.webhook('Agent request', 'workbench-agent')
    body = '={{ {execution_id: $execution.id} }}'
    url = '={{ "'+BASE+'/tickets/" + $("Agent request").first().json.body.ticket_id + "/turn" }}'
    turn = g.http('Call saved agent and model', url, body, 280, 0)
    failed = g.condition('Provider failed?', 'failed', 500, 0)
    pending = g.condition('Provider running?', 'pending', 720, 0)
    wait = g.wait('Wait for provider', 720, 220)
    stop = g.stop('Review provider or action error', 500, -220)
    complete = g.condition('Result complete?', 'finished', 960, 0)
    action = g.http('Execute verified remote action',
        '={{ "'+BASE+'/tickets/" + $json.ticket_id + "/action/" + $json.turn }}', '={{ {} }}', 960, 220)
    action_failed = g.condition('Action failed?', 'failed', 1190, 220)
    done = g.node('Validated result returned to research', 'noOp', {}, 1200, 0)
    g.connect(start, turn); g.connect(turn, failed); g.connect(failed, stop)
    g.connect(failed, pending, 1); g.connect(pending, wait); g.connect(wait, turn)
    g.connect(pending, complete, 1); g.connect(complete, done)
    g.connect(complete, action, 1); g.connect(action, action_failed)
    g.connect(action_failed, stop); g.connect(action_failed, turn, 1)
    g.body['nodeGroups'] = []
    g.note('## Agent request\nUses the project’s frozen preset and result schema. Every provider call counts against the saved grant.\nRemote commands, reads, writes and artifact fetches go through the approved Kaggle session.', -70, -420, 1350)
    g.note('## No automatic replay of uncertain work\nFailed or uncertain actions stop this execution and appear in the project. Review and reconcile before continuing.', 400, 420, 800)
    return g.body


if __name__ == '__main__':
    folder = Path(__file__).parent
    for workflow in (research(), agent()):
        (folder/(workflow['id']+'.json')).write_text(json.dumps(workflow, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
