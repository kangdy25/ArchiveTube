"""YouTube discovery and one-item downloads, with optional extras isolated from media."""
import json
import os
import re
import subprocess
import time
from pathlib import Path

import yt_dlp

from models import extension, parse_youtube_url, safe_error, safe_name, video_url
from runtime import ffmpeg_path, runtime_options


class DownloadCancelled(Exception):
    pass


def thumbnail(info):
    return info.get('thumbnail') or next((t.get('url') for t in reversed(info.get('thumbnails') or []) if t.get('url')), None)


def describe(info, index=1):
    identifier = info.get('id')
    return {
        'id': identifier, 'index': index, 'url': video_url(identifier) if identifier else '',
        'title': info.get('title') or f'영상 {index}', 'thumbnail': thumbnail(info),
        'duration': info.get('duration'), 'uploader': info.get('uploader') or info.get('channel') or '',
        'upload_date': info.get('upload_date'), 'is_live': bool(info.get('is_live')),
        'is_available': bool(identifier) and info.get('title') not in {'[Private video]', '[Deleted video]'}
        and (bool(info.get('formats')) or info.get('availability') not in {
            'private', 'premium_only', 'subscriber_only', 'needs_auth'}),
    }


class MediaService:
    def __init__(self, ydl_factory=None):
        self.ydl_factory = ydl_factory or yt_dlp.YoutubeDL

    def get_info(self, url, settings):
        vid, playlist_id = parse_youtube_url(url)
        opts = runtime_options(settings)
        current = None
        playlist = None
        warnings = []
        if playlist_id:
            try:
                with self.ydl_factory({**opts, 'extract_flat': 'in_playlist', 'skip_download': True}) as ydl:
                    data = ydl.extract_info(f'https://www.youtube.com/playlist?list={playlist_id}', download=False)
                if not data:
                    raise ValueError('재생목록 정보를 가져오지 못했습니다.')
                entries = [describe(entry or {}, index) for index, entry in enumerate(data.get('entries') or [], 1)]
                playlist = {
                    'id': playlist_id, 'is_playlist': True, 'title': data.get('title') or '재생목록',
                    'url': f'https://www.youtube.com/playlist?list={playlist_id}',
                    'thumbnail': thumbnail(data) or next((e['thumbnail'] for e in entries if e['thumbnail']), None),
                    'uploader': data.get('uploader') or '', 'entries': entries, 'video_count': len(entries),
                }
            except Exception as error:
                if not vid:
                    raise
                warnings.append('재생목록 분석 실패: ' + safe_error(error))
        if vid:
            try:
                with self.ydl_factory({**opts, 'noplaylist': True, 'skip_download': True}) as ydl:
                    data = ydl.extract_info(video_url(vid), download=False)
                if not data:
                    raise ValueError('영상 정보를 가져오지 못했습니다.')
                current = describe(data)
                formats = {}
                for f in data.get('formats') or []:
                    key = (f.get('ext'), f.get('height'), f.get('acodec') != 'none', f.get('vcodec') != 'none')
                    formats[key] = {'ext': key[0], 'height': key[1], 'has_audio': key[2], 'has_video': key[3]}
                current.update({
                    'formats': list(formats.values()),
                    'subtitle_languages': sorted((data.get('subtitles') or {}).keys()),
                    'auto_subtitle_languages': sorted((data.get('automatic_captions') or {}).keys()),
                })
            except Exception as error:
                if not playlist:
                    raise
                warnings.append('현재 영상 분석 실패: ' + safe_error(error))
        result = playlist or current
        if not result:
            raise ValueError('영상 정보를 찾지 못했습니다.')
        result.update({'success': True, 'warnings': warnings})
        if playlist and current:
            result['current_video'] = current
            result.update(video_title=current['title'], video_url=current['url'],
                          video_thumbnail=current['thumbnail'], video_duration=current['duration'])
        return result


def download_options(options, stem, hook, post_hook):
    ext = extension(options)
    result = {
        **runtime_options(options), 'noplaylist': True, 'ignoreerrors': False,
        'outtmpl': str(stem).replace('%', '%%') + '.%(ext)s',
        'progress_hooks': [hook], 'postprocessor_hooks': [post_hook],
        'continuedl': True, 'overwrites': True,
    }
    if options['format_type'] == 'video':
        limit = '' if options['video_quality'] == 'best' else f"[height<={options['video_quality']}]"
        audio = 'm4a' if ext == 'mp4' else 'webm'
        result.update(format=f'bestvideo[ext={ext}]{limit}+bestaudio[ext={audio}]/best[ext={ext}]{limit}',
                      merge_output_format=ext, final_ext=ext)
    elif ext == 'mp3':
        result.update(format='bestaudio/best', final_ext='mp3', postprocessors=[{
            'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3',
            'preferredquality': str(options['audio_bitrate']),
        }])
    else:
        # Copy AAC in an M4A container without inventing a bitrate or transcoding.
        result.update(format='bestaudio[ext=m4a]', final_ext='m4a', postprocessors=[{
            'key': 'FFmpegExtractAudio', 'preferredcodec': 'm4a',
        }])
    return result


class DownloadRunner:
    def __init__(self, ydl_factory=None):
        self.ydl_factory = ydl_factory or yt_dlp.YoutubeDL

    def run(self, job, item, cancel, update):
        options = job['options']
        folder = Path(options['download_dir'])
        if job['scope'] == 'playlist':
            folder /= safe_name(job['title'])
        folder.mkdir(parents=True, exist_ok=True)
        ext = extension(options)
        name = safe_name(item['title'])
        if job['scope'] == 'playlist':
            name = f"{item['index']:02d} - {name}"
        target = Path(item['target_path']) if item.get('target_path') else folder / f'{name}.{ext}'
        if target.exists():
            if options['collision'] == 'skip':
                return {'status': 'skipped', 'path': str(target), 'warnings': [], 'actual_quality': None}
            if options['collision'] == 'rename':
                suffix = 2
                while target.exists():
                    target = folder / f'{name} ({suffix}).{ext}'
                    suffix += 1
        update({'target_path': str(target), 'stage': 'preparing', 'status': 'running'})
        # Stable staging path permits a stopped download to resume without touching a final file.
        staging = folder / '.archivetube' / item['item_id']
        staging.mkdir(parents=True, exist_ok=True)
        stem = staging / target.stem
        last_update = 0.0

        def hook(data):
            nonlocal last_update
            if cancel.is_set():
                raise DownloadCancelled()
            now = time.monotonic()
            if data['status'] == 'downloading' and now - last_update >= 0.25:
                last_update = now
                total = data.get('total_bytes') or data.get('total_bytes_estimate')
                downloaded = data.get('downloaded_bytes', 0)
                update({'stage': 'downloading', 'downloaded_bytes': downloaded,
                        'total_bytes': total, 'speed': data.get('speed'), 'eta': data.get('eta'),
                        'percent': min(99, downloaded / total * 100) if total else None})
            elif data['status'] == 'finished':
                update({'stage': 'processing', 'speed': None, 'eta': None, 'percent': None})

        def post_hook(_data):
            # Let an in-flight conversion finish; cancellation is checked before the next item.
            update({'stage': 'processing', 'speed': None, 'eta': None, 'percent': None})

        if cancel.is_set():
            raise DownloadCancelled()
        with self.ydl_factory(download_options(options, stem, hook, post_hook)) as ydl:
            info = ydl.extract_info(item['url'], download=True)
        media_path = stem.with_name(stem.name + '.' + ext)
        if not info or not media_path.is_file() or media_path.stat().st_size == 0:
            raise RuntimeError('다운로드 후 최종 미디어 파일을 확인하지 못했습니다.')
        warnings = []
        if not cancel.is_set():
            warnings = self._extras(options, item, info, stem, media_path, update)
        elif any(options.get(k) for k in ('save_thumbnail', 'save_description', 'save_metadata')) or options['subtitle_mode'] != 'off':
            warnings.append('취소 요청으로 추가 보관 파일 처리를 생략했습니다.')
        update({'stage': 'saving', 'speed': None, 'eta': None, 'percent': None})
        if target.exists() and options['collision'] != 'overwrite':
            # Another program may have created this filename while we were downloading.
            raise FileExistsError('저장 중 같은 이름의 파일이 생겼습니다. 다시 시도하면 충돌 정책을 적용합니다.')
        os.replace(media_path, target)
        extras = []
        for file in list(staging.iterdir()):
            if file.is_file() and file.name.startswith(stem.name + '.') and not file.name.endswith(('.part', '.ytdl', '.tmp')):
                destination = folder / file.name
                try:
                    if destination.exists() and options['collision'] != 'overwrite':
                        warnings.append(f'추가 파일이 이미 있어 건너뛰었습니다: {destination.name}')
                        continue
                    os.replace(file, destination)
                    extras.append(str(destination))
                except OSError as error:
                    warnings.append('추가 파일 저장 실패: ' + safe_error(error))
        # Only remove an empty, application-owned staging directory.
        try:
            staging.rmdir()
            staging.parent.rmdir()
        except OSError:
            pass
        actual = f"{info['height']}p" if info.get('height') and options['format_type'] == 'video' else (
            f"{options['audio_bitrate']}kbps" if ext == 'mp3' else (f"{round(info['abr'])}kbps" if info.get('abr') else None))
        return {'status': 'completed', 'path': str(target), 'extra_paths': extras,
                'actual_quality': actual, 'warnings': warnings, 'percent': 100,
                'size': target.stat().st_size}

    def _extras(self, options, item, info, stem, media_path, update):
        warnings = []
        selected_subtitles = []
        update({'stage': 'extras', 'speed': None, 'eta': None, 'percent': None})
        if options['subtitle_mode'] != 'off':
            manual = info.get('subtitles') or {}
            automatic = info.get('automatic_captions') or {} if options['auto_subtitles'] else {}
            for requested in options['subtitle_languages']:
                matches = [lang for lang in manual if lang == requested or lang.startswith(requested + '-')]
                if not matches:
                    matches = [lang for lang in automatic if lang == requested or lang.startswith(requested + '-')]
                if not matches:
                    warnings.append(f'{requested} 자막이 없어 미디어만 저장했습니다.')
                selected_subtitles.extend(matches)
            if selected_subtitles:
                try:
                    with self.ydl_factory({
                        **runtime_options(options), 'skip_download': True, 'noplaylist': True,
                        'outtmpl': str(stem).replace('%', '%%') + '.%(ext)s',
                        'writesubtitles': True, 'writeautomaticsub': options['auto_subtitles'],
                        'subtitleslangs': [re.escape(lang) for lang in sorted(set(selected_subtitles))],
                        'subtitlesformat': 'vtt/best',
                    }) as ydl:
                        # skip_download still writes requested subtitles.
                        ydl.extract_info(item['url'], download=True)
                except Exception as error:
                    warnings.append('자막 저장 실패: ' + safe_error(error))
                if options['subtitle_mode'] == 'embed' and options['format_type'] == 'video':
                    files = sorted(p for p in stem.parent.iterdir() if p.name.startswith(stem.name + '.') and p.suffix == '.vtt')
                    if files:
                        try:
                            self._embed(media_path, files, extension(options))
                        except Exception as error:
                            warnings.append('자막 삽입 실패 (별도 파일 유지): ' + safe_error(error))
        if options['save_thumbnail']:
            try:
                with self.ydl_factory({**runtime_options(options), 'skip_download': True, 'noplaylist': True,
                                      'outtmpl': str(stem).replace('%', '%%') + '.%(ext)s', 'writethumbnail': True}) as ydl:
                    ydl.extract_info(item['url'], download=True)
            except Exception as error:
                warnings.append('썸네일 저장 실패: ' + safe_error(error))
        for enabled, suffix, value in [
            (options['save_description'], '.description.txt', info.get('description') or ''),
            (options['save_metadata'], '.info.json', json.dumps({
                'id': item['id'], 'title': info.get('title') or item['title'],
                'uploader': info.get('uploader'), 'url': item['url'],
                'upload_date': info.get('upload_date'), 'duration': info.get('duration'),
                'height': info.get('height'), 'format': extension(options),
            }, ensure_ascii=False, indent=2)),
        ]:
            if enabled:
                try:
                    Path(str(stem) + suffix).write_text(value, encoding='utf-8')
                except OSError as error:
                    warnings.append('보관 정보 저장 실패: ' + safe_error(error))
        return warnings

    @staticmethod
    def _embed(media, subtitles, ext):
        destination = media.with_name(media.stem + '.subtitled.' + ext)
        args = [ffmpeg_path(), '-y', '-i', str(media)]
        for subtitle in subtitles:
            args += ['-i', str(subtitle)]
        args += ['-map', '0']
        for index, subtitle in enumerate(subtitles, 1):
            args += ['-map', f'{index}:0', f'-metadata:s:s:{index - 1}', f'language={subtitle.suffixes[-2][1:]}']
        args += ['-c', 'copy', '-c:s', 'mov_text' if ext == 'mp4' else 'webvtt', str(destination)]
        result = subprocess.run(args, capture_output=True, text=True, creationflags=(0x08000000 if os.name == 'nt' else 0))
        if result.returncode:
            destination.unlink(missing_ok=True)
            raise RuntimeError(result.stderr[-1500:])
        os.replace(destination, media)
