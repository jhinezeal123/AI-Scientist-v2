"""Mode metadata pinned by approval; old snapshots remain byte-for-byte intact."""
from typing import Literal

RunMode = Literal['training_research', 'etc']


def request_settings(mode, desired_output='', *, require_output=False):
    mode = 'training_research' if mode is None else mode
    if mode not in {'training_research', 'etc'}:
        raise ValueError('Mode phải là Training/Research hoặc Etc')
    if not isinstance(desired_output, str) or len(desired_output) > 20_000:
        raise ValueError('Mô tả đầu ra phải là text, tối đa 20.000 ký tự')
    desired_output = desired_output.strip()
    if require_output and mode == 'etc' and not desired_output:
        raise ValueError('Etc cần mô tả đầu ra mong muốn trước khi lập hoặc duyệt proposal')
    return mode, desired_output


def snapshot_settings(snapshot, *, require_output=False):
    idea = snapshot['idea']
    return request_settings(idea.get('mode'), idea.get('desired_output', ''), require_output=require_output)


def mode_metadata(snapshot):
    mode, desired_output = snapshot_settings(snapshot)
    return {'mode': mode, 'desired_output': desired_output, 'mode_legacy': 'mode' not in snapshot['idea']}
