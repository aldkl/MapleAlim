# MapleAlim

메이플스토리 캐릭터별 보스 수익, TODO, 수익 캘린더를 정리하는 웹 앱입니다.

## 로컬 실행

```powershell
python .\server.py
```

브라우저에서 `http://127.0.0.1:8765/`로 접속합니다.

## GitHub Pages

`main` 브랜치에 푸시하면 `.github/workflows/pages.yml`이 정적 화면을 배포합니다. GitHub Pages에서는 Python과 비밀 API 키를 실행할 수 없으므로 캐릭터 검색은 별도 백엔드가 필요합니다. 백엔드 배포 후 `config.js`의 `MAPLE_API_BASE_URL`에 공개 API 주소를 지정합니다.
