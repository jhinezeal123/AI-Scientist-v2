"""MVP1 file Library regressions; all providers and remote terminals are local fixtures."""
import asyncio
import base64
from copy import deepcopy
import hashlib
from io import BytesIO
import json
import shlex
import subprocess
import sys
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, DecodedStreamObject, NameObject
import pytest

from ai_scientist.workbench.api import library_router
from ai_scientist.workbench.ingestion import ingest
from ai_scientist.workbench.library import LibraryFiles
from ai_scientist.workbench.service import PlanningService
from ai_scientist.workbench.ssh_terminal import transfer_library_file
from ai_scientist.workbench.store import ProjectStore, StoreConflict
from ai_scientist.workbench.worker import RuntimeWorker
from test_planning import request_type
from test_working import fixture


def pdf_bytes(texts, password=None):
    writer = PdfWriter()
    for text in texts:
        page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject({NameObject('/Type'):NameObject('/Font'),
                                 NameObject('/Subtype'):NameObject('/Type1'),
                                 NameObject('/BaseFont'):NameObject('/Helvetica')})
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):font})})
        stream = DecodedStreamObject()
        escaped = text.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
        stream.set_data(f'BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET'.encode('ascii'))
        page[NameObject('/Contents')] = stream
    if password:
        writer.encrypt(password)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def paper_plan(source_id):
    return {'needs_clarification':False, 'questions':[], 'paraphrase':'Đọc tài liệu đã chọn',
            'objective':'Tóm tắt hai trang, dẫn đúng trang', 'data_refs':[source_id],
            'implementation_steps':['Đọc text đã trích theo trang', 'Viết tóm tắt có dẫn trang'],
            'expected_outputs':['output/summary.md']}


def test_pdf_text_pages_and_extraction_limits(monkeypatch):
    original = pdf_bytes(['UNIQUE_PAGE_ONE', 'UNIQUE_PAGE_TWO'])
    kind, meta, files = ingest('paper.pdf', original)
    assert kind == 'pdf' and meta['status'] == 'extracted'
    assert meta['page_count'] == meta['text_pages'] == 2
    assert files['original.pdf'] == original
    for index, text in enumerate(['UNIQUE_PAGE_ONE', 'UNIQUE_PAGE_TWO'], 1):
        page = meta['pages'][index-1]
        assert page['page'] == index and page['status'] == 'extracted'
        assert text in files[page['path']].decode()
        assert page['sha256'] == hashlib.sha256(files[page['path']]).hexdigest()
    assert json.loads(files['ingestion.json']) == meta
    monkeypatch.setattr('ai_scientist.workbench.ingestion.MAX_TEXT_BYTES', 8)
    _, limited, files = ingest('paper.pdf', original)
    assert limited['status'] == 'partial' and limited['issues']
    assert files['original.pdf'] == original and b'UNIQUE_PAGE_TWO' not in files['pages/page-0002.md']
    monkeypatch.setattr('ai_scientist.workbench.ingestion.MAX_PAGES', 1)
    _, limited, _ = ingest('paper.pdf', original)
    assert limited['page_count'] == 2 and len(limited['pages']) == 1


@pytest.mark.parametrize('data,status', [(pdf_bytes([''], 'secret'), 'locked'),
                                        (pdf_bytes(['']), 'no_text'), (b'not a PDF', 'error')])
def test_unreadable_pdf_is_retained_with_truthful_status(data, status):
    _, metadata, files = ingest('document.pdf', data)
    assert metadata['status'] == status and metadata['issues']
    assert files['original.pdf'] == data
    assert metadata['text_pages'] == 0
    if status == 'no_text':
        assert metadata['pages'][0]['status'] == 'no_text'


def test_plain_text_and_binary_files_keep_originals(monkeypatch):
    original = 'Nội dung tài liệu'.encode('utf-16')
    kind, meta, files = ingest('../../Tài liệu.txt', original)
    assert kind == 'file' and meta['filename'] == 'Tài liệu.txt'
    assert meta['status'] == 'extracted' and 'Nội dung' in files['text.md'].decode()
    assert files['original.txt'] == original
    _, meta, files = ingest('dataset.bin', b'\x00\xff\x10')
    assert meta['status'] == 'file_reference' and 'text.md' not in files
    _, meta, files = ingest('invalid.txt', b'\xff\x01')
    assert meta['status'] == 'error' and files['original.txt'] == b'\xff\x01'
    with pytest.raises(ValueError, match='rỗng'):
        ingest('empty.txt', b'')
    monkeypatch.setattr('ai_scientist.workbench.ingestion.MAX_FILE_BYTES', 5)
    with pytest.raises(ValueError, match='25 MB'):
        ingest('large.bin', b'123456')


def test_import_version_pinning_project_isolation_and_restart(tmp_path):
    store = ProjectStore(tmp_path/'projects')
    project = store.create_project('Paper')['id']
    other = store.create_project('Competition')['id']
    original = pdf_bytes(['PRIVATE_PAPER_PAGE_ONE', 'PRIVATE_PAPER_PAGE_TWO'])
    source = store.import_file(project, 'Paper title', 'paper.pdf', original)
    assert source['status'] == 'extracted' and source['attachment']['processed_pages'] == 2
    idea = store.save_idea(project, 'Summarize this paper', 'Paper summary')
    context = store.context_snapshot(project, idea['id'], [source['id']])
    frozen = deepcopy(context)
    assert 'PRIVATE_PAPER_PAGE' not in json.dumps(context)
    proposal = store.save_proposal(project, idea['id'], paper_plan(source['id']), context)
    run = store.approve_proposal(project, proposal, 1, context['context_sha256'])
    updated = store.import_file(project, 'Renamed paper', 'new.pdf', pdf_bytes(['NEW_UNAPPROVED_TEXT']), source['id'], 1)
    assert updated['version'] == 2 and updated['content_sha256'] != source['content_sha256']
    assert store.approved_snapshot(project, run['id'])['snapshot'] == frozen['snapshot']
    restarted = ProjectStore(store.root)
    assert restarted.resources(project) == [updated] and restarted.resources(other) == []
    assert restarted.ingestion(project, source['id'], 1)['original']['sha256'] == hashlib.sha256(original).hexdigest()
    staged = tmp_path/'agent'
    restarted.library(project).stage(frozen['snapshot'], staged)
    agent = restarted.library(project).agent_snapshot(frozen['snapshot'])['resources'][0]
    assert agent['file_path'] == 'library/Renamed paper/v1/source.md'
    assert (staged/agent['attachment']['original_file_path']).read_bytes() == original
    assert 'PRIVATE_PAPER_PAGE_ONE' in (staged/agent['file_path']).parent.joinpath('pages/page-0001.md').read_text()
    assert not list(staged.rglob('v2')) and context == frozen
    with pytest.raises(StoreConflict):
        restarted.import_file(project, '', 'another.pdf', original, source['id'], 1)
    with pytest.raises(KeyError):
        restarted.import_file(other, '', 'wrong.pdf', original, source['id'], 2)


def test_import_stales_pending_proposal_and_failed_save_can_retry(tmp_path, monkeypatch):
    store = ProjectStore(tmp_path/'projects')
    project = store.create_project('Paper')['id']
    source = store.import_file(project, '', 'notes.txt', b'first text')
    idea = store.save_idea(project, 'Summarize')
    context = store.context_snapshot(project, idea['id'], [source['id']])
    store.save_proposal(project, idea['id'], paper_plan(source['id']), context)
    writer = store._write_resource
    def fail(*args):
        raise RuntimeError('fixture database failure')
    monkeypatch.setattr(store, '_write_resource', fail)
    with pytest.raises(RuntimeError, match='database failure'):
        store.import_file(project, '', 'notes.txt', b'failed replacement', source['id'], 1)
    assert store.resources(project) == [source]
    assert not store.library(project).source_path(source['id'], 2).parent.exists()
    monkeypatch.setattr(store, '_write_resource', writer)
    store.import_file(project, '', 'notes.txt', b'valid replacement', source['id'], 1)
    assert store.proposals(project)[0]['state'] == 'STALE'
    with pytest.raises(StoreConflict):
        store.approve_proposal(project, store.proposals(project)[0]['id'], 1, context['context_sha256'])
    # Partial disk writes never publish a source version.
    original_write = LibraryFiles._write_version_file
    def fail_page(path, data):
        if path.name == 'page-0001.md':
            raise OSError('fixture disk failure')
        return original_write(path, data)
    monkeypatch.setattr(LibraryFiles, '_write_version_file', staticmethod(fail_page))
    with pytest.raises(OSError, match='disk failure'):
        store.import_file(project, '', 'paper.pdf', pdf_bytes(['new']), source['id'], 2)
    assert not store.library(project).source_path(source['id'], 3).parent.exists()
    assert not list(store.directory(project).rglob('.v*-import-*'))


def test_import_cleanup_cannot_remove_a_project_or_source_folder(tmp_path):
    store = ProjectStore(tmp_path/'projects')
    project = store.create_project('Paper')['id']
    source = store.import_file(project, '', 'notes.txt', b'keep this source')
    library = store.library(project)
    for path in [store.directory(project), store.directory(project)/'library', library.source_path(source['id'], 1).parent.parent,
                 tmp_path/'outside']:
        with pytest.raises(ValueError, match='cleanup path'):
            library.discard_import(path)
    assert store.resources(project) == [source]


@pytest.mark.parametrize('file', ['original.pdf', 'pages/page-0001.md', 'ingestion.json'])
def test_selected_import_rejects_changed_original_page_or_provenance(tmp_path, file):
    store = ProjectStore(tmp_path/'projects')
    project = store.create_project('Paper')['id']
    source = store.import_file(project, '', 'paper.pdf', pdf_bytes(['protected']))
    idea = store.save_idea(project, 'Summarize')
    context = store.context_snapshot(project, idea['id'], [source['id']])
    root = store.library(project).source_path(source['id'], 1).parent
    (root/file).write_bytes(b'changed')
    with pytest.raises(ValueError, match='hash|provenance'):
        list(store.library(project).selected_files(context['snapshot']))


def test_multipart_routes_original_pages_version_and_project_ownership(tmp_path, monkeypatch):
    store = ProjectStore(tmp_path/'projects')
    project = store.create_project('Paper')['id']
    other = store.create_project('Other')['id']
    app = FastAPI()
    app.include_router(library_router(store, tmp_path))
    base = f'/api/projects/{project}'
    original = pdf_bytes(['PAGE_ONE', 'PAGE_TWO'])
    with TestClient(app) as client:
        response = client.post(base+'/resources/import', data={'title':'Document'}, files={'file':('paper.pdf', original, 'application/pdf')})
        assert response.status_code == 201
        source = response.json()
        url = base+f"/library/{source['id']}/versions/1"
        assert client.get(url+'/original').content == original
        assert 'attachment' in client.get(url+'/original').headers['content-disposition']
        assert 'PAGE_TWO' in client.get(url+'/pages/2').text
        assert client.get(url+'/pages/3').status_code == 404
        assert client.get(url+'/text').status_code == 404
        assert client.get(url.replace(project, other)+'/original').status_code == 404
        update = base+f"/resources/{source['id']}/import"
        upload = {'file':('notes.txt', b'Updated text', 'text/plain')}
        assert client.put(update, data={'expected_version':2}, files=upload).status_code == 409
        assert client.put(update.replace(project, other), data={'expected_version':1}, files=upload).status_code == 404
        assert client.put(update, data={'expected_version':1}, files=upload).json()['version'] == 2
        assert 'Updated text' in client.get(url.replace('/versions/1', '/versions/2')+'/text').text
        assert client.get(url+'/original').content == original
        monkeypatch.setattr('ai_scientist.workbench.ingestion.MAX_FILE_BYTES', 10)
        assert client.post(base+'/resources/import', files={'file':('large.bin', b'x'*11)}).status_code == 413
        assert client.post(base+'/resources/import', files={'file':('empty.txt', b'')}).status_code == 422
        path = store.library(project).path(source['attachment']['original_file_path'])
        path.write_bytes(b'tampered')
        assert client.get(url+'/original').status_code == 409


def test_planner_can_read_uploaded_pages_on_demand(tmp_path):
    store = ProjectStore(tmp_path/'projects')
    project = store.create_project('Paper')['id']
    source = store.import_file(project, '', 'paper.pdf', pdf_bytes(['FACT_ON_PAGE_ONE', 'FACT_ON_PAGE_TWO']))
    idea = store.save_idea(project, 'Read the selected paper')
    class Runtime:
        def run(self, request, progress, cancelled):
            context = json.loads(request.prompt.split('UNTRUSTED PROJECT CONTEXT:\n')[1])
            ref = context['resources'][0]
            assert 'FACT_ON_PAGE' not in request.prompt and 'not that you have read it' in request.prompt
            manifest = json.loads((request.workdir/ref['attachment']['manifest_file_path']).read_text())
            root = (request.workdir/ref['file_path']).parent
            assert 'FACT_ON_PAGE_TWO' in (root/manifest['pages'][1]['path']).read_text()
            return SimpleNamespace(text=json.dumps(paper_plan(ref['id'])), files={})
    worker = RuntimeWorker(Runtime(), tmp_path/'worker.json')
    planner = PlanningService(store, SimpleNamespace(request_type=request_type), worker, tmp_path)
    async def check():
        await planner.start(project, idea['id'], [source['id']])
        await planner.task
        assert store.proposals(project)[0]['state'] == 'AWAITING_APPROVAL'
        await planner.close()
        await worker.close(1)
    asyncio.run(check())


def test_working_transfers_imported_original_and_pages_to_same_terminal(tmp_path):
    async def check():
        store, project, old_run, worker, planner, service, runtime, _, donor = fixture(tmp_path)
        with store.connection(project) as connection:
            connection.execute("UPDATE runs SET state='CANCELLED' WHERE id=?", (old_run,))
        original = pdf_bytes(['WORKING_SELECTED_PAGE'])
        source = store.import_file(project, '', 'paper.pdf', original)
        idea = store.save_idea(project, 'Read imported paper')
        context = store.context_snapshot(project, idea['id'], [source['id']])
        proposal = store.save_proposal(project, idea['id'], paper_plan(source['id']), context)
        run = store.approve_proposal(project, proposal, 1, context['context_sha256'])
        await service.start(project, run['id'])
        await service.tasks[project, run['id']]
        assert service.detail(project, run['id'])['state'] == 'COMPLETED'
        assert len(runtime.calls) == len(donor.opens) == 1
        terminal = donor.opens[0][1]
        ref = source['attachment']
        assert terminal.files[ref['original_file_path']] == original
        assert b'WORKING_SELECTED_PAGE' in terminal.files['library/paper/v1/pages/page-0001.md']
        assert terminal.stop_requested and terminal.closed
        await service.close(1)
        await planner.close()
        await worker.close(1)
    asyncio.run(check())


def test_large_library_file_is_chunked_verified_and_not_replayed(tmp_path):
    class Terminal:
        def __init__(self):
            self.writes = []
            self.commands = []
        def request(self, action, **body):
            if action == 'write':
                data = base64.b64decode(body['data'])
                assert len(data) <= 1_000_000
                self.writes.append(len(data))
                path = tmp_path/body['path']
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                return {'bytes':len(data)}
            assert action == 'exec'
            args = shlex.split(body['command'])
            assert args.pop(0) == 'python3'
            self.commands.append(args)
            return {'returncode':subprocess.run([sys.executable, *args], cwd=tmp_path, capture_output=True).returncode}
    terminal = Terminal()
    data = b'Original large PDF bytes\x00' * 110_000
    name = "library/Paper's title/v1/original.pdf"
    transfer_library_file(terminal, name, data)
    assert (tmp_path/name).read_bytes() == data
    assert max(terminal.writes) == 512_000 and len(terminal.commands) == len(terminal.writes)+1
    assert not list(tmp_path.rglob('.transfer-*'))
    class FailedTerminal:
        calls = 0
        def request(self, *args, **kwargs):
            self.calls += 1
            return {'bytes':1}
    failed = FailedTerminal()
    with pytest.raises(ValueError, match='chunk transfer'):
        transfer_library_file(failed, name, data)
    assert failed.calls == 1
