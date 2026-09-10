from dataclasses import replace
from unittest.mock import Mock
import time

import numpy as np
import pytest

from app.domain import Context, FramePacket, PoseFrame, PosePerson
from app.dual_camera import FramePairer, secondary_context
from app.quality import PoseAnalyzer
from app.vision import VisionWorker


def paired_packet():
    ctx = Context(1, 'rehab', 'two-view-fixture', 'SYNTHETIC', 'TEST')
    t = time.monotonic()-.1
    front = FramePacket(ctx, 11, t, t, '', np.zeros((480, 640, 3), np.uint8))
    side = replace(front, context=secondary_context(ctx, 'sagittal'), seq=33, time_s=t+.02, received_monotonic=t+.02)
    p = FramePairer(ctx, 'frontal')
    p.add('frontal', front)
    p.add('sagittal', side)
    return p.take()


def pose(packet):
    points = [[320., 240.] for _ in range(17)]
    points[5], points[6], points[11], points[12] = [220., 150.], [420., 150.], [250., 330.], [390., 330.]
    return PoseFrame(packet.context, packet.seq, packet.time_s, (640, 480),
                     [PosePerson(packet.context.epoch+':1', [180, 60, 460, 440], points, [.99]*17)],
                     model_manifest_id='fixture-model')


def test_paired_inference_uses_separate_backend_instances_and_preserves_both_provenances():
    worker = VisionWorker(start_thread=False)
    worker.secondary_vision = VisionWorker(start_thread=False)
    packet = paired_packet()
    worker.infer = Mock(side_effect=lambda p, backend, side: pose(p))
    worker.secondary_vision.infer = Mock(side_effect=lambda p, backend, side: pose(p))
    try:
        result = worker.infer_pair(packet, backend='mediapipe_wrist', side='right')
        worker.infer.assert_called_once_with(packet, 'mediapipe_wrist', 'right')
        worker.secondary_vision.infer.assert_called_once_with(packet.paired_frame, 'yolo', 'right')
        assert result.context == packet.context and result.paired_pose.context == packet.paired_frame.context
        assert result.seq == 11 and result.paired_pose.seq == 33
        assert result.paired_pose.people[0].track_key != result.people[0].track_key
    finally:
        worker.close()


def test_failed_secondary_is_not_returned_as_successful_primary_only_inference():
    worker = VisionWorker(start_thread=False)
    worker.secondary_vision = VisionWorker(start_thread=False)
    worker.infer = Mock(side_effect=lambda p, backend, side: pose(p))
    worker.secondary_vision.infer = Mock(side_effect=RuntimeError('fixture auxiliary failure'))
    try:
        with pytest.raises(RuntimeError, match='fixture auxiliary failure'):
            worker.infer_pair(paired_packet())
    finally:
        worker.close()


def test_auxiliary_frontal_metrics_do_not_require_or_borrow_primary_eye_ear_points():
    packet = paired_packet()
    frontal = pose(packet)
    for index in (0, 1, 2, 3, 4):
        frontal.people[0].conf[index] = 0.
    observation = PoseAnalyzer(auxiliary_view='frontal').analyze(frontal)
    assert observation.status == 'VALID'
    assert set(observation.metrics) == {'aux_shoulder_line_deg', 'aux_trunk_frontal_deg'}
    assert observation.value('aux_shoulder_line_deg') == pytest.approx(0.)
    assert observation.value('aux_trunk_frontal_deg') == pytest.approx(0.)


def test_auxiliary_sagittal_uses_only_the_selected_hip_and_shoulder():
    packet = paired_packet().paired_frame
    sagittal = pose(packet)
    for index in (6, 12):
        sagittal.people[0].conf[index] = 0.
    observation = PoseAnalyzer(side='left', auxiliary_view='sagittal').analyze(sagittal)
    assert observation.status == 'VALID'
    assert set(observation.metrics) == {'aux_trunk_sagittal_deg'}
    assert observation.value('aux_trunk_sagittal_deg') is not None
    right = PoseAnalyzer(side='right', auxiliary_view='sagittal').analyze(sagittal)
    assert right.status == 'UNKNOWN' and not right.metrics['aux_trunk_sagittal_deg'].valid


def test_auxiliary_metric_missingness_is_independent_and_short_reference_lines_are_unknown():
    frontal = pose(paired_packet())
    frontal.people[0].conf[11] = 0.
    result = PoseAnalyzer(auxiliary_view='frontal').analyze(frontal)
    assert result.value('aux_shoulder_line_deg') == 0. and result.value('aux_trunk_frontal_deg') is None
    frontal.people[0].xy[6] = [221., 150.]
    result = PoseAnalyzer(auxiliary_view='frontal').analyze(frontal)
    assert result.status == 'UNKNOWN' and all(not m.valid for m in result.metrics.values())


def test_single_camera_analyzer_keeps_its_existing_metric_contract():
    result = PoseAnalyzer().analyze(pose(paired_packet()))
    assert not any(key.startswith('aux_') for key in result.metrics)
