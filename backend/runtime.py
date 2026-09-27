import os
import shutil
import sys
from pathlib import Path


def resource_path(relative):
    root = getattr(sys, '_MEIPASS', str(Path(__file__).resolve().parent.parent))
    return str(Path(root) / relative)


def binary(name):
    filename = name + ('.exe' if os.name == 'nt' else '')
    bundled = Path(resource_path('bin')) / filename
    return str(bundled) if bundled.is_file() else shutil.which(name)


def ffmpeg_path():
    path = binary('ffmpeg')
    if path:
        return path
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def runtime_options(settings):
    options = {'quiet': True, 'no_warnings': True, 'noprogress': True,
               'socket_timeout': 20, 'retries': 3, 'fragment_retries': 3,
               'ffmpeg_location': ffmpeg_path()}
    node = binary('node')
    if node:
        options['js_runtimes'] = {'node': {'path': node}}
    if settings.get('cookie_browser'):
        options['cookiesfrombrowser'] = (settings['cookie_browser'], settings.get('cookie_profile') or None)
    return options
