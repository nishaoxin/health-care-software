import math
import unittest

from geometry_reference import angle_deg, knee_flexion_projection_deg, normalized_to_pixels, observed_interval_s


class GeometryTests(unittest.TestCase):
    def test_right_angle(self):
        self.assertAlmostEqual(angle_deg((1, 0), (0, 0), (0, 1)), 90.0)

    def test_straight_knee_is_zero_flexion(self):
        self.assertAlmostEqual(knee_flexion_projection_deg((0, 0), (0, 1), (0, 2)), 0.0)

    def test_zero_vector_invalid(self):
        self.assertIsNone(angle_deg((0, 0), (0, 0), (1, 1)))

    def test_nan_invalid(self):
        self.assertIsNone(angle_deg((math.nan, 0), (0, 0), (1, 1)))

    def test_restore_non_square_coordinates(self):
        width, height = 1920, 1080
        pixel = [(1200, 700), (800, 700), (1000, 900)]
        normalized = [(x / width, y / height) for x, y in pixel]
        restored = [normalized_to_pixels(p, width, height) for p in normalized]
        self.assertAlmostEqual(angle_deg(*restored), angle_deg(*pixel), places=10)
        self.assertGreater(abs(angle_deg(*normalized) - angle_deg(*pixel)), 1.0)

    def test_bad_dimensions(self):
        self.assertIsNone(normalized_to_pixels((0.2, 0.3), 0, 1080))

    def test_shoulder_angle_at_shoulder(self):
        hip, shoulder, elbow = (100, 200), (100, 100), (200, 100)
        self.assertAlmostEqual(angle_deg(hip, shoulder, elbow), 90.0)


class ObservationTests(unittest.TestCase):
    def compute(self, start, end, a="STANDING", b="STANDING", **kwargs):
        defaults = dict(same_track=True, previous_valid=True, current_valid=True)
        defaults.update(kwargs)
        return observed_interval_s(start, end, a, b, **defaults)

    def test_valid_duration(self):
        self.assertAlmostEqual(self.compute(0, 0.1), 0.1)

    def test_gap_not_assumed_activity(self):
        self.assertEqual(self.compute(0, 20), 0)

    def test_missing_and_other_person(self):
        self.assertEqual(self.compute(0, 0.1, current_valid=False), 0)
        self.assertEqual(self.compute(0, 0.1, same_track=False), 0)

    def test_changed_state_not_interpolated(self):
        self.assertEqual(self.compute(0, 0.1, "SITTING", "STANDING"), 0)

    def test_repeated_and_reverse_timestamp(self):
        self.assertEqual(self.compute(1, 1), 0)
        self.assertEqual(self.compute(2, 1), 0)

    def test_unknown_never_counts(self):
        self.assertEqual(self.compute(0, 0.1, "UNKNOWN", "UNKNOWN"), 0)


if __name__ == "__main__":
    unittest.main()
