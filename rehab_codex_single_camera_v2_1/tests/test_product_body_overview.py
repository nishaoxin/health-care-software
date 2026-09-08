import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtWidgets import QApplication

from app.assessment import build_body_profile
from app.ui.body_overview import BodyOverview


@pytest.fixture(scope='module')
def qt_app():
    return QApplication.instance() or QApplication([])


def sample_profile():
    profile = build_body_profile([], 'layout-test', 'SYNTHETIC', 'TEST')
    profile['items'][0].update(status='ASSESSED', session_id='synthetic-one',
                               motion_range={'min_deg': 0, 'max_deg': 60, 'range_deg': 60},
                               valid_ratio=.8, start_utc='2026-09-08T00:00:00+00:00')
    profile['items'][1].update(status='UNAVAILABLE', session_id='synthetic-two')
    profile['assessed_count'] = 1
    return profile


def test_empty_profile_does_not_fill_screen_with_missing_measurements(qt_app):
    view = BodyOverview()
    view.set_profile(build_body_profile([], 'empty'))
    assert view.table.rowCount() == 0
    assert view.available.value.text() == '0 项'
    assert view.review.value.text() == '0 项'
    assert view.current_item() is None
    view.show_unassessed.setChecked(True)
    assert view.table.rowCount() == 106
    assert all(view.table.item(i, 3).text() == '—' for i in range(106))
    view.close()


def test_unavailable_record_is_not_a_zero_angle_or_a_training_candidate(qt_app):
    view = BodyOverview()
    view.set_profile(sample_profile())
    assert view.table.rowCount() == 2
    assert view.table.item(0, 3).text() == '0.0° – 60.0°'
    assert view.table.item(1, 3).text() == '—'
    view.table.selectRow(1)
    assert view.current_item()['status'] == 'UNAVAILABLE'
    assert '重新评估' in view.selection_hint.text()
    assert view.review.value.text() == '1 项'
    view.close()


def test_filter_clears_selection_and_loading_discards_previous_user(qt_app):
    view = BodyOverview()
    selected = []
    view.item_selected.connect(selected.append)
    view.set_profile(sample_profile())
    assert view.current_item()['session_id'] == 'synthetic-one'
    view.joint.setCurrentIndex(view.joint.findData('finger'))
    assert view.current_item() is None
    assert selected[-1] is None
    view.set_loading()
    assert view.profile is None
    assert view.available.value.text() == '—'
    assert view.table.rowCount() == 0
    view.close()
