import unittest

from core.gesture_engine.gesture_arbiter import GestureArbiter


class GestureArbiterTests(unittest.TestCase):
    def test_prefers_configured_gesture_inside_conflict_group(self):
        arbiter = GestureArbiter(activation_frames=1)
        gestures = {
            "has_face": True,
            "calibrating": False,
            "calibration_progress": 1.0,
            "smile": True,
            "smile_right": True,
            "smile_left": False,
        }

        filtered = arbiter.filter(
            gestures,
            action_resolver=lambda name: {"type": "key_hold", "keys": ["right"]} if name == "smile_right" else None,
        )

        self.assertTrue(filtered["smile_right"])
        self.assertFalse(filtered["smile"])

    def test_allows_only_one_mouth_gesture(self):
        arbiter = GestureArbiter(activation_frames=1)
        gestures = {
            "has_face": True,
            "calibrating": False,
            "calibration_progress": 1.0,
            "mouth_open": True,
            "mouth_o": True,
            "mouth_pucker": False,
        }

        filtered = arbiter.filter(gestures)

        self.assertTrue(filtered["mouth_o"])
        self.assertFalse(filtered["mouth_open"])

    def test_delays_normal_gesture_until_stable(self):
        arbiter = GestureArbiter(activation_frames=2)
        gestures = {
            "has_face": True,
            "calibrating": False,
            "calibration_progress": 1.0,
            "eye_wide": True,
            "eye_blink": False,
        }

        first = arbiter.filter(gestures)
        second = arbiter.filter(gestures)

        self.assertFalse(first["eye_wide"])
        self.assertTrue(second["eye_wide"])

    def test_hold_gesture_can_activate_without_extra_delay(self):
        arbiter = GestureArbiter(activation_frames=2, hold_activation_frames=1)
        gestures = {
            "has_face": True,
            "calibrating": False,
            "calibration_progress": 1.0,
            "smile_right": True,
            "smile_left": False,
            "smile": False,
        }

        filtered = arbiter.filter(
            gestures,
            action_resolver=lambda name: {"type": "key_hold", "keys": ["right"]} if name == "smile_right" else None,
        )

        self.assertTrue(filtered["smile_right"])

    def test_normal_gesture_survives_one_missing_frame(self):
        arbiter = GestureArbiter(activation_frames=1, release_frames=2)
        active = {
            "has_face": True,
            "calibrating": False,
            "calibration_progress": 1.0,
            "eye_wide": True,
            "eye_blink": False,
        }
        missing = dict(active)
        missing["eye_wide"] = False

        self.assertTrue(arbiter.filter(active)["eye_wide"])
        self.assertTrue(arbiter.filter(missing)["eye_wide"])
        self.assertFalse(arbiter.filter(missing)["eye_wide"])

    def test_switch_inside_group_waits_for_stability(self):
        arbiter = GestureArbiter(activation_frames=2, release_frames=2)
        right = {
            "has_face": True,
            "calibrating": False,
            "calibration_progress": 1.0,
            "smile_right": True,
            "smile_left": False,
            "smile": False,
        }
        left = dict(right)
        left["smile_right"] = False
        left["smile_left"] = True

        arbiter.filter(right)
        self.assertTrue(arbiter.filter(right)["smile_right"])

        first_left = arbiter.filter(left)
        second_left = arbiter.filter(left)

        self.assertTrue(first_left["smile_right"])
        self.assertFalse(first_left["smile_left"])
        self.assertFalse(second_left["smile_right"])
        self.assertTrue(second_left["smile_left"])

    def test_activation_override_by_gesture(self):
        arbiter = GestureArbiter(activation_frames=1, activation_frames_by_gesture={"mouth_o": 3})
        gestures = {
            "has_face": True,
            "calibrating": False,
            "calibration_progress": 1.0,
            "mouth_o": True,
            "mouth_open": False,
            "mouth_pucker": False,
        }

        first = arbiter.filter(gestures)
        second = arbiter.filter(gestures)
        third = arbiter.filter(gestures)

        self.assertFalse(first["mouth_o"])
        self.assertFalse(second["mouth_o"])
        self.assertTrue(third["mouth_o"])

    def test_from_config_reads_priorities_and_frame_overrides(self):
        arbiter = GestureArbiter.from_config(
            {
                "gesture_arbitration": {
                    "activation_frames": 1,
                    "release_frames": 1,
                    "activation_frames_by_gesture": {"mouth_o": 4},
                    "release_frames_by_gesture": {"mouth_o": 3},
                    "priorities": {"mouth_open": 99},
                }
            }
        )

        self.assertEqual(arbiter.activation_frames_by_gesture["mouth_o"], 4)
        self.assertEqual(arbiter.release_frames_by_gesture["mouth_o"], 3)
        self.assertEqual(arbiter.priorities["mouth_open"], 99)

    def test_debug_records_candidates_and_rejections(self):
        arbiter = GestureArbiter(activation_frames=1)
        gestures = {
            "has_face": True,
            "calibrating": False,
            "calibration_progress": 1.0,
            "mouth_open": True,
            "mouth_o": True,
            "mouth_pucker": False,
        }

        arbiter.filter(gestures)
        debug = arbiter.last_debug
        mouth_debug = debug["groups"]["mouth"]

        self.assertEqual(debug["raw_active"], ["mouth_open", "mouth_o"])
        self.assertEqual(mouth_debug["candidate"], "mouth_o")
        self.assertEqual(mouth_debug["active"], "mouth_o")
        self.assertIn("mouth_open", mouth_debug["rejected"])

    def test_debug_marks_waiting_candidate_before_activation(self):
        arbiter = GestureArbiter(activation_frames=3)
        gestures = {
            "has_face": True,
            "calibrating": False,
            "calibration_progress": 1.0,
            "eye_wide": True,
            "eye_blink": False,
        }

        filtered = arbiter.filter(gestures)
        eye_debug = arbiter.last_debug["groups"]["eyes"]

        self.assertFalse(filtered["eye_wide"])
        self.assertEqual(eye_debug["candidate"], "eye_wide")
        self.assertIsNone(eye_debug["active"])
        self.assertEqual(eye_debug["candidate_frames"], 1)
        self.assertEqual(eye_debug["required_activation_frames"], 3)

    def test_score_confidence_breaks_ties_inside_group(self):
        arbiter = GestureArbiter(activation_frames=1)
        gestures = {
            "has_face": True,
            "calibrating": False,
            "calibration_progress": 1.0,
            "mouth_open": True,
            "mouth_o": True,
            "gesture_scores": {
                "mouth_open": {"confidence": 0.95, "margin": 0.4, "score": 1.4},
                "mouth_o": {"confidence": 0.2, "margin": -0.2, "score": 0.8},
            },
        }

        filtered = arbiter.filter(gestures)

        self.assertTrue(filtered["mouth_open"])
        self.assertFalse(filtered["mouth_o"])
        self.assertEqual(arbiter.last_debug["groups"]["mouth"]["candidate"], "mouth_open")
        self.assertEqual(arbiter.last_debug["groups"]["mouth"]["scores"]["mouth_open"]["confidence"], 0.95)


if __name__ == "__main__":
    unittest.main()
