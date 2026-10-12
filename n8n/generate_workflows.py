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
        selected = [node for node in self.body['nodes'] if node['name'] in members]
        # Collapsed groups anchor at their left edge. Keep those edges close;
        # expanded groups retain the detailed operation layout inside them.
        index = len(self.body.get('nodeGroups', []))
        dx = 288 + index*528 - min(node['position'][0] for node in selected)
        dy = -80 - min(node['position'][1] for node in selected)
        for node in selected:
            node['position'] = [node['position'][0]+dx, node['position'][1]+dy]
        self.body.setdefault('nodeGroups', []).append({'id': identity, 'name': name,
            'nodeIds': [node['id'] for node in self.body['nodes'] if node['name'] in members],
            'description': description})


def research():
    g = Graph('workbenchResearch', 'Workbench · Project autoresearch')
    trigger = g.webhook('Research request', 'workbench-research', 0, -240)
    previous = trigger
    manager_choice = single_done = None
    groups = []
    operations = [
        ('ideation', 'Sinh ứng viên · Lưu archive'), ('literature', 'Literature · Novelty từng ứng viên'),
        ('idea_selection', 'Chọn idea từ archive'), ('proposal', 'Lập proposal'),
        ('approval', 'Trao đổi / duyệt proposal'), ('run_approval', 'Cấu hình và duyệt run'),
        ('execution', 'Mở phiên Kaggle đã duyệt'), ('draft', 'Draft · Các baseline song song'),
        ('tuning', 'Tuning · Các cấu hình song song'), ('research', 'Research · Cải tiến và mở rộng'),
        ('ablation', 'Ablation · So sánh thành phần'), ('single_execution', 'Chạy một thí nghiệm'),
        ('tree_export', 'Chọn kết quả · Lưu cây thí nghiệm'), ('multi_seed', 'Tổng hợp đánh giá nhiều seed'),
        ('summary', 'Tổng hợp kết quả từng stage'), ('report', 'Tạo báo cáo nghiên cứu'),
        ('citations', 'Thu thập citation · BibTeX'), ('plots', 'Tổng hợp figures'),
        ('vision_plots', 'VLM · Đánh giá hình trước viết bài'), ('writeup', 'Viết bài · Compile PDF · Reflection'),
        ('vision_paper', 'VLM · Hình và PDF cuối'), ('review', 'Review khoa học'),
        ('collect', 'Thu kết quả · Đóng vòng nghiên cứu')]
    for index, (step, label) in enumerate(operations):
        x = 280 + index*700 + (700 if index>=5 else 0)
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
            g.connect(manager_choice if step=='single_execution' else previous, op, 1 if step=='single_execution' else 0)
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
        old_previous = previous
        previous = complete
        if step=='execution':
            manager_choice=g.condition('Experiment manager bật?', 'search_enabled', x+660, 0)
            g.connect(complete,manager_choice)
            groups[-1][1].append(manager_choice)
            previous=manager_choice
        elif step=='single_execution':
            single_done=complete
            previous=old_previous
            for node in g.body['nodes'][-3:]:
                node['position'][1]=260
        elif step=='multi_seed':
            merged=g.node('Thí nghiệm đã hoàn tất','noOp',{},x+660,0)
            g.connect(complete,merged)
            g.connect(single_done,merged)
            groups[-1][1].append(merged)
            previous=merged
        if step=='approval':
            revise=g.condition('Bạn nhắn lại?', 'revise_proposal', x+660, 0)
            accepted=g.node('Proposal đã chốt','noOp',{},x+880,80)
            g.connect(complete,revise)
            g.connect(revise,'Lập proposal')
            g.connect(revise,accepted,1)
            groups[-1][1].extend([revise,accepted])
            previous=accepted
    again = g.condition('Another approved iteration?', 'continue', x+700, 0)
    g.connect(previous, again)
    restart = g.node('Continue research', 'noOp', {}, x+920, -96)
    g.connect(again, restart)
    g.connect(restart, operations[0][1])
    done = g.node('Project workflow complete', 'noOp', {}, x+920, 96)
    g.connect(again, done, 1)
    groups[-1][1].extend([again, restart, done])
    sections = [
        ('ideation', 'Ideathon / Novelty', ['ideation','literature','idea_selection'], 'Sinh nhiều ứng viên, lưu archive, kiểm tra novelty và chọn một idea.'),
        ('proposal', 'Thiết kế proposal', ['proposal','approval'], 'Lập proposal, làm rõ yêu cầu và duyệt ứng viên hiện tại.'),
        ('run_approval', 'Cấu hình run', ['run_approval'], 'Duyệt đúng run, tài nguyên và phạm vi đã lưu.'),
        ('execution', 'Thực thi thí nghiệm', ['execution','draft','tuning','research','ablation','single_execution','tree_export','multi_seed'], 'Các nhánh song song có shell và thư mục riêng. Mở rộng nằm trong budget và dữ liệu đã duyệt.'),
        ('collect', 'Kết quả / Viết bài / Lặp', ['summary','report','citations','plots','vision_plots','writeup','vision_paper','review','collect'], 'Summary, report, citation, figures, VLM, PDF và review dùng cấu hình đã chọn trong Workbench.')]
    for i, (identity, title, phases, description) in enumerate(sections, 1):
        members = [member for phase, nodes in groups if phase in phases for member in nodes]
        g.group('stage-'+identity, f'{i:02} · {title}', members, description)
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
