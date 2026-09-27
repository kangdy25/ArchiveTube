import asyncio
import copy
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobs import JobManager
from main import BackendApi
from media import DownloadRunner, MediaService, describe, download_options
from models import defaults, parse_youtube_url, safe_error, safe_name, settings_with
from runtime import binary, ffmpeg_path
from store import Store


def request(directory, ids=('one', 'two'), **options):
    return {
        'url': 'https://www.youtube.com/playlist?list=abc', 'scope': 'playlist', 'title': 'My playlist',
        'options': {'download_dir': str(directory), **options},
        'items': [{'id': vid, 'index': index, 'title': f'Video {vid}', 'url': f'https://youtube.com/watch?v={vid}'}
                  for index, vid in enumerate(ids, 1)],
    }


def wait_until(predicate, timeout=4):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError('Timed out waiting for queue state')


class SuccessfulRunner:
    def __init__(self):
        self.calls = []

    def run(self, job, item, cancel, update):
        self.calls.append((job['id'], item['id'], copy.deepcopy(job['options'])))
        target = Path(job['options']['download_dir']) / f"{item['id']}.mp4"
        target.write_bytes(b'completed')
        return {'status': 'completed', 'path': str(target), 'percent': 100, 'warnings': []}


class FakeYDL:
    fail = False
    calls = []

    def __init__(self, options):
        self.options = options
        self.calls.append(options)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def extract_info(self, url, download=False):
        if 'playlist?list=' in url:
            return {'title': 'Playlist', 'entries': [
                {'id': 'one', 'title': 'First', 'duration': 60, 'uploader': 'Artist'},
                {'id': 'two', 'title': 'Private', 'availability': 'private'}, None,
            ]}
        info = {'id': 'one', 'title': 'First', 'height': 720, 'uploader': 'Artist', 'description': 'Description',
                'subtitles': {'en': [{'url': 'https://example.test/en.vtt'}]}, 'duration': 60,
                'formats': [{'ext': 'mp4', 'height': 720, 'acodec': 'aac', 'vcodec': 'h264'}]}
        if self.options.get('skip_download'):
            if self.options.get('writesubtitles'):
                path = self.options['outtmpl'] % {'ext': 'en.vtt'}
                Path(path).write_text('WEBVTT\n\n00:00:00.000 --> 00:00:00.200\nHello\n')
            if self.options.get('writethumbnail'):
                Path(self.options['outtmpl'] % {'ext': 'jpg'}).write_bytes(b'thumbnail')
        elif download:
            for hook in self.options.get('progress_hooks', []):
                hook({'status': 'downloading', 'downloaded_bytes': 5, 'total_bytes': 10, 'speed': 5, 'eta': 1})
                hook({'status': 'finished'})
            if self.fail:
                raise RuntimeError('FFmpeg merge failed after download finished')
            for hook in self.options.get('postprocessor_hooks', []):
                hook({'status': 'finished'})
            output = self.options['outtmpl'] % {'ext': self.options.get('final_ext', 'mp4')}
            Path(output).write_bytes(b'complete media')
            info['filepath'] = output
        return info


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root / 'state.db')
        self.manager = JobManager(self.store, SuccessfulRunner(), autostart=False)

    def tearDown(self):
        self.manager.shutdown()
        self.store.close()
        self.temp.cleanup()

    def start(self):
        self.manager.thread.start()

    def test_options_and_stable_video_identity_survive_restart(self):
        ids = self.manager.enqueue([request(self.root, video_quality='720')])
        self.manager.save_settings({'video_quality': '1080'})
        restored = JobManager(self.store, SuccessfulRunner(), autostart=False)
        self.assertTrue(restored.paused)
        self.assertEqual(restored.jobs[ids[0]]['options']['video_quality'], '720')
        self.assertEqual(restored.jobs[ids[0]]['items'][1]['url'], 'https://www.youtube.com/watch?v=two')

    def test_restored_running_item_is_interrupted_not_success(self):
        job_id = self.manager.enqueue([request(self.root)])[0]
        job = self.manager.jobs[job_id]
        job['status'] = 'running'; job['items'][0]['status'] = 'running'
        self.store.save_job(job)
        restored = JobManager(self.store, SuccessfulRunner(), autostart=False)
        self.assertEqual(restored.jobs[job_id]['status'], 'interrupted')
        restored.thread.start()
        time.sleep(0.04)
        self.assertEqual(restored.jobs[job_id]['status'], 'interrupted')
        restored.resume()
        wait_until(lambda: restored.jobs[job_id]['status'] == 'completed')
        restored.shutdown()

    def test_serial_execution_and_queue_reordering(self):
        ids = self.manager.enqueue([request(self.root, (key,)) for key in ['one', 'two', 'three']])
        self.manager.reorder(ids[::-1])
        self.start()
        wait_until(lambda: all(j['status'] == 'completed' for j in self.manager.jobs.values()))
        self.assertEqual([call[1] for call in self.manager.runner.calls], ['three', 'two', 'one'])
        self.assertEqual(max(j['updated_at'] for j in self.manager.jobs.values()), self.manager.jobs[ids[0]]['updated_at'])

    def test_notification_is_once_per_drained_queue(self):
        summaries = []
        self.manager.on_drained = summaries.append
        self.manager.enqueue([request(self.root, ('one',)), request(self.root, ('two',))])
        self.start()
        wait_until(lambda: len(summaries) == 1)
        self.assertEqual(summaries, [{'completed': 2, 'failed': 0}])
        time.sleep(.55)
        self.assertEqual(len(summaries), 1)

    def test_cancel_only_queue_does_not_notify(self):
        summaries = []
        self.manager.on_drained = summaries.append
        job_id = self.manager.enqueue([request(self.root)])[0]
        self.manager.cancel_job(job_id)
        self.start()
        wait_until(lambda: not self.manager.batch_ids)
        self.assertEqual(summaries, [])

    def test_pause_finishes_current_job_but_prevents_next(self):
        entered = threading.Event(); release = threading.Event()
        class Blocking(SuccessfulRunner):
            def run(inner, *args):
                entered.set(); release.wait(2)
                return super().run(*args)
        self.manager.runner = Blocking()
        ids = self.manager.enqueue([request(self.root, ('one',)), request(self.root, ('two',))])
        self.start(); self.assertTrue(entered.wait(2)); self.manager.pause(); release.set()
        wait_until(lambda: self.manager.jobs[ids[0]]['status'] == 'completed')
        self.assertEqual(self.manager.jobs[ids[1]]['status'], 'queued')
        self.manager.resume()
        wait_until(lambda: self.manager.jobs[ids[1]]['status'] == 'completed')

    def test_failed_item_does_not_stop_batch_and_retry_only_failed(self):
        class Failing(SuccessfulRunner):
            def run(inner, job, item, cancel, update):
                if item['id'] == 'two':
                    raise RuntimeError('network disconnected')
                return super().run(job, item, cancel, update)
        self.manager.runner = Failing()
        job_id = self.manager.enqueue([request(self.root, ('one', 'two', 'three'))])[0]
        self.start(); wait_until(lambda: self.manager.jobs[job_id]['status'] == 'partial')
        self.manager.pause()
        retry_id = self.manager.retry(job_id)[0]
        retry = self.manager.jobs[retry_id]
        self.assertEqual([i['id'] for i in retry['items']], ['two'])
        self.assertEqual(retry['items'][0]['index'], 2)
        self.assertEqual(self.manager.jobs[job_id]['status'], 'partial')
        self.manager.runner = SuccessfulRunner(); self.manager.resume()
        wait_until(lambda: retry['status'] == 'completed')

    def test_cancel_during_conversion_keeps_finished_file_and_remaining_retry(self):
        entered = threading.Event(); release = threading.Event()
        class Converting(SuccessfulRunner):
            def run(inner, job, item, cancel, update):
                update({'stage': 'processing'}); entered.set(); release.wait(2)
                return super().run(job, item, cancel, update)
        self.manager.runner = Converting()
        job_id = self.manager.enqueue([request(self.root)])[0]
        self.start(); self.assertTrue(entered.wait(2))
        self.manager.cancel_job(job_id); release.set()
        wait_until(lambda: self.manager.jobs[job_id]['status'] == 'cancelled')
        self.assertEqual([i['status'] for i in self.manager.jobs[job_id]['items']], ['completed', 'cancelled'])
        self.manager.pause()
        retry = self.manager.jobs[self.manager.retry(job_id)[0]]
        self.assertEqual([i['id'] for i in retry['items']], ['two'])

    def test_delete_history_never_deletes_media(self):
        job_id = self.manager.enqueue([request(self.root, ('one',))])[0]
        self.start(); wait_until(lambda: self.manager.jobs[job_id]['status'] == 'completed')
        self.manager.delete(job_id)
        self.assertTrue((self.root / 'one.mp4').is_file())
        self.assertEqual(self.store.jobs(), [])

    def test_history_checks_missing_files(self):
        job_id = self.manager.enqueue([request(self.root, ('one',))])[0]
        self.start(); wait_until(lambda: self.manager.jobs[job_id]['status'] == 'completed')
        (self.root / 'one.mp4').unlink()
        self.assertFalse(self.manager.history()[0]['items'][0]['file_exists'])

    def test_revisions_are_monotonic_and_snapshots_cannot_mutate_state(self):
        revisions = []
        self.manager.on_change = lambda data: revisions.append(data['revision'])
        self.manager.enqueue([request(self.root)])
        self.manager.pause(); self.manager.resume()
        snapshot = self.manager.snapshot(); snapshot['settings']['theme'] = 'light'
        self.assertEqual(self.manager.settings['theme'], 'dark')
        self.assertEqual(revisions, sorted(set(revisions)))

    def test_invalid_batch_is_not_partially_registered(self):
        with self.assertRaises(ValueError):
            self.manager.enqueue([request(self.root), {**request(self.root), 'items': []}])
        self.assertEqual(self.store.jobs(), [])

    def test_single_worker_stays_single_while_new_jobs_are_added(self):
        entered = threading.Event(); release = threading.Event()
        class Blocking(SuccessfulRunner):
            def run(inner, *args):
                entered.set(); release.wait(2)
                return super().run(*args)
        self.manager.runner = Blocking()
        first = self.manager.enqueue([request(self.root, ('one',))])[0]
        self.start(); self.assertTrue(entered.wait(2))
        second = self.manager.enqueue([request(self.root, ('two',))])[0]
        self.assertEqual(self.manager.jobs[first]['status'], 'running')
        self.assertEqual(self.manager.jobs[second]['status'], 'queued')
        release.set(); wait_until(lambda: self.manager.jobs[second]['status'] == 'completed')


class MediaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.options = settings_with({'download_dir': str(self.root)})
        self.job = {'id': 'job', 'options': self.options, 'title': 'Playlist', 'scope': 'single'}
        self.item = {'id': 'one', 'item_id': 'item-one', 'index': 1, 'title': 'First', 'url': 'https://youtube.com/watch?v=one'}
        self.updates = []
        FakeYDL.calls = []; FakeYDL.fail = False

    def tearDown(self):
        FakeYDL.fail = False; self.temp.cleanup()

    def run_download(self):
        return DownloadRunner(FakeYDL).run(self.job, self.item, threading.Event(), lambda data: self.updates.append(data))

    def test_discovery_includes_unavailable_entries_and_current_video(self):
        info = MediaService(FakeYDL).get_info('https://youtube.com/watch?v=one&list=abc', self.options)
        self.assertEqual([e['is_available'] for e in info['entries']], [True, False, False])
        self.assertEqual(info['current_video']['subtitle_languages'], ['en'])
        self.assertEqual(info['entries'][0]['url'], 'https://www.youtube.com/watch?v=one')

    def test_placeholder_entries_and_authorized_private_video(self):
        self.assertFalse(describe({'id': 'one', 'title': '[Deleted video]'})['is_available'])
        self.assertFalse(describe({'id': 'one', 'title': '[Private video]'})['is_available'])
        self.assertTrue(describe({'id': 'one', 'title': 'My video', 'availability': 'private',
                                  'formats': [{'ext': 'mp4'}]})['is_available'])

    def test_finished_transfer_then_postprocess_failure_is_not_success(self):
        FakeYDL.fail = True
        with self.assertRaisesRegex(RuntimeError, 'merge failed'):
            self.run_download()
        self.assertTrue(any(update['stage'] == 'processing' for update in self.updates))
        self.assertFalse((self.root / 'First.mp4').exists())
        self.assertFalse(any(update.get('status') == 'completed' for update in self.updates))

    def test_final_file_and_actual_quality_verified(self):
        result = self.run_download()
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['actual_quality'], '720p')
        self.assertTrue(Path(result['path']).is_file())

    def test_skip_does_not_start_download(self):
        (self.root / 'First.mp4').write_bytes(b'original'); self.options['collision'] = 'skip'
        result = self.run_download()
        self.assertEqual(result['status'], 'skipped'); self.assertEqual(FakeYDL.calls, [])

    def test_rename_applies_to_media_and_sidecars(self):
        (self.root / 'First.mp4').write_bytes(b'original')
        self.options.update(save_metadata=True, save_description=True, save_thumbnail=True, subtitle_mode='file')
        result = self.run_download()
        self.assertEqual(Path(result['path']).name, 'First (2).mp4')
        self.assertEqual((self.root / 'First.mp4').read_bytes(), b'original')
        self.assertTrue((self.root / 'First (2).info.json').exists())
        self.assertTrue((self.root / 'First (2).en.vtt').exists())
        metadata = json.loads((self.root / 'First (2).info.json').read_text())
        self.assertEqual(metadata['uploader'], 'Artist')
        self.assertNotIn('cookies', metadata)
        self.assertTrue(any('ko' in warning for warning in result['warnings']))

    def test_overwrite_preserves_original_on_failure(self):
        original = self.root / 'First.mp4'; original.write_bytes(b'original')
        self.options['collision'] = 'overwrite'; FakeYDL.fail = True
        with self.assertRaises(RuntimeError): self.run_download()
        self.assertEqual(original.read_bytes(), b'original')

    def test_different_formats_do_not_share_skip_identity(self):
        (self.root / 'First.mp4').write_bytes(b'existing video')
        self.options.update(format_type='audio', collision='skip')
        self.assertEqual(self.run_download()['status'], 'completed')
        self.assertTrue((self.root / 'First.mp3').exists())

    def test_subtitle_failure_is_warning_not_media_failure(self):
        class SubtitleFail(FakeYDL):
            def extract_info(inner, *args, **kwargs):
                if inner.options.get('writesubtitles'): raise RuntimeError('subtitle offline')
                return super().extract_info(*args, **kwargs)
        self.options['subtitle_mode'] = 'file'
        result = DownloadRunner(SubtitleFail).run(self.job, self.item, threading.Event(), lambda _: None)
        self.assertEqual(result['status'], 'completed')
        self.assertTrue(any('자막 저장 실패' in warning for warning in result['warnings']))

    def test_storage_permission_failure_is_not_ignored(self):
        with patch('media.os.replace', side_effect=PermissionError('Permission denied')):
            with self.assertRaises(PermissionError): self.run_download()

    def test_format_limits_cookies_and_m4a_no_transcoding(self):
        opts = download_options(settings_with({'video_quality': '720', 'cookie_browser': 'firefox', 'cookie_profile': 'test'}), Path('/tmp/x'), lambda _: None, lambda _: None)
        self.assertIn('[height<=720]', opts['format'])
        self.assertEqual(opts['cookiesfrombrowser'], ('firefox', 'test'))
        audio = download_options(settings_with({'format_type': 'audio', 'audio_format': 'm4a'}), Path('/tmp/x'), lambda _: None, lambda _: None)
        self.assertEqual(audio['format'], 'bestaudio[ext=m4a]')
        self.assertNotIn('preferredquality', audio['postprocessors'][0])


class ValidationTests(unittest.TestCase):
    def test_youtube_variants_and_host_validation(self):
        self.assertEqual(parse_youtube_url('https://youtu.be/abc?list=xyz'), ('abc', 'xyz'))
        self.assertEqual(parse_youtube_url('https://youtube.com/shorts/abc'), ('abc', None))
        self.assertEqual(parse_youtube_url('https://youtube.com/live/abc'), ('abc', None))
        for url in ['https://youtube.com.attacker.test/watch?v=abc', 'file:///etc/passwd', 'https://example.com/?v=x']:
            with self.assertRaises(ValueError): parse_youtube_url(url)

    def test_setting_and_file_name_validation(self):
        with self.assertRaises(ValueError): settings_with({'collision': 'delete'})
        with self.assertRaises(ValueError): settings_with({'download_dir': 'relative'})
        with self.assertRaises(ValueError): settings_with({'subtitle_languages': ['../ko']})
        self.assertNotIn('/', safe_name('../bad/name'))
        self.assertEqual(safe_name('CON'), '_CON')
        self.assertLessEqual(len(safe_name('한글 제목' * 100).encode('utf-8')), 180)
        self.assertNotIn('SECRET', safe_error('Cookie=SECRET https://test/?token=SECRET'))


class BridgeTests(unittest.TestCase):
    def test_bridge_reports_errors_and_persists_settings(self):
        with tempfile.TemporaryDirectory() as root:
            api = BackendApi(database=Path(root) / 'state.db', runner=SuccessfulRunner(), media=MediaService(FakeYDL), autostart=False)
            try:
                self.assertTrue(api.save_settings({'theme': 'light'})['success'])
                self.assertEqual(api.get_state()['settings']['theme'], 'light')
                self.assertFalse(api.get_info('https://example.test/video')['success'])
                self.assertFalse(api.enqueue_downloads([])['success'])
                result = api.download('https://youtube.com/watch?v=one', 'audio', 'single')
                self.assertTrue(result['success'])
                self.assertEqual(api.manager.jobs[result['job_id']]['options']['format_type'], 'audio')
            finally:
                api.manager.shutdown(); api.store.close()


class FFmpegTests(unittest.TestCase):
    @unittest.skipUnless(binary('ffprobe'), 'FFprobe required for integration check')
    def test_local_mp3_m4a_and_embedded_mp4_subtitle(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root); video = root / 'fixture.mp4'
            subprocess.run([ffmpeg_path(), '-y', '-f', 'lavfi', '-i', 'color=c=blue:s=160x90:d=0.3', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=0.3', '-c:v', 'libx264', '-c:a', 'aac', '-shortest', str(video)], check=True, capture_output=True)
            subtitle = root / 'fixture.en.vtt'; subtitle.write_text('WEBVTT\n\n00:00:00.000 --> 00:00:00.200\nHello\n')
            DownloadRunner._embed(video, [subtitle], 'mp4')
            probe = json.loads(subprocess.check_output([binary('ffprobe'), '-v', 'quiet', '-show_streams', '-of', 'json', str(video)]))
            self.assertTrue(any(s['codec_type'] == 'subtitle' for s in probe['streams']))
            webm = root / 'fixture.webm'
            subprocess.run([ffmpeg_path(), '-y', '-i', str(video), '-sn', '-c:v', 'libvpx-vp9',
                            '-c:a', 'libopus', str(webm)], check=True, capture_output=True)
            DownloadRunner._embed(webm, [subtitle], 'webm')
            webm_probe = json.loads(subprocess.check_output([binary('ffprobe'), '-v', 'quiet', '-show_streams', '-of', 'json', str(webm)]))
            self.assertTrue(any(s['codec_name'] == 'webvtt' for s in webm_probe['streams']))
            for ext, codec in [('mp3', 'libmp3lame'), ('m4a', 'copy')]:
                output = root / f'audio.{ext}'
                subprocess.run([ffmpeg_path(), '-y', '-i', str(video), '-vn', '-sn', '-c:a', codec, str(output)], check=True, capture_output=True)
                self.assertGreater(output.stat().st_size, 0)


if __name__ == '__main__':
    unittest.main()
