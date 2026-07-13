# MapleAlim

메이플스토리 캐릭터별 보스 수익, TODO, 수익 캘린더를 정리하는 웹 앱입니다.

## 로컬 실행

```powershell
python .\server.py
```

브라우저에서 `http://127.0.0.1:8765/`로 접속합니다.

## GitHub Pages

`main` 브랜치에 푸시하면 `.github/workflows/pages.yml`이 정적 화면을 배포합니다. GitHub Pages에서는 Python과 비밀 API 키를 실행할 수 없으므로 캐릭터 검색은 별도 백엔드가 필요합니다. 백엔드 배포 후 `config.js`의 `MAPLE_API_BASE_URL`에 공개 API 주소를 지정합니다.

## Vercel API

`api/character.py`는 Vercel Python Function으로 캐릭터 검색 API를 제공합니다. Vercel 프로젝트 환경변수에 `NEXON_OPEN_API_KEY`를 등록해야 하며, API 키는 Git 저장소나 프론트엔드에 넣지 않습니다.
