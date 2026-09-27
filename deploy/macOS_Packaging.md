# macOS 앱 패키징

Python 가상환경과 프런트엔드 의존성을 먼저 설치합니다. Node.js 22.12 이상과 FFprobe가 PATH에 필요합니다. 프로젝트 루트에서 실행하세요.

```bash
backend/venv/bin/python -m pip install pyinstaller Pillow
backend/venv/bin/python deploy/build.py
open dist/ArchiveTube.app
```

빌드는 Vue 프로덕션 파일, FFmpeg, FFprobe와 의존 라이브러리, Node, yt-dlp EJS 및 OS 연동 의존성을 포함합니다. 마지막에 앱의 깊은 서명 검사와 **번들 내부 FFmpeg·FFprobe·Node 실행**을 검증합니다.

## 서명과 알림

기본 빌드는 PyInstaller의 암시적 ad-hoc 서명을 사용하는 **로컬 실행용**입니다. `--codesign-identity -`를 명시하면 hardened runtime이 켜져 ad-hoc 라이브러리 로딩이 실패할 수 있으므로 사용하지 않습니다.

배포 인증서가 있다면 `ARCHIVETUBE_SIGNING_IDENTITY`에 서명 이름을 지정할 수 있습니다. 이때 Node JIT용 `deploy/entitlements.plist`를 적용합니다. Developer ID 서명·공증·다른 Mac에서의 Gatekeeper 확인은 별도 배포 절차이며 이번 로컬 빌드로 검증된 것은 아닙니다.

macOS 알림은 앱 번들과 서명이 필요합니다. 설정에서 활성화하여 OS 권한을 허용하고, 시스템 설정의 알림과 집중 모드를 확인하세요. 소스 Python 실행에서는 네이티브 오류를 방지하기 위해 안내 오류를 반환합니다. [desktop-notifier macOS 요구사항](https://desktop-notifier.readthedocs.io/en/latest/#notes-on-macos)을 참고하세요.

`dist/ArchiveTube.app/Contents/MacOS/ArchiveTube --check-notifications`는 사용자 DB·쿠키·다운로드를 건드리지 않고 알림 권한과 테스트 알림 전송만 검사합니다. 결과를 JSON으로 출력하고 검증 창을 닫습니다. OS 권한 거부는 실패로 보고하며 자동으로 우회하지 않습니다.

실행 중인 기존 앱을 보존하며 별도 번들을 만들려면 `ARCHIVETUBE_DIST_DIR`에 원하는 출력 폴더의 절대 경로를 지정하세요. 도구 복사는 임시 파일 생성 후 원자적으로 교체하여 실행 중인 바이너리를 직접 덮어쓰지 않습니다.

## 배포 전 실기 확인

- 새 사용자 데이터에서 분석·다운로드·종료·재시작·명시적 재개
- 권한이 있는 영상의 MP4/WebM/MP3/M4A 재생과 자막 트랙
- 알림 권한 허용/거부, 큐당 한 번 알림, 취소만 한 큐의 알림 억제
- 클립보드 복사/붙여넣기와 앱 복귀 시 중복 제안 억제
- 저장 폴더 접근 거부, 디스크 부족, 외부 파일 삭제 표시
- Windows는 해당 OS에서 별도 빌드 및 실기 확인

현재 실행한 검사와 미확인 항목은 [검증 기록](../docs/VERIFICATION.md)에 구분합니다. DMG 제작과 공증은 빌드 스크립트가 자동 수행하지 않습니다.
