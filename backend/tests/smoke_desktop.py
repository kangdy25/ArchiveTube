"""Opt-in native WebView smoke test; uses a temporary DB and offline media fixtures.

Run after `npm run build`: backend/venv/bin/python backend/tests/smoke_desktop.py
"""
import json
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import webview
from main import BackendApi
from media import DownloadRunner, MediaService
from test_main import FakeYDL


def main():
    failures = []
    with tempfile.TemporaryDirectory(prefix='archivetube-smoke-') as temporary:
        api = BackendApi(database=Path(temporary) / 'archive.db', runner=DownloadRunner(FakeYDL), media=MediaService(FakeYDL))
        api.manager.save_settings({'download_dir': temporary})
        window = webview.create_window('ArchiveTube · 검증', str(Path(__file__).resolve().parents[2] / 'frontend/dist/index.html'), js_api=api, width=1100, height=800)
        api.window = window

        def wait_js(expression, timeout=12):
            until = time.monotonic() + timeout
            while time.monotonic() < until:
                if window.evaluate_js(expression): return
                time.sleep(.1)
            raise AssertionError(f'Native UI condition failed: {expression}')

        def click(text):
            window.evaluate_js(f'Array.from(document.querySelectorAll("button")).find(x => x.textContent.trim() === {json.dumps(text)}).click()')

        def run():
            threading.Thread(target=api.dispatch_events, daemon=True).start()
            try:
                wait_js('document.querySelector(".connection-indicator")?.textContent.includes("연결됨")')
                window.evaluate_js('const field = document.querySelector("#url-input"); field.value="https://youtube.com/watch?v=one&list=abc"; field.dispatchEvent(new Event("input", {bubbles:true}))')
                wait_js('!Array.from(document.querySelectorAll("button")).find(x => x.textContent.trim() === "링크 분석").disabled')
                click('링크 분석')
                wait_js('document.querySelectorAll(".playlist-row").length === 3')
                click('선택 해제')
                wait_js('document.querySelector(".download-bar strong").textContent.startsWith("0개")')
                click('전체 선택')
                wait_js('document.querySelector(".download-bar strong").textContent.startsWith("1개")')
                window.evaluate_js('document.querySelector(".download-bar button").click()')
                wait_js('document.querySelector(".status-pill.completed") !== null')
                result = api.get_history()
                assert result['success'] and len(result['jobs']) == 1
                output = Path(result['jobs'][0]['items'][0]['path'])
                assert output.is_file() and output.stat().st_size > 0
                click('설정')
                wait_js('document.querySelector(".settings-layout") !== null')
                window.evaluate_js('const theme = Array.from(document.querySelectorAll("select")).find(x=>Array.from(x.options).some(o=>o.value==="light")); theme.value="light"; theme.dispatchEvent(new Event("change",{bubbles:true}))')
                click('설정 저장')
                wait_js('document.documentElement.dataset.theme === "light"')
                assert api.store.get_settings()['theme'] == 'light'
                print('PASS: native WebView bridge, analysis, selection, offline download, final file, history and settings/theme', flush=True)
            except Exception:
                failures.append(traceback.format_exc())
                print(failures[-1], flush=True)
            finally:
                api.manager.shutdown(); api.store.close(); api._closed = True
                window.destroy()

        webview.start(run, debug=False)
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
