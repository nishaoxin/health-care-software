import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.exercises import EXERCISE_IDS, exercise_spec
from app.exercise_instructions import exercise_instructions, JOINT_LABELS
from app.ui.catalog import ExerciseCatalog


@pytest.fixture(scope='module')
def qt_app():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize('exercise_id', EXERCISE_IDS)
def test_every_action_has_specific_instructions(exercise_id):
    info = exercise_instructions(exercise_id)
    assert info['joint'] in JOINT_LABELS
    assert info['label'] == exercise_spec(exercise_id)['label']
    assert all(info[k] for k in ('position', 'camera', 'start', 'move', 'return', 'count', 'boundary'))
    assert info['measurement_label'] == exercise_spec(exercise_id)['metric_label']
    assert info['clinical_rom'] is False
    assert '正常' not in info['move']


def test_fingers_name_the_actual_joint_not_just_a_fist():
    mcp = exercise_instructions('index_mcp_flexion')
    pip = exercise_instructions('index_pip_flexion')
    dip = exercise_instructions('index_dip_flexion')
    assert '指根' in mcp['move'] and '中间' in pip['move'] and '指尖' in dip['move']
    assert '腕—掌指' in mcp['boundary']
    assert 'MCP' in mcp['search_terms']


def test_directions_and_reverse_start_are_not_interchangeable():
    assert '掌侧' in exercise_instructions('wrist_flexion')['move']
    assert '手背' in exercise_instructions('wrist_extension')['move']
    assert '拇指' in exercise_instructions('wrist_radial_deviation')['move']
    assert '小指' in exercise_instructions('wrist_ulnar_deviation')['move']
    assert '屈肘' in exercise_instructions('elbow_extension')['start']
    assert '站位' in exercise_instructions('sit_to_stand')['count']


def test_catalog_filters_searches_and_emits_real_action(qt_app):
    catalog = ExerciseCatalog()
    catalog.resize(1000, 650)
    catalog.show()
    qt_app.processEvents()
    assert catalog.visible_ids == []
    catalog.select_joint('all')
    assert set(catalog.visible_ids) == set(EXERCISE_IDS)
    catalog.select_joint('wrist')
    assert len(catalog.visible_ids) == 4
    catalog.search.setText('桡偏')
    assert catalog.visible_ids == ['wrist_radial_deviation']
    picked = []
    catalog.exercise_selected.connect(picked.append)
    QTest.mouseClick(catalog.cards['wrist_radial_deviation'].open_button, Qt.MouseButton.LeftButton)
    assert picked == ['wrist_radial_deviation']
    catalog.select_joint('finger')
    catalog.search.setText('食指 DIP')
    assert set(catalog.visible_ids) == {'index_dip_flexion', 'index_dip_extension'}
    catalog.search.setText('不存在的动作')
    assert catalog.visible_ids == []
    assert catalog.empty.isVisible()
    catalog.close()


def test_unknown_action_is_not_presented_as_supported():
    with pytest.raises(ValueError):
        exercise_instructions('neck_rotation')
