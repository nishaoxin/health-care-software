import unittest
from app.audio import AudioGate
from app.domain import Context
from app.regression import validate_groups


class RegressionAndAudioTests(unittest.TestCase):
    def test_participant_cannot_cross_splits_even_with_different_recordings(self):
        rows = [{'participant_id': 'a', 'recording_id': '1', 'split': 'development', 'annotation_origin': 'human'},
                {'participant_id': 'a', 'recording_id': '2', 'split': 'acceptance', 'annotation_origin': 'human'}]
        with self.assertRaises(ValueError):
            validate_groups(rows)

    def test_recording_windows_and_augmentations_stay_together(self):
        rows = [{'participant_id': 'a', 'recording_id': '1', 'split': 'development', 'annotation_origin': 'human'},
                {'participant_id': 'b', 'recording_id': '1', 'split': 'acceptance', 'annotation_origin': 'human'}]
        with self.assertRaises(ValueError):
            validate_groups(rows)

    def test_predictions_are_not_ground_truth(self):
        with self.assertRaises(ValueError):
            validate_groups([{'participant_id': 'a', 'recording_id': '1', 'split': 'development', 'annotation_origin': 'prediction'}])

    def test_old_context_and_missing_audio_are_silent(self):
        old = Context(1, 'rehab', 'fixture', 'SYNTHETIC', 'TEST')
        new = Context(2, 'rehab', 'fixture', 'SYNTHETIC', 'TEST')
        audio = AudioGate()
        audio.reset(new)
        self.assertFalse(audio.play(old, 1, 'missing.wav'))
        self.assertFalse(audio.play(new, 1, 'missing.wav'))


if __name__ == '__main__':
    unittest.main()
