import html
import os
import re
from datetime import datetime
from typing import List, Literal
from urllib.parse import urlparse

import anthropic
import pandas as pd
import requests
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from sheets import append_news, get_existing_urls

load_dotenv()

NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
SEARCH_KEYWORDS = os.getenv("SEARCH_KEYWORDS", "")
MAX_ARTICLES = int(os.getenv("MAX_ARTICLES", "30"))

NAVER_NEWS_URL = "https://naverapihub.apigw.ntruss.com/search/v1/news"
CLAUDE_MODEL = "claude-haiku-4-5"
MIN_DESCRIPTION_LENGTH = 50
TITLE_DEDUP_PREFIX_LENGTH = 20

# 스포츠/연예 전문 매체 도메인 제외 목록. netloc이 이 값들 중 하나로 시작하면 제외된다.
# (예: "sports" -> sports.chosun.com, sportskhan.co.kr 등 모두 걸러짐)
EXCLUDED_DOMAINS = [
    "sports",
    "star.mt.co.kr",
    "enews24.com",
    "tenasia.hankyung.com",
    "xportsnews.com",
    "osen.mt.co.kr",
]

COLUMNS = [
    "날짜",
    "수집일",
    "검색 키워드",
    "기업명",
    "뉴스 제목",
    "원문링크",
    "요약",
    "카테고리",
    "산업",
    "직무",
    "중요도 점수",
    "검토 필요도",
    "review_status",
    "반려 사유",
]

POLITICAL_KEYWORDS = [
    "국회",
    "청문회",
    "후보자",
    "의원",
    "정당",
    "시민사회단체",
    "더불어민주당",
    "국민의힘",
    "오산시장",
]
ENTERTAINMENT_KEYWORDS = [
    "영화",
    "드라마",
    "개봉",
    "배우",
    "감독",
    "예능",
    "가수",
    "앨범",
    "콘서트",
    "음주운전",
    "이혼",
    "연애",
    "방송 출연",
]

claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None


class NewsAnalysis(BaseModel):
    company: str = Field(description="기사에서 언급된 핵심 관련 기업명. 특정할 수 없으면 '기타'")
    summary: List[str] = Field(min_length=3, max_length=3, description="한국어 3줄 요약, 각 항목은 한 문장")
    category: Literal[
        "채용공고",
        "채용설명회/이벤트",
        "사업동향",
        "재무/실적",
        "인사/조직개편",
        "산업/정책 동향",
        "리스크/이슈",
        "기타",
    ] = Field(description="기사 카테고리")
    importance: Literal[1, 2, 3, 4, 5] = Field(description="구직자 관점에서의 중요도 (1: 낮음 ~ 5: 높음)")
    industry: Literal[
        "금융/보험",
        "IT·테크",
        "제조",
        "유통·커머스",
        "헬스케어",
        "바이오·제약",
        "건설",
        "에너지",
        "자동차·모빌리티",
        "뷰티",
        "미디어·엔터",
        "교육",
        "기타",
    ] = Field(description="기사와 가장 관련 있는 산업")
    job_function: List[
        Literal[
            "AI",
            "데이터분석",
            "개발/엔지니어링",
            "연구개발",
            "디자인",
            "운영",
            "영업",
            "마케팅",
            "기획/전략",
            "PM/서비스기획",
            "인사",
            "재무/회계",
            "고객서비스",
            "기타",
        ]
    ] = Field(
        description=(
            "기사에 명시적으로 언급된 직무만 선택. 여러 개면 리스트에 모두 포함하고, "
            "기사에 직무가 명시되어 있지 않으면 빈 리스트로 응답"
        )
    )
    review_priority: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "이 기사가 취업/기업분석 관련 내용이 맞다는 전제하에, 카테고리·산업·직무·중요도 같은 "
            "세부 분류를 판단하기 얼마나 애매한지 (0: 전혀 애매하지 않음, 1: 매우 애매함). "
            "기사 내용 자체가 취업뉴스와 무관한지 여부와는 별개이며, 오직 분류 판단의 애매함만 반영할 것"
        ),
    )


def strip_html(text: str) -> str:
    text = re.sub(r"<.*?>", "", text or "")
    return html.unescape(text).strip()


def format_pub_date(pub_date: str) -> str:
    try:
        return datetime.strptime(pub_date, "%a, %d %b %Y %H:%M:%S %z").strftime("%Y-%m-%d")
    except ValueError:
        return pub_date


def fetch_naver_news(keyword: str, display: int) -> list[dict]:
    headers = {
        "X-NCP-APIGW-API-KEY-ID": NAVER_CLIENT_ID,
        "X-NCP-APIGW-API-KEY": NAVER_CLIENT_SECRET,
    }
    params = {"query": keyword, "display": min(display, 100), "sort": "date"}

    response = requests.get(NAVER_NEWS_URL, headers=headers, params=params, timeout=10)
    response.raise_for_status()
    return response.json().get("items", [])


CATEGORY_GUIDE = """\
- 채용공고: 실제 공채/수시채용 소식
- 채용설명회/이벤트: 채용설명회, 취업박람회, 잡페어, 취업 특강, 산학협력 프로그램
- 사업동향: 신사업 진출, 신제품/서비스 출시, M&A, 파트너십, 해외 진출
- 재무/실적: 실적 발표, 매출/영업이익, 투자 유치, 주가 관련
- 인사/조직개편: 임원 인사, CEO 교체, 조직개편, 신설 부서
- 산업/정책 동향: 특정 기업이 아닌 업계 전반 트렌드, 정부 정책/규제 변화
- 리스크/이슈: 소송, 노사 갈등, 논란, 제재
- 기타: 위 어디에도 안 맞는 것 (단신, 사진뉴스, 관련성 낮은 기사)"""

IMPORTANCE_GUIDE = """\
- 5점: 산업 전반에 영향을 주는 대형 이슈(대규모 M&A, 신사업 진출, 주요 정책 변화, 조직 대개편) — 채용 사이트에서 얻기 어려운 정보
- 4점: 특정 기업의 유의미한 변화(실적, 신제품, 리더십 교체) 또는 채용 사이트에서 얻기 어려운 구체적 채용 세부정보
- 3점: 일반적인 산업 트렌드 기사 또는 채용 사이트에서도 흔히 볼 수 있는 수준의 공채 소식
- 2점: 간접적으로만 관련
- 1점: 거의 무관"""

REVIEW_REASON_GUIDE = {
    "노이즈(잘못 수집됨)": "검색 키워드가 우연히 겹쳐서 걸린, 명백히 잘못 수집된 기사",
    "관심 분야 아님": "관련은 있지만 지금 관심 산업·직무가 아닌 기사",
    "중복": "이미 비슷한 내용의 다른 기사가 있는 경우",
    "AI 오류(사실과 다름)": "AI 요약이나 분류 내용이 원문과 다르거나 사실이 아닌 내용을 포함하는 경우",
    "기타": "위에 해당하지 않는 경우",
}


def analyze_with_claude(title: str, description: str) -> NewsAnalysis:
    prompt = (
        "다음은 취업/채용 관련 뉴스 기사입니다. 이 기사를 분석해주세요.\n\n"
        f"제목: {title}\n"
        f"내용: {description}\n\n"
        "카테고리는 아래 8개 중 기사 내용에 가장 적합한 하나를 선택하세요.\n"
        f"{CATEGORY_GUIDE}\n\n"
        "중요도 점수는 아래 기준에 따라 매기세요.\n"
        f"{IMPORTANCE_GUIDE}\n\n"
        "기사가 사진 설명이나 단순 행사 스케치처럼 실질적 정보가 없으면 "
        "카테고리를 '기타'로, 중요도를 1점으로 매겨주세요.\n"
        "요약을 작성할 때 주어진 정보에 명시되지 않은 사실(인명, 수치, 날짜 등)을 "
        "추측하거나 지어내지 마세요. 확실하지 않으면 해당 정보를 생략하세요.\n"
        "review_priority는 오직 이 기사가 취업/기업분석 관련 내용이 맞다는 전제하에, "
        "세부 분류(카테고리, 산업, 직무, 중요도)를 판단하기 애매한 정도만 나타내야 합니다. "
        "기사 내용 자체가 취업뉴스와 명백히 무관한 경우는 review_priority와 별개 문제이니 혼동하지 마세요.\n"
        "반드시 한국어로 답변하세요."
    )

    response = claude_client.messages.parse(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
        output_format=NewsAnalysis,
    )
    return response.parsed_output


RULE_FILTER_KEYWORDS = POLITICAL_KEYWORDS + ENTERTAINMENT_KEYWORDS


def is_rule_filtered(title: str, description: str) -> bool:
    text = f"{title} {description}"
    return any(keyword in text for keyword in RULE_FILTER_KEYWORDS)


def is_excluded_domain(link: str) -> bool:
    domain = urlparse(link).netloc.lower()
    return any(domain.startswith(excluded) for excluded in EXCLUDED_DOMAINS)


def collect() -> pd.DataFrame:
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        raise RuntimeError("NAVER_CLIENT_ID / NAVER_CLIENT_SECRET이 .env에 설정되어 있지 않습니다.")
    if not claude_client:
        raise RuntimeError("ANTHROPIC_API_KEY가 .env에 설정되어 있지 않습니다.")

    keywords = [k.strip() for k in SEARCH_KEYWORDS.split(",") if k.strip()]
    if not keywords:
        raise RuntimeError("SEARCH_KEYWORDS가 .env에 설정되어 있지 않습니다.")

    seen_urls = get_existing_urls()
    collected_at = datetime.now().strftime("%Y-%m-%d")

    rows = []
    for keyword in keywords:
        print(f"[수집] 키워드 '{keyword}' 뉴스 검색 중...")
        try:
            items = fetch_naver_news(keyword, MAX_ARTICLES)
        except requests.exceptions.RequestException as e:
            print(f"[에러] 네이버 뉴스 API 호출 실패 (키워드: {keyword}): {e}")
            continue

        seen_title_prefixes = set()

        for item in items:
            title = strip_html(item.get("title", ""))
            description = strip_html(item.get("description", ""))
            link = item.get("originallink") or item.get("link", "")
            pub_date = format_pub_date(item.get("pubDate", ""))

            if link in seen_urls:
                print(f"[스킵] 이미 저장된 기사: {title!r}")
                continue

            title_prefix = title.strip()[:TITLE_DEDUP_PREFIX_LENGTH]
            if title_prefix and title_prefix in seen_title_prefixes:
                print(f"[스킵] 같은 키워드 내 유사 제목 기사: {title!r}")
                continue
            seen_title_prefixes.add(title_prefix)

            if len(description) < MIN_DESCRIPTION_LENGTH:
                print(f"[스킵] 설명이 너무 짧은 기사(사진/단신 추정): {title!r}")
                continue

            if is_excluded_domain(link):
                print(f"[규칙 기반 제외] 스포츠/연예 매체 도메인: {title!r} ({link})")
                continue

            if is_rule_filtered(title, description):
                print(f"[규칙 기반 제외] 정치/연예 키워드 감지: {title!r}")
                continue

            try:
                analysis = analyze_with_claude(title, description)
            except anthropic.APIError as e:
                print(f"[에러] Claude API 호출 실패, 기사 건너뜀: {title!r} ({e})")
                continue
            except (ValueError, TypeError, KeyError) as e:
                print(f"[에러] Claude 응답 형식이 올바르지 않음, 기사 건너뜀: {title!r} ({e})")
                continue

            seen_urls.add(link)

            rows.append(
                {
                    "날짜": pub_date,
                    "수집일": collected_at,
                    "검색 키워드": keyword,
                    "기업명": analysis.company,
                    "뉴스 제목": title,
                    "원문링크": link,
                    "요약": "\n".join(f"- {line}" for line in analysis.summary),
                    "카테고리": analysis.category,
                    "산업": analysis.industry,
                    "직무": ", ".join(analysis.job_function),
                    "중요도 점수": analysis.importance,
                    "검토 필요도": analysis.review_priority,
                    "review_status": "pending",
                    "반려 사유": "",
                }
            )

    return pd.DataFrame(rows, columns=COLUMNS)


def main():
    df = collect()

    if df.empty:
        print("수집된 기사가 없습니다.")
        return

    print(f"총 {len(df)}건의 기사를 분석했습니다. 시트에 저장합니다...")
    try:
        append_news(df)
    except Exception as e:
        print(f"[에러] 시트 저장 실패: {e}")
        return

    print("시트 저장 완료.")


if __name__ == "__main__":
    main()
