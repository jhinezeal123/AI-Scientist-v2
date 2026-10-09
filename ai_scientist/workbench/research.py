"""Approved research finishing steps using upstream prompts/functions and one SSH."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import statistics
import time
from types import SimpleNamespace

from .models import ResearchPlan
from .journal import restore_journal
from .ssh_terminal import collect_files, transfer_library_file


def saved_pipeline(root):
    path = root / 'research/pipeline.json'
    if (not path.is_file() or path.is_symlink() or path.parent.is_symlink()
            or path.is_junction() or path.parent.is_junction()
            or not path.resolve().is_relative_to(root.resolve())):
        return None
    return json.loads(path.read_text(encoding='utf-8'))


def interrupt_saved_pipeline(root):
    state = saved_pipeline(root)
    if state is None or state['status'] not in {'running', 'pending'}:
        return
    for component in state['components'].values():
        if component['status'] in {'pending','running'}:
            component.update(status='interrupted',reason='Backend restart: không replay công việc còn thiếu.')
    state.update(status='interrupted',updated_at=datetime.now(timezone.utc).isoformat())
    from .tree_search import write_json
    write_json(root / 'research/pipeline.json',state)


class CodexResearchClient:
    """The small chat client surface used by upstream llm.get_response_from_llm."""
    def __init__(self, owner):
        self.owner = owner
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, *, messages, **kwargs):
        response = self.owner.query(system_message={
            'Role': 'Fulfil the original research module request below using only verified experiment evidence.',
            'Messages': messages,
        }, user_message=None)
        # Upstream make_llm_call's tracker expects these response attributes.
        # Actual token counts come from owner.call_agent, not fabricated usage.
        return SimpleNamespace(model=self.owner.service.config.codex_model, created=int(time.time()),
                               choices=[SimpleNamespace(message=SimpleNamespace(content=response))])


class ResearchPipeline:
    """Persist the scope and outcome of finishing steps for this experiment."""
    def __init__(self, owner, settings):
        self.owner = owner
        self.plan = ResearchPlan.model_validate(settings)
        self.root = owner.root / 'research'
        self.root.mkdir(exist_ok=True)
        self.client = CodexResearchClient(owner)
        execution = 'execution' if getattr(owner, 'single_run', False) else 'tree'
        requested = {execution:True, 'multi_seed':bool(self.plan.seeds) and not getattr(owner, 'single_run', False), 'summary':self.plan.summary,
                     'report':self.plan.report, 'plots':self.plan.plots,
                     'writeup':self.plan.writeup != 'none', 'review':self.plan.review}
        self.state = {'format':1, 'run_id':owner.key[1], 'context_sha256':owner.approved['context_sha256'],
                      'plan':self.plan.model_dump(), 'status':'running',
                      'components':{name:{'status':'pending' if enabled else 'not_requested',
                                          'reason':'' if enabled else 'Không được yêu cầu trong proposal.', 'artifacts':[]}
                                    for name, enabled in requested.items()}}
        self.seed_results = {}
        self.limitations = []
        self.state['components'][execution]['status'] = 'running'
        self.save()

    def save(self):
        from .tree_search import write_json
        self.state['updated_at'] = datetime.now(timezone.utc).isoformat()
        write_json(self.root / 'pipeline.json', self.state)

    def set(self, name, status, reason='', artifacts=()):
        self.state['components'][name] = {'status':status, 'reason':reason, 'artifacts':list(artifacts)}
        self.save()

    def step(self, name, operation):
        if self.state['components'][name]['status'] == 'not_requested':
            return
        self.owner.check_running()
        self.set(name, 'running')
        self.owner.service.records.update(*self.owner.key, phase='research_' + name)
        self.owner.service.records.append_log(*self.owner.key, f'Research: {name}…\n', 'backend')
        try:
            artifacts = operation()
            self.owner.check_running()
            self.set(name, 'completed', artifacts=artifacts)
        except Exception as exc:
            reason = f'{name} chưa hoàn tất ({type(exc).__name__}): {str(exc)[:300]}'
            self.limitations.append(reason)
            self.set(name, 'failed', reason)
            self.owner.service.records.append_log(*self.owner.key, reason + '\n', 'backend')
        except BaseException:
            self.set(name, 'interrupted', 'Working đã bị dừng hoặc hết thời gian; không tự chạy lại.')
            raise

    def interrupted(self, status='interrupted', reason='Working dừng trước khi hoàn tất; không replay khi restart.'):
        self.state['status'] = status
        for component in self.state['components'].values():
            if component['status'] in {'pending', 'running'}:
                component.update(status=status, reason=reason)
        self.save()

    def record_seeds(self, stage, nodes):
        results = []
        for node in nodes:
            root, _, payload = self.owner.nodes[node.id]
            request = json.loads((root / 'search-request.json').read_text(encoding='utf-8'))
            results.append({'node_id':node.id, 'seed':request['evaluation_seed'],
                            'succeeded':not node.is_buggy, 'metric':node.metric.to_dict(),
                            'result':payload.model_dump()})
        self.seed_results[stage] = results
        self.state['seed_results'] = self.seed_results
        self.set('multi_seed', 'running', 'Đang đánh giá các seed đã duyệt.')

    def finish_seeds(self):
        from .tree_search import write_json
        stats = {}
        for stage, results in self.seed_results.items():
            if {item['seed'] for item in results} != set(self.plan.seeds) or not all(item['succeeded'] for item in results):
                raise ValueError(f'Chưa đủ seed thành công ở {stage}')
            metrics = [item['metric'] for item in results]
            values = [item['value'] for item in metrics if item['value'] is not None]
            if len(values) != len(results) or len({(item['name'],item['maximize']) for item in metrics}) != 1:
                raise ValueError('Seed metrics phải có cùng tên/hướng và giá trị đã xác minh')
            stats[stage] = {'n':len(values), 'mean':statistics.mean(values),
                            'sample_std':statistics.stdev(values) if len(values)>1 else None}
        if {int(stage.split('_')[0]) for stage in self.seed_results} != set(self.plan.seed_stages):
            raise ValueError('Chưa đánh giá đủ các stage/seed được duyệt')
        write_json(self.root / 'multi-seed.json', {'seeds':self.plan.seeds,'stages':self.seed_results,'statistics':stats,
                    'selection':'Seed repetitions excluded from model selection; the approved split remains fixed.'})
        return ['research/multi-seed.json']

    def journals(self):
        groups = {}
        for name, journal in self.owner.manager.journals.items():
            number = int(name.split('_')[0])
            records = groups.setdefault(number,{})
            for node in journal.nodes:
                records.setdefault(node.id,node.to_dict())
        return {number:restore_journal({'nodes':list(records.values())}) for number,records in groups.items()}

    def summarize(self):
        from ai_scientist.treesearch.log_summarization import get_stage_summary
        from .tree_search import write_json
        artifacts = []
        journals = self.journals()
        if getattr(self.owner, 'single_run', False):
            journal = journals[1]
            summary = get_stage_summary(journal, 'One user-controlled run', self.owner.service.config.codex_model, self.client)
            if not isinstance(summary, dict) or not summary:
                raise ValueError('Summary chưa trả JSON hợp lệ')
            write_json(self.root / 'summary.json', summary)
            # Upstream plotting/writeup read this interchange filename; it
            # describes this single run and does not schedule a tuning stage.
            write_json(self.owner.logs / 'baseline_summary.json',
                       {'best node': self.node_log(journal.nodes[0]), 'best node with different seeds': []})
            return ['research/summary.json', 'logs/0-run/baseline_summary.json']
        for number, journal in journals.items():
            self.owner.check_running()
            stage = self.owner.manager.main_stage_dict[number]
            summary = get_stage_summary(journal,stage,self.owner.service.config.codex_model,self.client)
            if not isinstance(summary,dict) or not summary:
                raise ValueError('Upstream stage summary chưa trả JSON hợp lệ')
            write_json(self.root / f'stage-{number}-summary.json',summary)
            artifacts.append(f'research/stage-{number}-summary.json')
        # Keep the upstream interchange schema read by plot/writeup modules.
        for number, filename in ((1,'draft_summary'),(2,'baseline_summary'),(3,'research_summary'),(4,'ablation_summary')):
            journal = journals.get(number)
            if journal is None:
                continue
            if number == 1:
                summary = json.loads((self.root / 'stage-1-summary.json').read_text(encoding='utf-8'))
            elif number in {2,3}:
                best = journal.get_best_node(cfg=self.owner.manager.cfg)
                summary = {'best node':self.node_log(best) if best else {},
                           'best node with different seeds':[self.node_log(node) for node in journal.nodes if node.is_seed_node]}
            else:
                summary = [self.node_log(node) for node in journal.good_nodes if node.ablation_name and not node.is_seed_node]
            write_json(self.owner.logs / f'{filename}.json',summary)
            artifacts.append(f'logs/0-run/{filename}.json')
        return artifacts

    def node_log(self, node):
        from ai_scientist.treesearch.log_summarization import get_node_log
        result = get_node_log(node)
        # Plot scripts run in output/research, while staged input evidence is
        # outside source/output so it is not counted as newly generated output.
        prefix = f'../../research-input/evidence/nodes/{node.id}/'
        result['exp_results_dir'] = prefix + 'output'
        manifest = self.owner.nodes.get(node.id, (None, {'files':[]}, None))[1]
        result['exp_results_npy_files'] = [prefix + item['path'] for item in manifest['files']
                                          if item['path'].endswith('.npy')]
        return result

    def report(self):
        from ai_scientist.treesearch.journal2report import journal2report
        records = {}
        for journal in self.owner.manager.journals.values():
            for node in journal.nodes:
                records.setdefault(node.id,node.to_dict())
        journal = restore_journal({'nodes':list(records.values())})
        idea = json.loads((self.owner.root / 'idea.json').read_text(encoding='utf-8'))
        text = journal2report(journal,idea,self.owner.manager.cfg.report)
        if not isinstance(text,str) or not text.strip():
            raise ValueError('Technical report is empty')
        (self.root / 'report.md').write_text(text,encoding='utf-8')
        return ['research/report.md']

    def remote_exec(self, command, timeout=60):
        self.owner.check_running()
        remaining = int(self.owner.deadline - time.monotonic())
        if remaining < 1:
            self.owner.check_running()
            raise TimeoutError('Research deadline reached')
        result = self.owner.terminal.request('exec',command=command,timeout=min(timeout,remaining))
        self.owner.check_running()
        return {**result,'text':result.get('output','')}

    def send(self, name, data):
        self.owner.check_running()
        if len(data) > 1_000_000:
            # Chunk assembly uses relative paths in the persistent shell; a
            # prior plot/compiler command may have changed its cwd.
            self.remote_exec('cd ' + shlex.quote(self.owner.descriptor['remote_directory']))
        transfer_library_file(self.owner.terminal,name,data)

    def collect_remote(self):
        manifest = collect_files(self.owner.terminal,self.root / 'remote',
                                 self.owner.approved['body'].get('budget',{}).get('output_bytes'))
        from .tree_search import write_json
        write_json(self.root / 'remote-manifest.json',manifest)
        return manifest

    def plots(self):
        from ai_scientist.perform_plotting import aggregate_plots
        from ai_scientist.perform_icbinb_writeup import load_exp_summaries
        self.send('output/research/idea.md',(self.owner.root / 'idea.md').read_bytes())
        for path in self.owner.logs.glob('*_summary.json'):
            self.send('output/research/logs/0-run/' + path.name,path.read_bytes())
        # All evidence keeps node IDs and verified bytes; generated code only
        # executes in Kaggle. The original node folders are never modified.
        index = {}
        for node_id,(root,manifest,_) in self.owner.nodes.items():
            index[node_id] = []
            for item in manifest['files']:
                data = (root / item['path']).read_bytes()
                if hashlib.sha256(data).hexdigest()!=item['sha256']:
                    raise ValueError('Node evidence changed before plotting')
                name = f'research-input/evidence/nodes/{node_id}/' + item['path']
                self.send(name,data)
                index[node_id].append({'path':'../../' + name,**{key:item[key] for key in ('bytes','sha256')}})
        self.send('research-input/evidence-index.json',json.dumps(index,ensure_ascii=False).encode())
        # Original prompt filtering omits paths/metrics; preserve the full saved
        # evidence as an additional scope-aware message for the Codex adapter.
        self.owner.research_context = {'summaries':load_exp_summaries(str(self.owner.root)), 'files':index,
                                      'remote_cwd':'output/research'}
        runs = []
        def run_script(code, local_script, base_folder, filename):
            Path(local_script).write_text(code,encoding='utf-8')
            self.send('output/research/' + filename,code.encode())
            remote = self.owner.descriptor['remote_directory'] + '/output/research'
            result = self.remote_exec('cd ' + shlex.quote(remote) + ' && python ' + shlex.quote(filename))
            runs.append(result)
            manifest = self.collect_remote()
            for item in manifest['files']:
                if item['path'].startswith('output/research/figures/'):
                    target = self.owner.root / 'figures' / Path(item['path']).name
                    target.parent.mkdir(exist_ok=True)
                    shutil.copyfile(self.root / 'remote' / item['path'],target)
            return f"Returncode: {result['returncode']}\n{result.get('text','')}"
        try:
            aggregate_plots(str(self.owner.root),model=self.owner.service.config.codex_model,
                            n_reflections=self.plan.reflections,client=self.client,run_script=run_script,raise_errors=True)
        finally:
            self.owner.research_context = None
        files = list((self.owner.root / 'figures').glob('*.png'))
        if not runs or runs[-1]['returncode'] != 0 or not files:
            raise ValueError('Plot aggregator chưa tạo figure PNG được xác minh')
        return ['auto_plot_aggregator.py',*('figures/' + file.name for file in files)]

    def writeup(self):
        from ai_scientist import perform_icbinb_writeup as workshop
        from ai_scientist import perform_writeup as normal
        from ai_scientist.llm import get_response_from_llm
        module = workshop if self.plan.writeup=='icbinb' else normal
        pages = 4 if self.plan.writeup=='icbinb' else 8
        self.prepare_tex()
        template = Path(module.__file__).parent / ('blank_icbinb_latex' if pages==4 else 'blank_icml_latex')
        local = self.root / 'latex'
        shutil.copytree(template,local)
        for bib in local.glob('*.bib'):
            bib.write_text('',encoding='utf-8')
        figures = self.owner.root / 'figures'
        names = [path.name for path in figures.glob('*.png')]
        if names:
            shutil.copytree(figures,self.root / 'figures')
        summaries = workshop.load_exp_summaries(str(self.owner.root))
        aggregator = self.owner.root / 'auto_plot_aggregator.py'
        latex = (local / 'template.tex').read_text(encoding='utf-8')
        # Do not carry the template's example references/claims into a new paper.
        latex = re.sub(r'(\\begin\{filecontents\}\{references.bib\}).*?(\\end\{filecontents\})',r'\1\n\2',latex,flags=re.DOTALL)
        context = module.writeup_prompt.format(idea_text=(self.owner.root/'idea.md').read_text(encoding='utf-8'),
                    summaries=json.dumps(summaries,ensure_ascii=False),
                    aggregator_code=aggregator.read_text(encoding='utf-8') if aggregator.is_file() else '',
                    plot_list=', '.join(names),latex_writeup=latex,
                    plot_descriptions='Only verified filenames/data are available. No visual review was performed.')
        system = module.writeup_system_message_template.format(page_limit=pages)
        response,history = get_response_from_llm(context,self.client,self.owner.service.config.codex_model,system)
        self.compile_draft(response,local)
        for _ in range(self.plan.reflections):
            feedback = (local/'compile.log').read_text(encoding='utf-8')[-12000:]
            response,history = get_response_from_llm(
                'Revise the complete LaTeX draft using the compiler output below. Use only verified results and selected Library references; do not invent citations or claim visual review. '
                'Return the entire file in a latex fence, or say I am done if the compiled draft needs no change.\n' + feedback,
                self.client,self.owner.service.config.codex_model,system,msg_history=history[-2:])
            if 'I am done' in response and '```latex' not in response:
                break
            self.compile_draft(response,local)
        pdf = self.root / 'paper.pdf'
        if not pdf.is_file():
            raise ValueError('LaTeX chưa compile được PDF; giữ bản thảo và compile.log')
        from pypdf import PdfReader
        if not PdfReader(pdf).pages:
            raise ValueError('PDF không có trang hợp lệ')
        return ['research/paper.pdf','research/latex/template.tex','research/latex/compile.log',
                'research/tex-bootstrap.log']

    def prepare_tex(self):
        """Provision upstream templates' compiler only for an explicitly selected PDF."""
        styles = ['cleveref.sty', 'subfigure.sty', 'times.sty', 'natbib.sty']
        packages = ['texlive-latex-extra', 'texlive-fonts-recommended']
        if self.plan.writeup == 'icml':
            styles += ['algorithm.sty', 'algorithmic.sty']
            packages.append('texlive-science')
        checks = ['command -v pdflatex', 'command -v bibtex', 'command -v kpsewhich']
        checks += ['kpsewhich ' + shlex.quote(style) for style in styles]
        check = ' && '.join(checks)
        result = self.remote_exec(check, 30)
        diagnostics = [result.get('text', '')]
        if result['returncode'] != 0:
            self.owner.service.records.append_log(*self.owner.key,
                'PDF: đang chuẩn bị compiler và packages TeX trong phiên Kaggle…\n', 'backend')
            # Keep package inventory out of the live log. Installation remains
            # foreground work in this same terminal, bounded by the run deadline.
            command = ('command -v apt-get >/dev/null && '
                'export DEBIAN_FRONTEND=noninteractive && '
                'apt-get update -qq >/tmp/ai-scientist-tex-install.log 2>&1 && '
                'apt-get install -y --no-install-recommends ' + shlex.join(packages) +
                ' >>/tmp/ai-scientist-tex-install.log 2>&1; '
                'tex_status=$?; if [ "$tex_status" -ne 0 ]; then '
                'tail -n 20 /tmp/ai-scientist-tex-install.log; exit "$tex_status"; fi; ' + check)
            result = self.remote_exec(command, 360)
            diagnostics.append(result.get('text', ''))
        (self.root / 'tex-bootstrap.log').write_text('\n'.join(diagnostics), encoding='utf-8')
        if result['returncode'] != 0:
            raise RuntimeError('Không chuẩn bị được TeX trong Kaggle; xem research/tex-bootstrap.log')

    def compile_draft(self, response, local):
        from ai_scientist.perform_icbinb_writeup import compile_latex
        match = re.search(r'```latex\s*(.*?)```',response,re.DOTALL)
        if not match:
            raise ValueError('Writeup chưa trả toàn bộ LaTeX trong latex fence')
        (local/'template.tex').write_text(match.group(1).strip(),encoding='utf-8')
        for path in local.iterdir():
            if path.suffix in {'.tex','.sty','.bst','.bib'}:
                self.send('output/research/latex/' + path.name,path.read_bytes())
        for path in (self.root/'figures').glob('*.png'):
            self.send('output/research/figures/' + path.name,path.read_bytes())
        (local/'template.pdf').unlink(missing_ok=True)
        (self.root/'paper.pdf').unlink(missing_ok=True)
        remote = self.owner.descriptor['remote_directory'] + '/output/research/latex'
        self.remote_exec('cd ' + shlex.quote(remote) + " && rm -f template.pdf references.bib")
        diagnostics = []
        def runner(command, **kwargs):
            if command[0]=='pdflatex':
                command=[*command[:1],'-no-shell-escape',*command[1:]]
                (local/'template.pdf').unlink(missing_ok=True)
            result = self.remote_exec('cd ' + shlex.quote(remote) + ' && ' + shlex.join(command),kwargs['timeout'])
            diagnostics.append(f"{shlex.join(command)}\nReturncode: {result['returncode']}\n{result.get('text','')}")
            manifest = self.collect_remote()
            item = next((item for item in manifest['files'] if item['path']=='output/research/latex/template.pdf'),None)
            if command[0]=='pdflatex' and item and result['returncode']==0:
                shutil.copyfile(self.root/'remote'/item['path'],local/'template.pdf')
            return SimpleNamespace(stdout=result.get('text',''),stderr='',returncode=result['returncode'])
        try:
            compile_latex(str(local),str(self.root/'paper.pdf'),run_command=runner)
        finally:
            (local/'compile.log').write_text('\n\n'.join(diagnostics),encoding='utf-8')

    def review(self):
        from ai_scientist.perform_llm_review import perform_review
        if self.plan.writeup!='none':
            if self.state['components']['writeup']['status']!='completed':
                raise ValueError('Chưa có paper hợp lệ để review')
            from pypdf import PdfReader
            text = '\n'.join(page.extract_text() or '' for page in PdfReader(self.root/'paper.pdf').pages)
        else:
            if self.state['components']['report']['status']!='completed':
                raise ValueError('Chưa có report hợp lệ để review')
            text = (self.root/'report.md').read_text(encoding='utf-8')
        if not text.strip():
            raise ValueError('Tài liệu review không có text')
        review = perform_review(text,self.owner.service.config.codex_model,self.client,
                                num_fs_examples=0,num_reflections=1,num_reviews_ensemble=1)
        if not isinstance(review,dict) or not review:
            raise ValueError('Upstream review chưa trả JSON hợp lệ')
        (self.owner.root/'review_text.txt').write_text(json.dumps(review,ensure_ascii=False,indent=2),encoding='utf-8')
        return ['review_text.txt']

    def run(self, tree_success):
        self.set('tree','completed' if tree_success else 'failed',
                 '' if tree_success else 'Chưa có bản thử thành công ở đủ bốn giai đoạn.',
                 ['logs/0-run/search-state.json','logs/0-run/unified_tree_viz.html'])
        self.step('multi_seed',self.finish_seeds)
        self.step('summary',self.summarize)
        self.step('report',self.report)
        for name,operation in (('plots',self.plots),('writeup',self.writeup)):
            if self.state['components'][name]['status']=='not_requested':
                continue
            if self.state['components']['summary']['status']!='completed':
                self.set(name,'blocked','Cần summary thí nghiệm đã lưu trước khi tạo đầu ra này.')
                self.limitations.append(f'{name} thiếu summary đã xác minh.')
            else:
                self.step(name,operation)
        self.step('review',self.review)
        succeeded = all(item['status'] in {'completed','not_requested'} for item in self.state['components'].values())
        self.state['status'] = 'completed' if succeeded else 'failed'
        self.save()
        return succeeded,self.limitations

    def run_single(self, success):
        """Independent optional outputs for one run; no search or seed nodes."""
        self.set('execution', 'completed' if success else 'failed',
                 '' if success else 'Run chưa thực hiện thành công mục tiêu đã duyệt.', ['execution.json', 'journal.json'])
        self.step('summary', self.summarize)
        # The original plot/PDF readers need their baseline interchange file.
        # A direct node log supplies it without an unrequested summarizer call.
        if (self.plan.plots or self.plan.writeup != 'none') and not self.plan.summary:
            self.state['dependencies'] = {'journal_evidence': {'status': 'running', 'artifacts': []}}
            self.save()
            try:
                from .run_graph import write_run_json
                journal = self.journals()[1]
                write_run_json(self.owner.logs / 'baseline_summary.json',
                               {'best node': self.node_log(journal.nodes[0]), 'best node with different seeds': []})
                self.state['dependencies']['journal_evidence'] = {'status': 'completed', 'artifacts': ['logs/0-run/baseline_summary.json']}
            except Exception as exc:
                self.state['dependencies']['journal_evidence'] = {'status': 'failed', 'reason': str(exc)[:300]}
                self.limitations.append('Thiếu bằng chứng journal cho plots/PDF.')
            self.save()
        self.step('report', self.report)
        for name, operation in (('plots', self.plots), ('writeup', self.writeup)):
            if self.state['components'][name]['status'] == 'not_requested':
                continue
            ready = (self.state['components']['summary']['status'] == 'completed'
                     or self.state.get('dependencies', {}).get('journal_evidence', {}).get('status') == 'completed')
            if ready:
                self.step(name, operation)
            else:
                self.set(name, 'blocked', 'Chưa đủ bằng chứng thí nghiệm để tạo đầu ra này.')
        if self.plan.review and not self.plan.report and self.plan.writeup == 'none':
            # A text review can use the factual execution journal directly.
            from ai_scientist.perform_llm_review import perform_review
            def review_journal():
                text = (self.owner.root / 'memory_journal.json').read_text(encoding='utf-8')
                result = perform_review(text, self.owner.service.config.codex_model, self.client,
                                        num_fs_examples=0, num_reflections=1, num_reviews_ensemble=1)
                if not isinstance(result, dict) or not result:
                    raise ValueError('Review chưa trả JSON hợp lệ')
                (self.owner.root / 'review_text.txt').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
                return ['review_text.txt']
            self.step('review', review_journal)
        else:
            self.step('review', self.review)
        complete = all(item['status'] in {'completed', 'not_requested'} for item in self.state['components'].values())
        self.state['status'] = 'completed' if complete else 'failed'
        self.save()
        return complete, self.limitations
