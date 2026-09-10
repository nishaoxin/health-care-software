"""Two real local YOLO predictors on blank synthetic images, not human accuracy."""
from dataclasses import replace
from app.dual_camera import secondary_context
from app.vision import VisionWorker
from test_dual_vision import paired_packet


def test_two_local_models_have_independent_trackers_and_both_reset_for_new_context():
    worker = VisionWorker(device='cpu', start_thread=False)
    packet = paired_packet()
    try:
        first = worker.infer_pair(packet)
        aux = worker.secondary_vision
        assert worker.model is not aux.model and worker.model.predictor is not aux.model.predictor
        main_tracker, aux_tracker = worker.model.predictor.trackers[0], aux.model.predictor.trackers[0]
        assert main_tracker is not aux_tracker
        assert not first.people and not first.paired_pose.people
        assert first.model_manifest_id == first.paired_pose.model_manifest_id and len(first.model_manifest_id) == 64
        second = replace(packet, seq=12, time_s=packet.time_s+.1, received_monotonic=packet.time_s+.1,
                         paired_frame=replace(packet.paired_frame, seq=34, time_s=packet.paired_frame.time_s+.1,
                                              received_monotonic=packet.paired_frame.time_s+.1))
        worker.infer_pair(second)
        assert main_tracker.frame_id == 2 and aux_tracker.frame_id == 2
        ctx = replace(packet.context, generation=packet.context.generation+1, epoch='next-epoch')
        new = replace(packet, context=ctx, paired_frame=replace(packet.paired_frame, context=secondary_context(ctx, 'sagittal')))
        worker.infer_pair(new)
        assert main_tracker.frame_id == 1 and aux_tracker.frame_id == 1
        assert worker.context == ctx and aux.context == new.paired_frame.context
    finally:
        assert worker.close()
