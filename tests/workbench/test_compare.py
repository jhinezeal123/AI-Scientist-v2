from ai_scientist.workbench.compare import compare_runs


def _working(split_b=None):
    class Store:
        def approved_snapshot(self, project, run):
            return {'body': {'data_refs': ['data'], 'split': split_b if run == 'b' and split_b else {'seed': 42},
                             'metric': {'name': 'accuracy', 'direction': 'maximize'}},
                    'snapshot': {'resources': [{'id': 'data', 'version': 1, 'content_sha256': 'abc'}]}}

    class Working:
        store = Store()

        def detail(self, project, run):
            return {'title': run, 'purpose': run, 'state': 'COMPLETED', 'account': run + '.txt',
                    'mode': 'training_research', 'variant': None, 'parent_run_id': None,
                    'result_metric': {'name': 'accuracy', 'direction': 'maximize',
                                      'final_value': 0.9 if run == 'a' else 0.8}}

    return Working()


def test_rank_only_matching_approved_protocol():
    same = compare_runs(_working(), 'project', ['a', 'b'])
    assert same['same_protocol'] and same['ranked_run_ids'] == ['a', 'b']
    changed = compare_runs(_working({'seed': 7}), 'project', ['a', 'b'])
    assert not changed['same_protocol'] and not changed['ranked_run_ids']
    assert any('split' in warning for warning in changed['warnings'])


def test_missing_protocol_or_wrong_result_metric_never_ranks():
    working = _working()
    original = working.store.approved_snapshot
    working.store.approved_snapshot = lambda project, run: {**original(project, run),
        'body': {**original(project, run)['body'], 'split': None}}
    assert not compare_runs(working, 'project', ['a', 'b'])['ranked_run_ids']
    working = _working()
    detail = working.detail
    working.detail = lambda project, run: {**detail(project, run),
        'result_metric': {'name': 'unapproved', 'direction': 'maximize', 'final_value': 1}}
    assert not compare_runs(working, 'project', ['a', 'b'])['ranked_run_ids']



def test_budget_difference_is_advisory(monkeypatch):
    from ai_scientist.workbench import compare
    monkeypatch.delenv("AI_SCIENTIST_MLFLOW_TRACKING_URI", raising=False)
    working = _working()
    original = working.store.approved_snapshot

    def differing_budget(project, run):
        result = original(project, run)
        result["body"]["budget"] = {"training_seconds": 60 if run == "a" else 120}
        return result

    working.store.approved_snapshot = differing_budget
    result = compare.compare_runs(working, "project", ["a", "b"])
    assert result["same_protocol"]
    assert result["ranked_run_ids"] == ["a", "b"]
    assert any("training_seconds" in item for item in result["fairness_warnings"])
    assert result["tracking_backend"] == "workbench"
