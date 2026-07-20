import unittest

from vision.gesture_detection.facial_gestures import FacialGestureDetector, FacialGestureThresholds


class FacialGestureScoresTests(unittest.TestCase):
    def test_detect_includes_scores_for_uncalibrated_and_missing_face(self):
        detector = FacialGestureDetector()

        result = detector.detect(None)

        self.assertIn("gesture_scores", result)
        self.assertIn("mouth_open", result["gesture_scores"])
        self.assertFalse(result["gesture_scores"]["mouth_open"]["active_raw"])

    def test_mouth_open_score_reports_confidence_before_debounce(self):
        detector = FacialGestureDetector(
            thresholds=FacialGestureThresholds(mouth_open=0.6, mouth_funnel=0.5)
        )
        detector._calibrated = True

        result = detector.detect({"blendshapes": {"jawOpen": 0.4, "mouthFunnel": 0.0}})
        score = result["gesture_scores"]["mouth_open"]

        self.assertFalse(result["mouth_open"])
        self.assertTrue(score["active_raw"])
        self.assertGreater(score["score"], 1.0)
        self.assertGreater(score["margin"], 0.0)
        self.assertEqual(score["confidence"], 1.0)

    def test_eye_blink_min_delta_uses_eye_metrics(self):
        detector = FacialGestureDetector(thresholds=FacialGestureThresholds(eye_blink=0.2))
        detector._calibrated = True

        result = None
        for _ in range(3):
            result = detector.detect({"blendshapes": {"eyeBlinkLeft": 0.3, "eyeBlinkRight": 0.0}})

        self.assertIsNotNone(result)
        self.assertTrue(result["eye_blink"])
        self.assertTrue(result["gesture_scores"]["eye_blink"]["active_raw"])


if __name__ == "__main__":
    unittest.main()
