"""Compatibility launcher; Kaggle implementation is owned by the donor repository."""
import json
from pathlib import Path
import subprocess
import sys


def main():
    root = Path(__file__).resolve().parents[2]
    config_path = root / '.workbench/config.local.json'
    config = json.loads(config_path.read_text(encoding='utf-8'))
    args = sys.argv[1:]
    if 'probe' in args:
        raise SystemExit('Use the persistent SSH terminal for workloads; the experiment probe was retired.')
    if '--config' not in args:
        args += ['--config', str(config_path)]
    if '--state-root' not in args:
        args += ['--state-root', str(root / '.workbench/tailcat-poc')]
    result = subprocess.run([config['donor_python'], '-m', 'interface_ai_scientist', *args],
                            cwd=config['donor_root'])
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
