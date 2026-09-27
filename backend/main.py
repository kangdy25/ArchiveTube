"""Desktop entry point and the JSON bridge used by Vue."""
import functools
import json
import os
import queue
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import webview

from desktop import DesktopServices
from jobs import JobManager
from media import MediaService
from models import ACTIVE, error_message, safe_error
from runtime import resource_path
from store import Store


def bridge(method):
    @functools.wraps(method)
    def wrapped(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except Exception as error:
            return {'success': False, 'error': error_message(error), 'detail': safe_error(error)}
    return wrapped


class BackendApi:
    def __init__(self, database=None, runner=None, media=None, desktop=None, autostart=True):
        if database is None:
            from platformdirs import user_data_dir
            database = Path(user_data_dir('ArchiveTube', appauthor=False)) / 'archive.db'
        self.window = None
        self.events = queue.Queue(maxsize=1)
        self.desktop = desktop or DesktopServices()
        self.media = media or MediaService()
        self.store = Store(database)
        self.manager = JobManager(self.store, runner, self._queue_event, self._notify, autostart)
        self._closed = False
        self._closing = False

    def _queue_event(self, snapshot):
        try:
            self.events.put_nowait(snapshot)
        except queue.Full:
            try:
                self.events.get_nowait()
            except queue.Empty:
                pass
            try:
                self.events.put_nowait(snapshot)
            except queue.Full:
                pass

    def _notify(self, summary):
        if self.manager.settings['notifications']:
            self.desktop.notify(summary)

    def dispatch_events(self):
        while not self._closed:
            try:
                snapshot = self.events.get(timeout=0.5)
            except queue.Empty:
                continue
            if self.window:
                try:
                    payload = json.dumps(snapshot, ensure_ascii=False)
                    self.window.evaluate_js(f'window.archiveStateChanged?.({payload})')
                except Exception:
                    pass

    @bridge
    def get_state(self):
        return {**self.manager.snapshot(), 'capabilities': self.desktop.capabilities()}

    @bridge
    def get_settings(self):
        return {'success': True, 'settings': self.manager.snapshot()['settings']}

    @bridge
    def get_info(self, url):
        return self.media.get_info(url, self.manager.snapshot()['settings'])

    @bridge
    def save_settings(self, values):
        if values.get('notifications') and not self.manager.settings['notifications']:
            self.desktop.enable_notifications()
        return {'success': True, 'settings': self.manager.save_settings(values)}

    @bridge
    def choose_folder(self):
        if not self.window:
            raise ValueError('데스크톱 앱에서 폴더를 선택하세요.')
        chosen = self.window.create_file_dialog(webview.FileDialog.FOLDER, directory=self.manager.settings['download_dir'])
        return {'success': True, 'path': chosen[0] if chosen else None}

    @bridge
    def enqueue_downloads(self, requests):
        return {'success': True, 'job_ids': self.manager.enqueue(requests)}

    @bridge
    def download(self, url, format_type='video', scope=None, playlist_items=None, options=None):
        info = self.media.get_info(url, self.manager.snapshot()['settings'])
        scope = scope or ('playlist' if info.get('is_playlist') else 'single')
        if scope == 'playlist':
            entries = [entry for entry in info.get('entries', []) if entry['is_available']
                       and (playlist_items is None or entry['index'] in playlist_items)]
        else:
            info = info.get('current_video', info)
            entries = [info]
        ids = self.manager.enqueue([{'url': info['url'], 'title': info['title'], 'scope': scope,
                                     'items': entries, 'options': {**(options or {}), 'format_type': format_type}}])
        return {'success': True, 'job_id': ids[0]}

    @bridge
    def cancel_download(self, job_id):
        self.manager.cancel_job(job_id)
        return {'success': True}

    @bridge
    def retry_download(self, job_id, all_items=False):
        ids = self.manager.retry(job_id, all_items)
        return {'success': True, 'job_id': ids[0]}

    @bridge
    def pause_queue(self):
        self.manager.pause()
        return {'success': True}

    @bridge
    def resume_queue(self):
        self.manager.resume()
        return {'success': True}

    @bridge
    def reorder_queue(self, job_ids):
        self.manager.reorder(job_ids)
        return {'success': True}

    @bridge
    def delete_job(self, job_id):
        self.manager.delete(job_id)
        return {'success': True}

    @bridge
    def get_history(self, query='', status='all'):
        return {'success': True, 'jobs': self.manager.history(query, status)}

    @bridge
    def open_folder(self, job_id=None):
        if job_id:
            with self.manager.lock:
                job = self.manager.jobs[job_id]
                path = next((i.get('path') for i in job['items'] if i.get('path')), None)
                if path:
                    directory = str(Path(path).parent)
                elif job['scope'] == 'playlist':
                    from models import safe_name
                    directory = str(Path(job['options']['download_dir']) / safe_name(job['title']))
                else:
                    directory = job['options']['download_dir']
        else:
            directory = self.manager.settings['download_dir']
        self.desktop.open_folder(directory)
        return {'success': True}

    @bridge
    def read_clipboard(self):
        return {'success': True, 'text': self.desktop.read_clipboard()}

    @bridge
    def copy_text(self, text):
        if not isinstance(text, str) or len(text) > 1_000_000:
            raise ValueError('복사할 텍스트가 올바르지 않습니다.')
        self.desktop.write_clipboard(text)
        return {'success': True}

    def on_closing(self):
        if self._closed:
            return True
        if self._closing:
            return False
        active = any(j['status'] in ACTIVE for j in self.manager.snapshot()['jobs'])
        if active and not self.window.create_confirmation_dialog(
            '작업을 중단하고 종료할까요?',
            '진행 중인 변환은 마친 뒤 종료합니다. 미완료 작업과 대기열은 저장되며 다음 실행에서 재개할 수 있습니다.',
        ):
            return False
        self._closing = True

        def finish():
            self.manager.shutdown()
            self.store.close()
            self._closed = True
            self.window.destroy()

        threading.Thread(target=finish, daemon=True).start()
        return False


def main():
    if '--check-notifications' in sys.argv:
        return check_notifications()
    api = BackendApi(database=os.environ.get('ARCHIVETUBE_DATABASE'))
    production = getattr(sys, 'frozen', False) or '--prod' in sys.argv
    url = resource_path('frontend/dist/index.html') if production else 'http://localhost:5173'
    api.window = webview.create_window('ArchiveTube', url=url, js_api=api, width=1100, height=800,
                                       min_size=(720, 600), background_color='#0b1020', text_select=True)
    api.window.events.closing += api.on_closing
    webview.start(api.dispatch_events, debug=not production)


def check_notifications():
    """Explicit, isolated native diagnostic: no user DB, cookies or downloads."""
    desktop = DesktopServices()
    result = {'success': False}
    window = webview.create_window('ArchiveTube · 알림 검증', html='<html lang="ko"><body><h1>시스템 알림 검증</h1><p>OS 알림 권한 요청을 확인하세요. 검증 후 이 창은 닫힙니다.</p></body></html>', width=600, height=300)

    def run():
        try:
            desktop.enable_notifications()
            desktop.notify({'completed': 1, 'failed': 0})
            if desktop.notification_error:
                raise RuntimeError(desktop.notification_error)
            result['success'] = True
        except Exception as error:
            result['error'] = safe_error(error)
        finally:
            print(json.dumps(result, ensure_ascii=False), flush=True)
            window.destroy()

    webview.start(run)
    return 0 if result['success'] else 1


if __name__ == '__main__':
    sys.exit(main())
