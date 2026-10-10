"""Mode metadata pinned by approval; old snapshots remain byte-for-byte intact."""
from typing import Literal

RunMode = Literal['training_research', 'etc', 'benchmark']


def request_settings(mode, desired_output='', *, require_output=False):
    mode = 'training_research' if mode is None else mode
    if mode not in {'training_research', 'etc', 'benchmark'}:
        raise ValueError('Mode pháº£i lÃ  Training/Research hoáº·c Etc')
    if not isinstance(desired_output, str) or len(desired_output) > 20_000:
        raise ValueError('MÃ´ táº£ Ä‘áº§u ra pháº£i lÃ  text, tá»‘i Ä‘a 20.000 kÃ½ tá»±')
    desired_output = desired_output.strip()
    if require_output and mode == 'etc' and not desired_output:
        raise ValueError('Etc cáº§n mÃ´ táº£ Ä‘áº§u ra mong muá»‘n trÆ°á»›c khi láº­p hoáº·c duyá»‡t proposal')
    return mode, desired_output


def snapshot_settings(snapshot, *, require_output=False):
    idea = snapshot['idea']
    return request_settings(idea.get('mode'), idea.get('desired_output', ''), require_output=require_output)


def mode_metadata(snapshot):
    mode, desired_output = snapshot_settings(snapshot)
    return {'mode': mode, 'desired_output': desired_output, 'mode_legacy': 'mode' not in snapshot['idea']}
