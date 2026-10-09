"""Extract uploaded documents without executing their contents."""
import hashlib
from io import BytesIO
import json
from pathlib import Path

from .named_paths import folder_title

MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_TEXT_BYTES = 2_000_000
MAX_PAGES = 500
TEXT_SUFFIXES = {'.txt', '.md', '.csv', '.json', '.jsonl', '.yaml', '.yml', '.py', '.rst', '.toml', '.tsv'}


def file_info(name, data):
    return {'path':name, 'bytes':len(data), 'sha256':hashlib.sha256(data).hexdigest()}


def ingest(filename, data):
    if not data:
        raise ValueError('File rỗng; chọn tài liệu có nội dung')
    if len(data) > MAX_FILE_BYTES:
        raise ValueError('File vượt quá 25 MB; dùng dataset reference cho dữ liệu lớn')
    filename = folder_title(filename.replace('\\', '/').rsplit('/', 1)[-1])
    suffix = Path(filename).suffix.lower()
    if not suffix[1:].isalnum() or len(suffix) > 17:
        suffix = ''
    original = 'original' + suffix
    files = {original:data}
    metadata = {'format':1, 'filename':filename, 'original':file_info(original, data),
                'status':'file_reference', 'page_count':None, 'text_pages':0, 'pages':[], 'issues':[]}
    if suffix == '.pdf':
        _pdf(data, metadata, files)
    elif suffix in TEXT_SUFFIXES:
        try:
            encoding = 'utf-16' if data.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig'
            encoded = data.decode(encoding).encode('utf-8')
            truncated = len(encoded) > MAX_TEXT_BYTES
            text = encoded[:MAX_TEXT_BYTES].decode('utf-8', errors='ignore')
            files['text.md'] = text.encode('utf-8')
            metadata['text'] = file_info('text.md', files['text.md'])
            metadata['status'] = 'partial' if truncated else 'extracted' if text.strip() else 'no_text'
            if truncated:
                metadata['issues'].append('Chỉ trích 2 MB text đầu; bản gốc được giữ đầy đủ.')
        except UnicodeError:
            metadata.update(status='error', issues=['Không đọc được encoding; tải bản UTF-8 hoặc UTF-16 lên.'])
    files['ingestion.json'] = json.dumps(metadata, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return 'pdf' if suffix == '.pdf' else 'file', metadata, files


def _pdf(data, metadata, files):
    from pypdf import PdfReader
    try:
        reader = PdfReader(BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(''):
            metadata.update(status='locked', issues=['PDF yêu cầu mật khẩu; tải lên bản đã mở khóa để trích text.'])
            return
        metadata['page_count'] = len(reader.pages)
        text_bytes = 0
        for index, page in enumerate(reader.pages[:MAX_PAGES], 1):
            status, text = 'extracted', ''
            try:
                contents = page.get_contents()
                if contents is not None and len(contents.get_data()) > 8_000_000:
                    raise ValueError('Page content stream is too large')
                text = page.extract_text() or ''
                remaining = max(0, MAX_TEXT_BYTES - text_bytes)
                encoded = text.encode('utf-8')
                if len(encoded) > remaining:
                    text = encoded[:remaining].decode('utf-8', errors='ignore')
                    status = 'partial'
                elif not text.strip():
                    status = 'no_text'
                text_bytes += len(text.encode('utf-8'))
            except Exception:
                status = 'error'
            name = f'pages/page-{index:04d}.md'
            files[name] = (f'# Trang {index}\n\nTrạng thái: {status}\n\n' + text).encode('utf-8')
            metadata['pages'].append({'page':index, 'status':status, **file_info(name, files[name])})
            if text.strip():
                metadata['text_pages'] += 1
        if metadata['page_count'] > MAX_PAGES:
            metadata['issues'].append('Chỉ trích 500 trang đầu; bản gốc được giữ đầy đủ.')
        statuses = {page['status'] for page in metadata['pages']}
        metadata['status'] = ('no_text' if not metadata['text_pages'] and statuses <= {'no_text'}
                              else 'error' if not metadata['text_pages']
                              else 'partial' if statuses != {'extracted'} or metadata['issues'] else 'extracted')
        if 'no_text' in statuses:
            metadata['issues'].append('Có trang không có text; PDF scan cần OCR ở giai đoạn sau.')
        if 'error' in statuses:
            metadata['issues'].append('Có trang trích text lỗi; xem trạng thái theo trang.')
        if 'partial' in statuses:
            metadata['issues'].append('Text vượt 2 MB; phần trích bị giới hạn, bản gốc vẫn đầy đủ.')
    except Exception:
        metadata.update(status='error', issues=['Không đọc được cấu trúc PDF; kiểm tra hoặc tải file khác.'])


def source_summary(metadata):
    lines = [f"File gốc: {metadata['original']['path']}", f"Trạng thái nhập: {metadata['status']}",
             f"SHA256 bản gốc: {metadata['original']['sha256']}", 'Chi tiết trích xuất: ingestion.json']
    if metadata['page_count'] is not None:
        lines += [f"PDF: {metadata['page_count']} trang; {metadata['text_pages']} trang có text.",
                  'Text theo trang: pages/page-NNNN.md (số trang bắt đầu từ 1).']
    if metadata.get('text'):
        lines.append('Text đã trích: text.md')
    origin = metadata.get('provenance')
    if origin:
        lines += [f"Bản sao từ Output: Run {origin['run_id']} · {origin.get('path') or 'nội dung Output'}",
                  f"Proposal: {origin['proposal_id']} v{origin['proposal_version']}",
                  f"Context SHA256: {origin['context_sha256']}",
                  f"Trạng thái run khi copy: {origin['run_state']} · Output {origin['output_status']}",
                  f"Đã xác nhận Kaggle dừng khi copy: {origin['stop_confirmed']}",
                  f"Thời điểm copy: {origin['copied_at']}",
                  *('Giới hạn từ Output: ' + value for value in origin.get('limitations', []))]
    return '\n\n'.join([*lines, *metadata['issues']])
