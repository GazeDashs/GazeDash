import unittest
import importlib.util
from pathlib import Path


_SETTINGS_STORE_PATH = Path(__file__).resolve().parents[1] / "ui" / "settings_store.py"
_SPEC = importlib.util.spec_from_file_location("settings_store_for_tests", _SETTINGS_STORE_PATH)
settings_store = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(settings_store)
set_profile_gesture_action = settings_store.set_profile_gesture_action


class SettingsStoreActionTests(unittest.TestCase):
    def test_set_profile_gesture_action_can_store_key_hold(self):
        config = {"profiles": {"juego": {"gesture_actions": {}}}}

        updated = set_profile_gesture_action(
            config,
            "juego",
            "smile_right",
            keys=["right"],
            label="Derecha",
            action_type="key_hold",
        )

        action = updated["profiles"]["juego"]["gesture_actions"]["smile_right"]
        self.assertEqual(action["type"], "key_hold")
        self.assertEqual(action["keys"], ["right"])
        self.assertEqual(action["label"], "Derecha")

    def test_set_profile_gesture_action_can_switch_back_to_hotkey(self):
        config = {
            "profiles": {
                "juego": {
                    "gesture_actions": {
                        "smile_right": {
                            "type": "key_hold",
                            "keys": ["right"],
                            "label": "Derecha",
                        }
                    }
                }
            }
        }

        updated = set_profile_gesture_action(
            config,
            "juego",
            "smile_right",
            keys=["right"],
            label="Derecha",
            action_type="hotkey",
        )

        action = updated["profiles"]["juego"]["gesture_actions"]["smile_right"]
        self.assertEqual(action["type"], "hotkey")
        self.assertEqual(action["keys"], ["right"])


if __name__ == "__main__":
    unittest.main()
