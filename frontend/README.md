# ArchiveTube Frontend

ArchiveTube의 Vue 3 사용자 인터페이스입니다. Vite와 SCSS를 사용하며, `pywebview`를 통해 Python 백엔드 API와 통신합니다.

```bash
npm install
npm run dev
```

프로덕션 프런트엔드 빌드는 다음 명령으로 생성합니다.

```bash
npm run build
```

`npm test`는 선택 범위, 필터 밖 선택 유지, URL 추출 및 표시 값 테스트를 실행합니다.

Python 없이 브라우저에서 실행하면 백엔드 미연결 안내가 표시됩니다. UI 개발용 모의 데이터는 개발 서버에 한해 `/?demo=1`을 명시적으로 지정해야 활성화됩니다. 프로덕션에는 데모 코드가 포함되지 않습니다.

`App.vue`가 브리지 연결/전체 상태 복원/변경 순번을 관리하고, `MediaCard`는 항목 선택, `DownloadOptions`는 형식과 보관 옵션, `JobCard`는 큐와 기록, `SettingsPanel`은 기본 설정을 담당합니다. 상태의 기준은 Python이며 클립보드·폴더 열기도 브리지를 이용합니다.
