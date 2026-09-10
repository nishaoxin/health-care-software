from collections import deque
from dataclasses import replace

import numpy as np
import pytest

from app.camera_manager import CameraManager
from app.domain import Context, DeviceDescriptor, FramePacket
from app.dual_camera import make_dual_source, validate_dual_source, secondary_context, FramePairer, validate_pair


DEVICES = [DeviceDescriptor('same name', 'front-path', 700, 4), DeviceDescriptor('same name', 'side-path', 700, 8)]
REFS = {view: dict(name=d.name, path=d.path, backend=d.backend) for view, d in zip(('frontal', 'sagittal'), DEVICES)}


def context(n=1):
    return Context(n, 'rehab', 'pair-fixture', 'LIVE_CAMERA', 'TEST')


def frame(ctx, seq, t):
    return FramePacket(ctx, seq, t, t, '2026-09-10T10:00:00+00:00', np.zeros((24, 32, 3), np.uint8))


class Worker:
    made = []
    fail_index = None
    fail_release_index = None

    def __init__(self, source, ctx, options):
        self.source, self.context, self.options = source, ctx, options
        self.frames, self.statuses = deque(), deque()
        self.stopped, self.stop_requested, self.stop_calls = False, False, 0
        self.made.append(self)

    def start(self):
        if self.source['index'] == self.fail_index:
            raise RuntimeError('fixture open failed')

    def request_stop(self):
        self.stop_requested = True

    def stop(self):
        self.stop_calls += 1
        if self.source['index'] == self.fail_release_index:
            return False
        self.stopped = True
        return True

    def change_context(self, ctx):
        self.context = ctx

    def read_latest(self):
        return self.frames.popleft() if self.frames else None

    def read_status(self):
        result, self.statuses = list(self.statuses), deque()
        return result


@pytest.fixture
def manager():
    Worker.made = []
    Worker.fail_index = Worker.fail_release_index = None
    m = CameraManager(enumerator=lambda b: DEVICES, worker_factory=Worker)
    yield m
    Worker.fail_release_index = None
    m.stop()


@pytest.mark.parametrize('view,index', [('frontal', 4), ('sagittal', 8)])
def test_two_views_resolve_device_paths_before_open_and_keep_primary_role(manager, view, index):
    manager.open_pair(REFS, view, context())
    assert len(Worker.made) == 2 and manager.resolved.index == index
    assert [w.source['index'] for w in Worker.made] == [4, 8]
    assert all(w.source['backend'] == 700 for w in Worker.made)
    assert manager.worker.workers[view].context == manager.worker.context
    other = 'sagittal' if view == 'frontal' else 'frontal'
    assert manager.worker.workers[other].context == secondary_context(manager.worker.context, other)
    with pytest.raises(RuntimeError):
        manager.open_camera(REFS['frontal'], context(2))


@pytest.mark.parametrize('bad', [dict(REFS, sagittal=REFS['frontal']),
                                dict(REFS, sagittal=dict(REFS['sagittal'], backend=1400)),
                                dict(REFS, sagittal=dict(REFS['sagittal'], path='missing'))])
def test_invalid_or_missing_second_device_never_opens_first(manager, bad):
    with pytest.raises((ValueError, RuntimeError)):
        manager.open_pair(bad, 'frontal', context())
    assert not Worker.made and manager.worker is None


def test_second_start_failure_rolls_back_both_workers(manager):
    Worker.fail_index = 8
    with pytest.raises(RuntimeError, match='fixture open failed'):
        manager.open_pair(REFS, 'frontal', context())
    assert manager.worker is None and all(w.stopped for w in Worker.made)


def test_rollback_release_failure_keeps_owner_locked_until_retry(manager):
    Worker.fail_index, Worker.fail_release_index = 8, 4
    with pytest.raises(RuntimeError):
        manager.open_pair(REFS, 'frontal', context())
    assert manager.worker is not None and Worker.made[1].stopped
    with pytest.raises(RuntimeError):
        manager.open_camera(REFS['sagittal'], context())
    Worker.fail_release_index = None
    manager.stop()
    assert manager.worker is None


def test_stop_requests_both_and_does_not_skip_second_on_first_failure(manager):
    manager.open_pair(REFS, 'frontal', context())
    Worker.fail_release_index = 4
    with pytest.raises(RuntimeError):
        manager.stop()
    assert all(w.stop_requested for w in Worker.made)
    assert Worker.made[1].stopped and manager.worker is not None
    Worker.fail_release_index = None
    manager.stop()
    assert Worker.made[1].stop_calls == 1 and manager.worker is None


def test_pairer_matches_receive_time_without_reuse_and_retains_original_view_times():
    ctx = context()
    p = FramePairer(ctx, 'frontal')
    p.add('frontal', frame(ctx, 1, 10.), now=10.1)
    assert p.take() is None
    p.add('sagittal', frame(secondary_context(ctx, 'sagittal'), 7, 10.04), now=10.1)
    result = p.take()
    assert result.seq == 1 and result.time_s == 10.
    assert result.paired_frame.seq == 7 and result.paired_frame.time_s == 10.04
    assert result.pairing['receive_delta_s'] == pytest.approx(.04)
    assert result.camera_view == 'frontal' and result.paired_frame.camera_view == 'sagittal'
    validate_pair(result, 'frontal', now=10.1)
    assert p.take() is None
    p.add('frontal', frame(ctx, 2, 10.06), now=10.1)
    assert p.take() is None  # The auxiliary frame has already been consumed.


def test_unmatched_old_frames_are_dropped_without_filling_a_missing_view():
    ctx = context()
    p = FramePairer(ctx, 'sagittal')
    p.add('sagittal', frame(ctx, 1, 10.), now=10.1)
    p.add('frontal', frame(secondary_context(ctx, 'frontal'), 1, 10.3), now=10.3)
    assert p.take() is None
    p.add('sagittal', frame(ctx, 2, 10.31), now=10.31)
    pair = p.take()
    assert pair.seq == 2 and pair.paired_frame.seq == 1


@pytest.mark.parametrize('change', [dict(seq=0), dict(time_s=float('nan')), dict(time_s=5.),
                                   dict(received_monotonic=float('inf')), dict(received_monotonic=30.),
                                   dict(context=context(9)), dict(time_basis='media_pts')])
def test_pairer_rejects_bad_duplicate_stale_or_foreign_input(change):
    ctx = context()
    p = FramePairer(ctx, 'frontal')
    p.add('frontal', frame(ctx, 1, 10.), now=10.1)
    p.add('frontal', replace(frame(ctx, 2, 10.1), **change), now=10.2)
    p.add('sagittal', frame(secondary_context(ctx, 'sagittal'), 1, 10.1), now=10.2)
    assert p.take().seq == 1
    assert p.take() is None


def test_context_change_discards_both_old_buffers_and_worker_callbacks(manager):
    ctx = context()
    manager.open_pair(REFS, 'frontal', ctx)
    pair = manager.worker
    pair.workers['frontal'].frames.append(frame(ctx, 1, 10.))
    pair.pairer.add('frontal', frame(ctx, 1, 10.), now=10.1)
    new = context(2)
    manager.change_context(new)
    assert pair.pairer.take() is None
    assert pair.workers['sagittal'].context == secondary_context(new, 'sagittal')
    assert not pair.pairer.add('frontal', frame(ctx, 2, 10.1), now=10.2)


def test_context_change_failure_releases_both_and_diagnostics_do_not_count_inference(manager, monkeypatch):
    ctx = context()
    manager.open_pair(REFS, 'frontal', ctx)
    pair = manager.worker
    pair.pairer.add('frontal', frame(ctx, 1, 10.), now=10.1)
    info = pair.diagnostics()
    assert info['received_by_pairer'] == {'frontal': 1, 'sagittal': 0}
    assert info['emitted_pairs'] == 0 and info['still_buffered']['frontal'] == 1
    def fail(_):
        raise RuntimeError('fixture context failure')
    monkeypatch.setattr(pair.workers['sagittal'], 'change_context', fail)
    with pytest.raises(RuntimeError, match='fixture context failure'):
        manager.change_context(context(2))
    assert manager.worker is None and all(w.stopped for w in Worker.made)


def test_each_camera_error_is_identified_and_opened_diagnostics_keep_both_views(manager):
    manager.open_pair(REFS, 'frontal', context())
    workers = manager.worker.workers
    workers['frontal'].statuses.append(dict(status='OPENED', reported_fps=30.))
    assert not any(s['status'] == 'OPENED' for s in manager.worker.read_status())
    workers['sagittal'].statuses.append(dict(status='OPENED', reported_fps=15.))
    reports = manager.worker.read_status()
    opened = next(s for s in reports if s['status'] == 'OPENED')
    assert opened['streams']['frontal']['reported_fps'] == 30.
    assert opened['streams']['sagittal']['reported_fps'] == 15.
    workers['sagittal'].statuses.append(dict(status='ERROR', message='fixture disconnected'))
    error = next(s for s in manager.worker.read_status() if s['status'] == 'ERROR')
    assert error['view'] == 'sagittal' and '侧面' in error['message']


def test_source_identity_tracks_roles_and_backend_but_not_device_names_or_current_indexes():
    a = make_dual_source(REFS, 'frontal', 'TEST')
    renamed = {k: dict(v, name='renamed', index=99) for k, v in REFS.items()}
    assert a['ref'] == make_dual_source(renamed, 'frontal', 'TEST')['ref']
    assert a['ref'] != make_dual_source(REFS, 'sagittal', 'TEST')['ref']
    validate_dual_source(a, 'frontal')
    with pytest.raises(ValueError):
        validate_dual_source(a, 'sagittal')
    with pytest.raises(ValueError):
        validate_dual_source(dict(a, ref='forged-source'), 'frontal')
    with pytest.raises(ValueError):
        validate_dual_source(dict(a, kind='REPLAY_FILE'), 'frontal')


def test_pair_validation_recomputes_difference_and_rejects_foreign_secondary():
    ctx = context()
    p = FramePairer(ctx, 'frontal')
    p.add('frontal', frame(ctx, 1, 10.), now=10.1)
    p.add('sagittal', frame(secondary_context(ctx, 'sagittal'), 2, 10.05), now=10.1)
    pair = p.take()
    with pytest.raises(ValueError):
        validate_pair(replace(pair, paired_frame=replace(pair.paired_frame, context=ctx)), 'frontal', now=10.1)
    with pytest.raises(ValueError):
        validate_pair(replace(pair, paired_frame=replace(pair.paired_frame, time_s=11., received_monotonic=11.)), 'frontal', now=11.1)
    with pytest.raises(ValueError):
        validate_pair(pair, 'frontal', now=14.)
