# 검증 기록

검증 환경: macOS arm64, Python 3.13.2, Vue 3 / Vite 7.3.1. 자동 테스트는 임시 SQLite와 모의 yt-dlp를 사용하며 실제 YouTube 다운로드를 반복하지 않습니다.

## 통과한 검사

- 백엔드 32개 테스트: 설정·큐 복원, 안정적인 영상 ID, 순차 실행, 순서 변경, 다음 작업 일시정지, 변환 중 취소, 실패 항목 재시도, 충돌 정책, 저장 권한 오류, 파일 유무, 삭제/비공개 항목 판별, 후처리 실패의 성공 오판 방지.
- 큐 종료 알림 1회와 취소 전용 큐 알림 억제; 클립보드 어댑터·Windows 폴더 열기 분기는 모의 테스트.
- 실제 FFmpeg로 작은 로컬 영상 생성, MP3/M4A 변환 및 MP4/WebM 자막 삽입, FFprobe로 결과 확인.
- 프런트엔드 5개 테스트: 원래 순번 범위, 필터 밖 선택 유지, 처음/마지막 선택, YouTube URL 추출, 알 수 없는 시간/전송량 표시.
- Vite 프로덕션 빌드. 프로덕션 산출물에서 개발 데모 제외.
- 네이티브 macOS WebView 스모크: 실제 Python 브리지 연결, 혼합 URL 분석, 전체 선택/해제, 오프라인 큐 실행, 최종 파일·기록, 설정 및 라이트 테마 저장.
- 개발 브라우저: 재생목록 표시·범위 선택, M4A 비트레이트 숨김, 모의 큐, 라이트 테마 저장, 720×600 설정 화면의 가로 넘침 없음, 브라우저 오류 없음.
- macOS `.app` 생성, 깊은 서명 검사, 번들 내부 FFmpeg·FFprobe·Node 실행, 실제 앱의 연결됨/다운로드/설정 화면 확인.
- README 미리보기는 새 개발 데모 화면을 촬영한 이미지이며 실제 다운로드 결과를 의미하지 않습니다.

## 아직 완료로 간주하지 않는 실기 항목

- macOS 알림: 격리된 서명 번들의 `--check-notifications`에서 OS가 `UNErrorDomain code=1: Notifications are not allowed for this application`을 반환했습니다. 앱이 권한 거부를 올바르게 안내하는 것은 확인했지만 실제 알림 표시는 미확인입니다. 시스템 알림 권한을 허용한 환경에서 재확인해야 합니다. 권한을 강제로 변경하지 않았습니다.
- Windows 실제 앱 빌드·WebView2·클립보드·WinRT 알림·폴더 선택은 Windows 기기에서 확인해야 합니다. 모의 OS 분기 테스트와 실제 검증은 구분합니다.
- 실제 로그인 쿠키 접근, 비공개/연령 제한 영상, 외부 YouTube 전송은 계정과 접근 권한이 있는 미디어로 확인해야 합니다. 사용자 브라우저 쿠키를 자동으로 읽지 않았습니다.
- Developer ID 배포 서명·공증·다른 Mac에서의 Gatekeeper, DMG 배포는 미검증입니다.

## 재실행

```bash
backend/venv/bin/python -m unittest discover -s backend/tests -v
npm --prefix frontend test
npm --prefix frontend run build
backend/venv/bin/python backend/tests/smoke_desktop.py
backend/venv/bin/python deploy/build.py
```

실기 확인 시 별도 `ARCHIVETUBE_DATABASE` 경로와 임시 다운로드 폴더를 사용하세요. 실제 사용자 기록이나 파일을 테스트 목적으로 삭제하지 않습니다.

이번 작업의 최신 실행 번들은 기존에 열려 있던 앱을 덮어쓰지 않도록 `dist/release/ArchiveTube.app`에 생성했습니다. 일반 빌드의 기본 출력은 계속 `dist/ArchiveTube.app`입니다.
