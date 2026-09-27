"""A durable single-worker queue. All state changes are serialized under one lock."""
import copy
import threading
import time
import uuid
from pathlib import Path

from media import DownloadCancelled, DownloadRunner
from models import ACTIVE, ITEM_DONE, TERMINAL, error_message, parse_youtube_url, safe_error, settings_with, video_url


class JobManager:
    def __init__(self, store, runner=None, on_change=None, on_drained=None, autostart=True):
        self.store = store
        self.runner = runner or DownloadRunner()
        self.on_change = on_change or (lambda _snapshot: None)
        self.on_drained = on_drained or (lambda _summary: None)
        self.lock = threading.RLock()
        self.condition = threading.Condition(self.lock)
        self.settings = settings_with(store.get_settings())
        self.jobs = {job['id']: job for job in store.jobs()}
        self.session_id = uuid.uuid4().hex
        self.revision = 0
        self.stopping = False
        self.cancel = threading.Event()
        self.batch_ids = set()
        for job in self.jobs.values():
            if job['status'] in ACTIVE:
                job['status'] = 'interrupted'
                for item in job['items']:
                    if item['status'] == 'running':
                        item.update(status='pending', stage='interrupted', speed=None, eta=None)
                store.save_job(job)
        self.paused = any(job['status'] in {'queued', 'interrupted'} for job in self.jobs.values())
        self.thread = threading.Thread(target=self._worker, name='ArchiveTube-downloads', daemon=True)
        if autostart:
            self.thread.start()

    def snapshot(self):
        with self.lock:
            return copy.deepcopy({
                'success': True, 'session_id': self.session_id, 'revision': self.revision,
                'paused': self.paused, 'settings': self.settings,
                'jobs': sorted(self.jobs.values(), key=lambda j: (j['order'], j['created_at'])),
            })

    def _changed(self, job=None):
        if job:
            job['updated_at'] = time.time()
            self.store.save_job(job)
        self.revision += 1
        # The callback only dispatches JS, never waits for JS to call back into Python.
        self.on_change(self.snapshot())
        self.condition.notify_all()

    def save_settings(self, values):
        with self.condition:
            self.settings = settings_with(values, self.settings)
            self.store.save_settings(self.settings)
            self._changed()
            return copy.deepcopy(self.settings)

    def enqueue(self, requests):
        if not isinstance(requests, list) or not requests or len(requests) > 100:
            raise ValueError('등록할 작업은 1~100개여야 합니다.')
        with self.condition:
            if self.stopping:
                raise ValueError('앱을 종료하고 있습니다.')
            pending = []
            order = max((j['order'] for j in self.jobs.values()), default=0)
            for request in requests:
                vid, playlist_id = parse_youtube_url(request['url'])
                scope = request.get('scope', 'single')
                if scope not in {'single', 'playlist'} or (scope == 'playlist' and not playlist_id):
                    raise ValueError('다운로드 범위를 확인하세요.')
                options = settings_with(request.get('options'), self.settings)
                entries = request.get('items') or []
                if not entries or (scope == 'single' and len(entries) != 1):
                    raise ValueError('다운로드할 영상을 선택하세요.')
                items = []
                for position, entry in enumerate(entries, 1):
                    entry_vid, _ = parse_youtube_url(entry['url'])
                    if not entry_vid or (scope == 'single' and vid != entry_vid):
                        raise ValueError('선택한 영상 URL을 확인하세요.')
                    index = int(entry.get('index', position))
                    if index < 1:
                        raise ValueError('영상 순번이 올바르지 않습니다.')
                    items.append({
                        'item_id': uuid.uuid4().hex, 'id': entry_vid, 'url': video_url(entry_vid),
                        'index': index, 'title': str(entry.get('title') or entry_vid),
                        'thumbnail': entry.get('thumbnail'), 'duration': entry.get('duration'),
                        'uploader': entry.get('uploader') or '', 'status': 'pending',
                        'stage': 'queued', 'percent': 0, 'warnings': [], 'error': None,
                    })
                order += 1
                job = {
                    'id': uuid.uuid4().hex, 'url': request['url'], 'scope': scope,
                    'title': str(request.get('title') or items[0]['title']),
                    'options': options, 'items': items, 'status': 'queued',
                    'created_at': time.time(), 'updated_at': time.time(), 'order': order,
                    'retry_of': request.get('retry_of'),
                }
                pending.append(job)
            for job in pending:
                self.jobs[job['id']] = job
                self.store.save_job(job)
                self.batch_ids.add(job['id'])
            self._changed()
            return [job['id'] for job in pending]

    def pause(self):
        with self.condition:
            self.paused = True
            self._changed()

    def resume(self):
        with self.condition:
            for job in self.jobs.values():
                if job['status'] == 'interrupted':
                    job['status'] = 'queued'
                    self.store.save_job(job)
                if job['status'] == 'queued':
                    self.batch_ids.add(job['id'])
            self.paused = False
            self._changed()

    def cancel_job(self, job_id):
        with self.condition:
            job = self.jobs[job_id]
            if job['status'] in ACTIVE:
                self.cancel.set()
                job['status'] = 'cancelling'
            elif job['status'] in {'queued', 'interrupted'}:
                job['status'] = 'cancelled'
                for item in job['items']:
                    if item['status'] not in ITEM_DONE:
                        item['status'] = 'cancelled'
            else:
                raise ValueError('이미 종료된 작업입니다.')
            self._changed(job)

    def reorder(self, ids):
        with self.condition:
            queued = {j['id'] for j in self.jobs.values() if j['status'] in {'queued', 'interrupted'}}
            if not isinstance(ids, list) or len(ids) != len(set(ids)) or set(ids) != queued:
                raise ValueError('대기열이 변경되었습니다. 다시 시도하세요.')
            start = max((j['order'] for j in self.jobs.values() if j['id'] not in queued), default=0)
            for index, job_id in enumerate(ids, start + 1):
                self.jobs[job_id]['order'] = index
                self.store.save_job(self.jobs[job_id])
            self._changed()

    def retry(self, job_id, all_items=False):
        with self.condition:
            job = self.jobs[job_id]
            if job['status'] not in TERMINAL:
                raise ValueError('진행 중인 작업은 재시도할 수 없습니다.')
            items = [i for i in job['items'] if all_items or i['status'] not in ITEM_DONE]
            if not items:
                raise ValueError('재시도할 항목이 없습니다.')
            ids = self.enqueue([{
                'url': job['url'], 'title': job['title'], 'scope': job['scope'],
                'items': items, 'options': job['options'], 'retry_of': job_id,
            }])
            if not all_items:
                # Reuse only unfinished staging files; successful items are never downloaded twice.
                new_job = self.jobs[ids[0]]
                for new, old in zip(new_job['items'], items):
                    new['item_id'] = old['item_id']
                    if old.get('target_path'):
                        new['target_path'] = old['target_path']
                self._changed(new_job)
            return ids

    def delete(self, job_id):
        with self.condition:
            job = self.jobs[job_id]
            if job['status'] in ACTIVE:
                raise ValueError('진행 중인 작업은 먼저 취소하세요.')
            self.store.delete_job(job_id)
            del self.jobs[job_id]
            self.batch_ids.discard(job_id)
            self._changed()

    def history(self, query='', status='all'):
        with self.lock:
            result = copy.deepcopy([j for j in self.jobs.values() if j['status'] in TERMINAL
                                    and (status == 'all' or j['status'] == status)
                                    and query.lower() in j['title'].lower()])
        for job in result:
            for item in job['items']:
                item['file_exists'] = bool(item.get('path') and Path(item['path']).is_file())
        return sorted(result, key=lambda j: j['created_at'], reverse=True)

    def shutdown(self):
        with self.condition:
            self.stopping = True
            self.paused = True
            self.cancel.set()
            self.condition.notify_all()
        if self.thread.is_alive() and self.thread != threading.current_thread():
            self.thread.join()

    def _worker(self):
        while True:
            summary = None
            with self.condition:
                if self.stopping:
                    return
                candidates = sorted([j for j in self.jobs.values() if j['status'] == 'queued'], key=lambda j: j['order'])
                if self.paused or not candidates:
                    if not candidates and not self.paused and self.batch_ids:
                        batch = [self.jobs[i] for i in self.batch_ids if i in self.jobs]
                        finished = [j for j in batch if j['status'] in TERMINAL and j['status'] != 'cancelled']
                        if finished:
                            summary = {
                                'completed': sum(i['status'] in ITEM_DONE for j in finished for i in j['items']),
                                'failed': sum(i['status'] == 'failed' for j in finished for i in j['items']),
                            }
                        self.batch_ids.clear()
                    if summary is None:
                        self.condition.wait(timeout=0.5)
                        continue
                else:
                    job = candidates[0]
                    self.cancel.clear()
                    job['status'] = 'running'
                    self._changed(job)
            if summary is not None:
                try:
                    self.on_drained(summary)
                except Exception:
                    pass  # An OS notification must never stop the queue.
                continue
            self._run_job(job)

    def _run_job(self, job):
        for item in job['items']:
            if item['status'] in ITEM_DONE:
                continue
            if self.cancel.is_set():
                break

            def update(fields):
                with self.condition:
                    item.update(fields)
                    self._changed(job)

            update({'status': 'running', 'stage': 'preparing', 'error': None})
            try:
                result = self.runner.run(job, item, self.cancel, update)
                update({**result, 'stage': result['status'], 'speed': None, 'eta': None})
            except Exception as error:
                if isinstance(error, DownloadCancelled) or self.cancel.is_set():
                    update({'status': 'cancelled', 'stage': 'cancelled', 'speed': None, 'eta': None})
                    break
                update({'status': 'failed', 'stage': 'failed', 'speed': None, 'eta': None,
                        'error': error_message(error), 'error_detail': safe_error(error)})
        with self.condition:
            unfinished = [i for i in job['items'] if i['status'] not in ITEM_DONE and i['status'] != 'failed']
            if self.stopping and unfinished:
                job['status'] = 'interrupted'
                for item in unfinished:
                    item.update(status='pending', stage='interrupted')
            elif self.cancel.is_set() and unfinished:
                job['status'] = 'cancelled'
                for item in unfinished:
                    item.update(status='cancelled', stage='cancelled')
            else:
                failed = sum(i['status'] == 'failed' for i in job['items'])
                successes = sum(i['status'] in ITEM_DONE for i in job['items'])
                job['status'] = ('partial' if successes else 'failed') if failed else 'completed'
            self._changed(job)
