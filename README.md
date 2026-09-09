# 취업 뉴스 자동 리포트

🔗 **배포 링크: [job-news-dashboard.streamlit.app](https://job-news-dashboard.streamlit.app)**

## 프로젝트 소개

취업 준비 중 매일 관심 기업/산업 뉴스를 수동으로 찾아보는 반복 작업을 자동화하기 위해 만든 프로젝트입니다. 생성형 AI(Claude)를 활용해 **뉴스 수집 → 요약 → 분류**를 자동화하고, AI가 놓치거나 잘못 판단할 수 있는 부분을 사람이 검증하는 **Human Review 프로세스**를 함께 설계했습니다.

## 아키텍처

```
네이버 뉴스 검색 API (국내 뉴스 수집)
        │
        ▼
Claude API (한국어 요약 · 카테고리 8종 · 산업 13종 · 직무 · 중요도 1~5점 · 검토 필요도 분석)
        │
        ▼
Google Sheets 저장 (서비스 계정 인증)
        │
        ▼
GitHub Actions (매일 자동 실행, KST 오전 9시)
        │
        ▼
Streamlit 대시보드 (시각화 및 Human Review)
```

## 주요 기능

- **Human Review 워크플로우**: 기사별 승인/수정/반려, 반려 사유 기록, 여러 기사를 한 번에 처리하는 일괄 처리 기능
- **검토 필요도 지표**: AI가 자신의 분류 결과에 대한 확신도를 스스로 매겨, 사람이 어떤 기사를 우선 검토해야 할지 알려주는 지표
- **규칙 기반 사전 필터**: 정치/연예 등 취업뉴스와 무관한 콘텐츠를 Claude API 호출 전에 키워드·도메인 기준으로 차단해 비용 절감
- **세분화된 분류 체계**: 8개 카테고리 × 13개 산업 × 직무(복수 선택 가능, 14종)
- **AI 성능/검토 현황 탭**: 반려율 추이, 검토 필요도 분포, 검토 필요도 구간별 반려율 등 AI 판단의 신뢰도를 검증하기 위한 시각화
- **뉴스 인사이트 탭**: 기업별 언급 빈도, 산업 × 카테고리 히트맵, 산업별 핵심 이슈 AI 요약

## 기술 스택

- **Python** / **Streamlit** — 대시보드
- **Anthropic Claude API** — 뉴스 요약 및 분류
- **네이버 뉴스 검색 API (NAVER API HUB)** — 뉴스 수집
- **Google Sheets API (gspread)** — 데이터 저장소
- **GitHub Actions** — 매일 자동 수집 스케줄링

## 트러블슈팅 및 개선 과정

- **AI 할루시네이션 발견**: 요약 과정에서 AI가 실존하지 않는 인물명을 지어내는 사례를 발견해, 프롬프트에 "명시되지 않은 사실을 추측하거나 지어내지 말 것"이라는 지침을 추가했습니다.
- **검토 효율화**: 처음엔 수집된 기사를 전수 검토했지만, 검토 필요도 지표를 도입하고 이 값이 실제 반려율과 상관관계가 있는지 검증한 뒤 우선순위 기반 검토 방식으로 개선했습니다.
- **노이즈 필터링**: 검색 키워드가 취업과 무관한 기사(정치인 동정, 연예인 소식 등)와 우연히 겹쳐 수집되는 문제를 발견해, Claude 호출 전에 걸러내는 규칙 기반 사전 필터를 도입했습니다.
- **배포 환경 인증 분기**: 로컬에서는 `service_account.json` 파일로, Streamlit Cloud에서는 파일이 없어 `st.secrets`로 인증하도록 분기 처리해 배포 환경 이슈를 해결했습니다.

## 개발 방식

Claude Code(AI 코딩 에이전트)를 활용해 개발했습니다. 요구사항을 정의하고, 결과를 직접 확인·검증하면서 기능을 반복적으로 구현하고 개선하는 방식으로 진행했습니다.

## 프로젝트 구조

```
news_dashboard/
├── app.py                      # Streamlit 대시보드
├── collect.py                  # 뉴스 수집·분석·저장 스크립트
├── sheets.py                   # Google Sheets 연동
├── requirements.txt            # 파이썬 패키지 목록
├── .env.example                # 환경 변수 예시 파일
├── service_account.json        # Google 서비스 계정 키 (직접 발급, git에는 포함되지 않음)
└── .github/workflows/daily.yml # 매일 자동 수집 GitHub Actions 워크플로우
```

## 로컬 실행 방법

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

필요한 값:

- `NAVER_CLIENT_ID` / `NAVER_CLIENT_SECRET`: [NAVER API HUB](https://www.ncloud.com/)에서 발급
- `ANTHROPIC_API_KEY`: [console.anthropic.com](https://console.anthropic.com)에서 발급
- `SHEET_URL`: 결과를 저장할 Google Sheets URL
- `SEARCH_KEYWORDS`, `MAX_ARTICLES`: 검색 키워드와 키워드당 최대 수집 기사 수
- `READ_ONLY_MODE`: `True`로 설정하면 대시보드가 조회 전용으로 동작 (승인/수정/반려·일괄 처리 버튼 숨김)

Google 서비스 계정 키(`service_account.json`)도 프로젝트 루트에 준비해야 합니다. 발급받은 계정 이메일을 대상 Google Sheets 문서에 편집자로 공유해야 합니다.

### 4. 뉴스 수집 실행

```bash
python collect.py
```

### 5. 대시보드 실행

```bash
streamlit run app.py
```

브라우저에서 `http://localhost:8501`로 접속하면 대시보드를 확인할 수 있습니다.

## 매일 자동 수집 (GitHub Actions)

`.github/workflows/daily.yml`이 매일 한국시간(KST) 오전 9시에 `collect.py`를 자동으로 실행합니다. 저장소의 **Settings → Secrets and variables → Actions**에서 아래 Secrets를 등록해야 합니다.

| Secret 이름 | 값 |
|---|---|
| `NAVER_CLIENT_ID` | 네이버 API HUB Client ID |
| `NAVER_CLIENT_SECRET` | 네이버 API HUB Client Secret |
| `ANTHROPIC_API_KEY` | Claude API 키 |
| `SHEET_URL` | 결과를 저장할 Google Sheets URL |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | `service_account.json` 파일 내용 전체를 그대로 붙여넣기 |

`SEARCH_KEYWORDS`, `MAX_ARTICLES`는 민감 정보가 아니라서 워크플로우 파일(`daily.yml`) 안에 직접 값이 들어 있습니다. 바꾸고 싶으면 그 파일을 직접 수정하면 됩니다. `Actions` 탭에서 `workflow_dispatch`로 수동 실행해 정상 동작하는지 먼저 확인해보는 것을 추천합니다.
