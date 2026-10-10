"""Immutable benchmark reference used by planner tests without provider I/O."""
BENCHMARK_ID = 'b' * 32
DEFINITION = {'metric': {'name': 'EMD', 'direction': 'minimize',
              'definition': 'sample mean of log10 weighted absolute cumulative error'},
              'test_split': '4 validation groups', 'train_split': '20 training groups'}
BENCHMARK = {'id': BENCHMARK_ID, 'run_id': BENCHMARK_ID, 'title': 'Fixture benchmark',
    'definition': DEFINITION, 'dataset': {'handle': 'fixture/benchmark', 'version': 1,
    'url': 'https://www.kaggle.com/datasets/fixture/benchmark', 'visibility': 'public',
    'manifest_sha256': 'a' * 64, 'files': []}}
