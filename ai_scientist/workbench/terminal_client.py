"""Standalone helper copied into the agent workspace; uses only Python stdlib."""
import argparse
import base64
import json
from pathlib import Path
import urllib.error
import urllib.request


def main():
    parser = argparse.ArgumentParser(description='Commands on the already-open Kaggle terminal')
    parser.add_argument('action', choices=('exec', 'read', 'write'))
    parser.add_argument('value', help='Shell command for exec, relative remote path for read/write')
    parser.add_argument('file', nargs='?', help='Local file for write')
    parser.add_argument('--timeout', type=int, default=120)
    args = parser.parse_args()
    access = json.loads(Path(__file__).with_name('terminal-access.json').read_text(encoding='utf-8'))
    body = {'action': args.action}
    if args.action == 'exec':
        body.update(command=args.value, timeout=args.timeout)
    else:
        body['path'] = args.value
        if args.action == 'write':
            if not args.file:
                parser.error('write requires a local file')
            body['data'] = base64.b64encode(Path(args.file).read_bytes()).decode('ascii')
    request = urllib.request.Request(access['url'], data=json.dumps(body).encode(),
        headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + access['token']})
    try:
        with urllib.request.urlopen(request, timeout=args.timeout + 30) as response:
            result = json.load(response)
    except (urllib.error.URLError, TimeoutError):
        raise SystemExit('Kaggle terminal unavailable; the command was not replayed')
    if args.action == 'exec':
        print(result['output'], end='')
        if result.get('output_truncated'):
            print('\n[Output truncated; complete records are in the Run log]')
        raise SystemExit(0 if result['returncode'] == 0 else 1)
    if args.action == 'read':
        print(base64.b64decode(result['data']).decode('utf-8', 'replace'), end='')
    else:
        print(json.dumps({'written_bytes': result['bytes']}))


if __name__ == '__main__':
    main()
