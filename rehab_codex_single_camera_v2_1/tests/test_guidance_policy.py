from app.guidance import GuidancePolicy
from app.settings import default_setup


def frame(valid=True, **extra):
    return dict(state='ONLINE', context='one', observation_status='VALID' if valid else 'UNKNOWN',
                current_measurement_valid=valid, adjustment='请调整侧面取景，让左髋也进入画面。',
                summary={'phase': 'RAISING'}, **extra)


def test_transient_data_never_keeps_inferred_phase_and_does_not_interrupt():
    policy = GuidancePolicy()
    plan = default_setup(exercise='neck_flexion')['plan']
    policy.render(frame(), plan, now=0)
    bad = policy.render(frame(False), plan, now=.1)
    assert bad['level'] == 'status'
    assert bad['status'] == '正在重新识别，当前不计次'
    assert bad['phase'] is None
    assert not bad['measurement_valid']
    assert '暂停' not in bad['instruction']
    assert policy.render(frame(False), plan, now=1.59)['level'] == 'status'
    assert policy.render(frame(False), plan, now=1.6)['instruction'] == '请调整侧面取景，让左髋也进入画面。'
    recovered = policy.render(frame(), plan, now=1.7)
    assert recovered['level'] == 'action'
    assert '髋' not in recovered['instruction']
    assert recovered['measurement_valid']


def test_fluctuations_context_and_critical_priority():
    policy = GuidancePolicy()
    plan = default_setup()['plan']
    for i in range(12):
        assert policy.render(frame(i % 2 == 0), plan, now=i*.2)['level'] != 'adjust'
    policy.render(frame(False), plan, now=5)
    fresh = frame(False)
    fresh['context'] = 'new'
    assert policy.render(fresh, plan, now=8)['level'] == 'status'
    multi = frame(False)
    multi['observation_status'] = 'MULTI_PERSON'
    assert policy.render(multi, plan, now=8.1)['level'] == 'critical'
    failed = frame(False)
    failed['state'] = 'SAVE_FAILED'
    failed['summary'] = {'training': {'stage': 'RESTING'}}
    assert policy.render(failed, plan, now=8.2)['recovery'] == 'save'


def test_auxiliary_missing_does_not_claim_no_count_and_errors_never_use_phase():
    policy = GuidancePolicy()
    plan = default_setup()['plan']
    g = policy.render(frame(auxiliary_missing=True), plan, now=0)
    assert g['measurement_valid'] and g['level'] == 'action'
    assert '不计次' not in g['status']
    g = policy.render(frame(error='设备断开'), plan, now=.1)
    assert g['level'] == 'critical' and g['phase'] is None


def test_completed_adjustment_can_advance_to_next_missing_point_without_chattering():
    policy, plan = GuidancePolicy(), default_setup()['plan']
    first = frame(False)
    policy.render(first, plan, now=0)
    assert policy.render(first, plan, now=1.5)['instruction'] == first['adjustment']
    second = frame(False)
    second['adjustment'] = '请让左肘也进入画面。'
    assert policy.render(second, plan, now=2)['instruction'] == first['adjustment']
    assert policy.render(second, plan, now=2.61)['instruction'] == second['adjustment']
    assert policy.render(frame(), plan, now=2.7)['level'] == 'action'
