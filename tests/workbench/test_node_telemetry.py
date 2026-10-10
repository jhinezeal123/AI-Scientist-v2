import json
from ai_scientist.workbench.monitor_store import node_telemetry


def marker(node,stage=1,stream='backend'):
    return {'stream':stream,'text':f'Giai đoạn {stage}_stage_1_test: improve · node {node}\n'}


def sample(value,step=1,elapsed=1):
    return {'stream':'stdout','text':'AILAB_METRIC '+json.dumps({'step':step,'total_steps':2,'elapsed_seconds':elapsed,'metrics':{'mse':value}})+'\n'}


def test_each_node_has_independent_steps_and_completed_selection():
    rows=[marker('a'*32),sample(.1),sample(.05,2,2),marker('b'*32,4),sample(1),sample(2,2,2)]
    active=node_telemetry(rows,'mse')
    assert active['error'] is None and active['node']=='b'*32
    complete=node_telemetry(rows,'mse','a'*32)
    assert complete['error'] is None and complete['points'][-1]['metrics']['mse']==.05
    assert [x['points'][0]['step'] for x in complete['nodes']]==[1,1]


def test_workload_text_cannot_create_a_node_boundary():
    assert node_telemetry([marker('a'*32,stream='stdout'),sample(1)],'mse') is None


def test_duplicate_boundary_cannot_reset_invalid_steps():
    result=node_telemetry([marker('a'*32),sample(1),marker('a'*32),sample(2)],'mse')
    assert result['error'] and len(result['nodes'])==1


def test_invalid_node_remains_visible_when_another_node_is_selected():
    result=node_telemetry([marker('a'*32),sample(1),sample(2),marker('b'*32),sample(.1)],'mse','b'*32)
    assert result['error'] and result['points'][0]['metrics']['mse']==.1


def test_legacy_prefix_and_chunked_frames_keep_exact_metrics():
    frame=sample(.123)['text'];rows=[marker('a'*8),{'stream':'stdout','text':frame[:20]},{'stream':'stdout','text':frame[20:]}]
    result=node_telemetry(rows,'mse','a'*32)
    assert result['error'] is None and result['points'][0]['metrics']['mse']==.123


def test_ambiguous_selected_prefix_fails_closed():
    result=node_telemetry([marker('a'*8),sample(.1),marker('a'*32),sample(.2)],'mse','a'*32)
    assert result['error'] and not result['points']


def test_oversized_unterminated_frame_remains_an_error():
    result=node_telemetry([marker('a'*32),sample(.1),{'stream':'stdout','text':'x'*16385}],'mse')
    assert result['error'] and result['points'][0]['metrics']['mse']==.1
