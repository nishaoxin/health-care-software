"""Real local model loading from portable project paths; synthetic frames only."""
import shutil
import time

import numpy as np
import pytest

from app.domain import Context, FramePacket
from app.landmark_backend import LandmarkBackend, landmark_python
from app.landmark_schemas import BACKEND_SCHEMAS
from app.settings import ROOT

MODEL_FILES = ('landmarks-manifest.json', 'pose_landmarker_full.task', 'hand_landmarker.task')
READY = landmark_python().is_file() and all((ROOT/'assets/models'/name).is_file() for name in MODEL_FILES)


@pytest.mark.skipif(not READY, reason='Optional verified local runtime/models not prepared')
@pytest.mark.parametrize('folder_name', ['models-ascii', '中文模型目录 with spaces'])
@pytest.mark.parametrize('backend', ['mediapipe_pose', 'mediapipe_hands', 'mediapipe_wrist'])
def test_models_load_from_ascii_and_unicode_directories(tmp_path, folder_name, backend):
    folder = tmp_path/folder_name
    folder.mkdir()
    for name in MODEL_FILES:
        shutil.copyfile(ROOT/'assets/models'/name, folder/name)
    context = Context(1, 'rehab', 'synthetic-model-path-check', 'SYNTHETIC', 'TEST')
    packet = FramePacket(context, 1, 0., time.monotonic(), '', np.zeros((480, 640, 3), dtype=np.uint8))
    worker = LandmarkBackend(backend, model_dir=folder)
    process = None
    try:
        output = worker.infer(packet)
        process = worker.process
        assert output.schema_id == BACKEND_SCHEMAS[backend]
        assert output.people == []
        assert worker.runtime_version == '1.0.1'
    finally:
        worker.close()
    assert process is not None and process.poll() is not None
