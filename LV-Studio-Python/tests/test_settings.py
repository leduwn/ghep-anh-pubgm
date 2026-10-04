import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from desktop_support import DesktopApi


class SettingsTests(unittest.TestCase):
    def test_saved_profile_survives_new_app_and_replaces_on_save(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'LOCALAPPDATA': folder}):
            first = DesktopApi('unused.log')
            self.assertIsNone(first.load_settings()['settings'])
            profile = {'version': 1, 'controls': {'bgHeight': '80'}, 'rects': {'normal': [1, 2, 3, 4]}}
            self.assertTrue(first.save_settings(profile)['saved'])
            second = DesktopApi('unused.log')
            self.assertEqual(second.load_settings()['settings'], profile)
            profile['controls']['bgHeight'] = '115'
            second.save_settings(profile)
            self.assertEqual(first.load_settings()['settings']['controls']['bgHeight'], '115')
            self.assertEqual(list((Path(folder) / 'LV-Studio-Python').glob('*.tmp')), [])

    def test_invalid_or_oversized_save_preserves_previous_profile(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'LOCALAPPDATA': folder}):
            api = DesktopApi('unused.log')
            profile = {'version': 1, 'controls': {}, 'rects': {}}
            api.save_settings(profile)
            for bad in [{'version': 2}, {'version': 1, 'extra': 'x' * 66000}]:
                with self.assertRaises(ValueError):
                    api.save_settings(bad)
                self.assertEqual(api.load_settings()['settings'], profile)
