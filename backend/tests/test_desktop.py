import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from desktop import DesktopServices


class DesktopTests(unittest.TestCase):
    def test_clipboard_uses_os_adapter(self):
        clipboard = Mock()
        clipboard.paste.return_value = 'https://youtu.be/example'
        with patch.dict(sys.modules, {'pyperclip': clipboard}):
            desktop = DesktopServices()
            self.assertEqual(desktop.read_clipboard(), 'https://youtu.be/example')
            desktop.write_clipboard('copied')
            clipboard.copy.assert_called_once_with('copied')

    def test_windows_folder_dispatch(self):
        with tempfile.TemporaryDirectory() as folder:
            # Build the concrete path before mocking os.name (Path chooses its
            # implementation from os.name and WindowsPath cannot run on macOS).
            directory = Path(folder)
            with patch('desktop.Path', return_value=directory), patch('desktop.os.name', 'nt'), patch('desktop.os.startfile', create=True) as start:
                DesktopServices().open_folder(folder)
                start.assert_called_once_with(folder)

    def test_missing_folder_reports_actionable_error(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, '이동하거나 삭제'):
                DesktopServices().open_folder(str(Path(folder) / 'missing'))

    def test_unsigned_macos_does_not_initialize_native_notifier(self):
        with patch('desktop.platform.system', return_value='Darwin'), patch('desktop.sys.frozen', False, create=True):
            service = DesktopServices()
            with self.assertRaisesRegex(ValueError, '시스템 알림'):
                service.enable_notifications()
            self.assertIn('서명된', service.notification_error)


if __name__ == '__main__':
    unittest.main()
