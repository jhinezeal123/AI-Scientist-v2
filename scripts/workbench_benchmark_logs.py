"""Read-only comparison of repeated full pages and cursor deltas on one real run."""
import argparse
import json
from pathlib import Path
import time
import urllib.request


def benchmark(base, project, run, samples=20):
    path = f'{base.rstrip("/")}/api/projects/{project}/runs/{run}'

    def get(suffix):
        started = time.perf_counter()
        with urllib.request.urlopen(path + suffix, timeout=20) as response:
            raw = response.read()
        return json.loads(raw), len(raw), (time.perf_counter() - started) * 1000

    first, _, _ = get('/logs?limit=250')
    cursor = first['next_cursor']
    results = {}
    for name, suffix in [('full_page', '/logs?limit=250'), ('cursor_delta', f'/logs?limit=250&cursor={cursor}')]:
        before, _, _ = get('/collector-stats')
        sizes, times, entries = [], [], 0
        for _ in range(samples):
            value, size, latency = get(suffix)
            sizes.append(size)
            times.append(latency)
            entries += len(value['entries'])
            if name == 'cursor_delta':
                suffix = f'/logs?limit=250&cursor={value["next_cursor"]}'
        after, _, _ = get('/collector-stats')
        upstream = None
        if before.get('provider') is not None and after.get('provider') is not None:
            upstream = {key: after['provider'][key]-before['provider'][key]
                        for key in ('requests', 'request_bytes', 'response_bytes', 'latency_ms')}
        results[name] = {'client_requests': samples, 'client_bytes': sum(sizes),
                         'client_mean_latency_ms': sum(times)/samples, 'returned_entries': entries,
                         'upstream_api_delta': upstream,
                         'upstream_frames_delta': after['upstream_frames']-before['upstream_frames']}
    detail, _, _ = get('')
    return {'project_id': project, 'run_id': run, 'state': detail['state'],
            'account': detail.get('account'), 'initial_cursor': cursor, 'samples': samples,
            'patterns': results, 'scope': 'Same run, sequential cached full-page vs delta reads; '
            'payload bytes exclude HTTP headers/TLS. Does not establish an MVP2 upstream-speed baseline.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8011')
    parser.add_argument('--project', required=True)
    parser.add_argument('--run', required=True)
    parser.add_argument('--samples', type=int, default=20, choices=range(1, 101))
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = benchmark(args.base_url, args.project, args.run, args.samples)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
