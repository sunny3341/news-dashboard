# 취업 뉴스 자동 리포트

키워드(취업, 채용, 공채 등) 기반으로 관련 뉴스를 자동으로 수집해 보여주는 Streamlit 대시보드입니다.

## 기능

- [NewsAPI](https://newsapi.org)를 통한 키워드 기반 뉴스 검색
- 검색 키워드 / 기간 / 기사 수 조절
- 결과를 CSV로 다운로드

## 프로젝트 구조

```
news_dashboard/
├── app.py            # Streamlit 앱 진입점
├── requirements.txt  # 파이썬 패키지 목록
├── .env.example      # 환경 변수 예시 파일
└── README.md
```

## 시작하기

### 1. 가상환경(venv) 세팅

**Windows (PowerShell)**

```powershell
# 가상환경 생성
python -m venv venv

# 가상환경 활성화
.\venv\Scripts\Activate.ps1

# (만약 스크립트 실행 정책 오류가 나면 아래 명령을 관리자 권한 없이 한 번 실행)
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

**macOS / Linux**

```bash
python3 -m venv venv
source venv/bin/activate
```

가상환경을 비활성화하려면 `deactivate` 명령을 사용합니다.

### 2. 패키지 설치

```bash
pip install -r requirements.txt
```

### 3. 환경 변수 설정

`.env.example` 파일을 복사해 `.env` 파일을 만들고, 발급받은 API 키를 입력합니다.

```powershell
copy .env.example .env
```

```bash
cp .env.example .env
```

`.env` 파일 내용:

```
NEWSAPI_KEY=your_newsapi_key_here
SEARCH_KEYWORDS=취업,채용,공채,인턴,신입
MAX_ARTICLES=30
```

- `NEWSAPI_KEY`: [newsapi.org](https://newsapi.org)에서 무료로 발급받을 수 있습니다.

### 4. 앱 실행

```bash
streamlit run app.py
```

브라우저에서 `http://localhost:8501` 로 접속하면 대시보드를 확인할 수 있습니다.

## GitHub Actions로 매일 자동 수집

`.github/workflows/daily.yml`이 매일 한국시간(KST) 오전 9시에 `collect.py`를 자동으로 실행합니다. 저장소의 **Settings → Secrets and variables → Actions**에서 아래 Secrets를 등록해야 합니다.

| Secret 이름 | 값 |
|---|---|
| `NAVER_CLIENT_ID` | 네이버 API HUB Client ID |
| `NAVER_CLIENT_SECRET` | 네이버 API HUB Client Secret |
| `ANTHROPIC_API_KEY` | Claude API 키 |
| `SHEET_URL` | 결과를 저장할 Google Sheets URL |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | `service_account.json` 파일 내용 전체를 그대로 붙여넣기 |

`SEARCH_KEYWORDS`, `MAX_ARTICLES`는 민감 정보가 아니라서 워크플로우 파일(`daily.yml`) 안에 직접 값이 들어 있습니다. 바꾸고 싶으면 그 파일을 직접 수정하면 됩니다. `Actions` 탭에서 `workflow_dispatch`로 수동 실행해 정상 동작하는지 먼저 확인해보는 것을 추천합니다.

## TODO

- [ ] 정기 실행(스케줄러)으로 리포트 자동 생성/전송 (예: 매일 아침 이메일 또는 슬랙 발송)
- [ ] 키워드별 뉴스 트렌드 시각화 추가
- [ ] NewsAPI 외 추가 뉴스 소스(RSS 등) 연동
