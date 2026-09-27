"""OS integration kept outside the downloader and its persistent data."""
import asyncio
import importlib.util
import os
import platform
import subprocess
import sys
import threading
from pathlib import Path
from models import safe_error


class DesktopServices:
    def __init__(self):
        self.loop = None
        self.notifier = None
        self.notification_error = None
        self.notification_lock = threading.Lock()

    def capabilities(self):
        return {'clipboard': importlib.util.find_spec('pyperclip') is not None,
                'notifications': importlib.util.find_spec('desktop_notifier') is not None,
                'platform': platform.system(), 'notification_error': self.notification_error}

    def read_clipboard(self):
        import pyperclip
        return pyperclip.paste()

    def write_clipboard(self, text):
        import pyperclip
        pyperclip.copy(text)

    def open_folder(self, path):
        directory = Path(path)
        if not directory.is_dir():
            raise ValueError('저장 폴더를 찾지 못했습니다. 외부에서 이동하거나 삭제했을 수 있습니다.')
        if os.name == 'nt':
            os.startfile(str(directory))
        else:
            subprocess.Popen(['open' if platform.system() == 'Darwin' else 'xdg-open', str(directory)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _notification_loop(self):
        with self.notification_lock:
            self._start_notification_loop()

    def _start_notification_loop(self):
        if self.loop:
            return
        if platform.system() == 'Darwin' and not getattr(sys, 'frozen', False):
            raise ValueError('macOS 알림은 서명된 ArchiveTube.app에서 사용할 수 있습니다.')
        from desktop_notifier import DesktopNotifier
        self.notifier = DesktopNotifier(app_name='ArchiveTube')
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True, name='ArchiveTube-notifications').start()

    def enable_notifications(self):
        try:
            self._notification_loop()
            # The first request waits for the user's OS permission decision.
            future = asyncio.run_coroutine_threadsafe(self.notifier.request_authorisation(), self.loop)
            try:
                allowed = future.result(timeout=120)
            except TimeoutError:
                future.cancel()
                raise ValueError('알림 권한 요청이 시간 초과되었습니다. OS 알림 요청을 확인한 뒤 다시 저장하세요.')
            if not allowed:
                raise ValueError('시스템 알림 권한이 허용되지 않았습니다. OS 알림 설정을 확인하세요.')
            self.notification_error = None
            return True
        except Exception as error:
            self.notification_error = f'{type(error).__name__}: {safe_error(error)}'
            raise ValueError('시스템 알림을 사용할 수 없습니다. OS 권한과 앱 서명을 확인하세요. ' + self.notification_error) from error

    def notify(self, summary):
        try:
            self._notification_loop()
            asyncio.run_coroutine_threadsafe(self.notifier.send(
                title='ArchiveTube · 대기열 처리 완료',
                message=f"완료 {summary['completed']}개 · 실패 {summary['failed']}개",
            ), self.loop).result(timeout=15)
        except Exception as error:
            self.notification_error = f'{type(error).__name__}: {safe_error(error)}'
