"""Validated, JSON-safe settings and stable media identities."""
import os
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse


def default_download_dir():
    try:
        from platformdirs import user_downloads_dir
        return user_downloads_dir()
    except ImportError:
        return str(Path.home() / 'Downloads')


def defaults():
    return {
        'download_dir': default_download_dir(), 'format_type': 'video',
        'video_format': 'mp4', 'video_quality': 'best',
        'audio_format': 'mp3', 'audio_bitrate': 192, 'collision': 'rename',
        'subtitle_mode': 'off', 'subtitle_languages': ['ko', 'en'],
        'auto_subtitles': False, 'save_thumbnail': False,
        'save_description': False, 'save_metadata': False,
        'theme': 'dark', 'reduce_motion': False, 'clipboard_monitor': False,
        'notifications': False, 'cookie_browser': '', 'cookie_profile': '',
    }


ENUMS = {
    'format_type': {'video', 'audio'}, 'video_format': {'mp4', 'webm'},
    'video_quality': {'best', '1080', '720'}, 'audio_format': {'mp3', 'm4a'},
    'audio_bitrate': {128, 192, 320}, 'collision': {'rename', 'skip', 'overwrite'},
    'subtitle_mode': {'off', 'file', 'embed'}, 'theme': {'dark', 'light', 'system'},
    'cookie_browser': {'', 'brave', 'chrome', 'chromium', 'edge', 'firefox',
                       'opera', 'safari', 'vivaldi', 'whale'},
}
TERMINAL = {'completed', 'partial', 'failed', 'cancelled'}
ACTIVE = {'running', 'cancelling'}
ITEM_DONE = {'completed', 'skipped'}


def settings_with(values=None, base=None):
    result = dict(base or defaults())
    for key, value in (values or {}).items():
        if key not in defaults():
            raise ValueError(f'알 수 없는 설정: {key}')
        if key in ENUMS and (isinstance(value, (dict, list)) or value not in ENUMS[key]):
            raise ValueError(f'올바르지 않은 설정: {key}')
        if isinstance(defaults()[key], bool) and not isinstance(value, bool):
            raise ValueError(f'올바르지 않은 설정: {key}')
        result[key] = value
    directory = result['download_dir']
    if not isinstance(directory, str) or not directory.strip() or not os.path.isabs(os.path.expanduser(directory)):
        raise ValueError('저장 폴더는 절대 경로여야 합니다.')
    result['download_dir'] = os.path.abspath(os.path.expanduser(directory))
    langs = result['subtitle_languages']
    if not isinstance(langs, list) or len(langs) > 30 or any(
        not isinstance(lang, str) or not re.fullmatch(r'[a-zA-Z0-9-]{1,35}', lang) for lang in langs
    ):
        raise ValueError('자막 언어 코드를 확인하세요. 예: ko, en, ja')
    result['subtitle_languages'] = list(dict.fromkeys(langs))
    if result['subtitle_mode'] != 'off' and not langs:
        raise ValueError('자막 언어를 하나 이상 선택하세요.')
    if not isinstance(result['cookie_profile'], str) or len(result['cookie_profile']) > 1024:
        raise ValueError('브라우저 프로필을 확인하세요.')
    return result


def parse_youtube_url(value):
    if not isinstance(value, str):
        raise ValueError('YouTube URL을 입력하세요.')
    value = value.strip()
    parsed = urlparse(value)
    host = (parsed.hostname or '').lower()
    if parsed.scheme not in {'http', 'https'} or host not in {
        'youtube.com', 'www.youtube.com', 'm.youtube.com', 'music.youtube.com',
        'youtu.be', 'www.youtu.be',
    } or parsed.username or parsed.password:
        raise ValueError('YouTube 영상 또는 재생목록 URL을 입력하세요.')
    query = parse_qs(parsed.query)
    video_id = (query.get('v') or [None])[0]
    parts = parsed.path.strip('/').split('/')
    if host.endswith('youtu.be'):
        video_id = parts[0]
    elif parts[0] in {'shorts', 'live', 'embed'} and len(parts) > 1:
        video_id = parts[1]
    playlist_id = (query.get('list') or [None])[0]
    for identifier in (video_id, playlist_id):
        if identifier and not re.fullmatch(r'[A-Za-z0-9_-]+', identifier):
            raise ValueError('URL의 영상 또는 재생목록 ID가 올바르지 않습니다.')
    if not video_id and not playlist_id:
        raise ValueError('영상 또는 재생목록 링크가 필요합니다. 채널 링크는 지원하지 않습니다.')
    return video_id, playlist_id


def video_url(identifier):
    return f'https://www.youtube.com/watch?v={identifier}'


def extension(options):
    return options['video_format'] if options['format_type'] == 'video' else options['audio_format']


def safe_name(value):
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', str(value or '제목 없음'))
    # Leave room for playlist prefixes, language suffixes and collision numbers on
    # filesystems with a 255-byte component limit (Korean titles use 3 bytes/char).
    value = value.strip(' .').encode('utf-8')[:180].decode('utf-8', errors='ignore').rstrip(' .') or '제목 없음'
    if value.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *[f'COM{i}' for i in range(10)], *[f'LPT{i}' for i in range(10)]}:
        value = '_' + value
    return value


def safe_error(error):
    text = re.sub(r'\x1b\[[0-9;]*m', '', str(error))
    text = re.sub(r'https?://[^\s]+', '[URL]', text)
    text = re.sub(r'(?i)(cookie|authorization|token|password)(\s*[:=]\s*)[^\s,;]+', r'\1\2[숨김]', text)
    return text[-4000:]


def error_message(error):
    detail = safe_error(error)
    lowered = detail.lower()
    if any(word in lowered for word in ['cookie', 'keychain', 'decrypt', 'database is locked']):
        return '브라우저 쿠키를 읽지 못했습니다. 브라우저·프로필과 OS 접근 권한을 확인하세요.'
    if any(word in lowered for word in ['sign in', 'private', 'age-restricted', 'login']):
        return '접근 제한 영상입니다. 설정에서 접근 권한이 있는 브라우저 세션을 선택하세요.'
    if any(word in lowered for word in ['no space', 'disk full', 'enospc']):
        return '저장 공간이 부족합니다. 공간을 확보하거나 저장 폴더를 변경하세요.'
    if any(word in lowered for word in ['permission', 'read-only', 'access is denied']):
        return '저장 폴더에 접근할 수 없습니다. 폴더와 쓰기 권한을 확인하세요.'
    if any(word in lowered for word in ['requested format', 'format is not available', 'no video formats']):
        return '선택한 형식이나 화질을 제공하지 않는 영상입니다. 다른 형식 또는 화질로 다시 시도하세요.'
    if any(word in lowered for word in ['timed out', 'timeout', 'network', 'connection', 'unable to download', 'http error']):
        return '네트워크 요청에 실패했습니다. 인터넷 연결을 확인하고 다시 시도하세요.'
    if any(word in lowered for word in ['ffmpeg', 'ffprobe', 'postprocessing', 'conversion', 'merge failed']):
        return '미디어 변환에 실패했습니다. 앱 실행 환경을 확인하거나 다른 형식으로 다시 시도하세요.'
    if any(word in lowered for word in ['unavailable', 'removed', 'not available', 'not found']):
        return '영상을 찾거나 접근할 수 없습니다. 원본 URL과 공개 상태를 확인하세요.'
    return detail if re.search(r'[가-힣]', detail) else '작업을 완료하지 못했습니다. 다시 시도하거나 오류 상세를 확인하세요.'
