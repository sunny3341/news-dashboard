import os

import gspread
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

SERVICE_ACCOUNT_FILE = "service_account.json"
SHEET_URL = os.getenv("SHEET_URL", "")


def _get_service_account_secret() -> dict | None:
    """Streamlit Cloud의 st.secrets에 등록된 서비스 계정 정보를 반환합니다.

    로컬 개발 환경처럼 secrets.toml이 없으면 None을 반환해 파일 기반 인증으로
    넘어가도록 합니다.
    """
    try:
        if "gcp_service_account" in st.secrets:
            return dict(st.secrets["gcp_service_account"])
    except Exception:
        return None

    return None


def get_worksheet(worksheet_name: str | None = None) -> gspread.Worksheet:
    """서비스 계정으로 인증하고 SHEET_URL의 워크시트를 반환합니다.

    Streamlit Cloud에 배포된 경우 st.secrets["gcp_service_account"]를 사용하고,
    로컬 개발 환경에서는 기존처럼 service_account.json 파일을 읽습니다.
    worksheet_name을 지정하지 않으면 첫 번째 시트를 사용합니다.
    """
    if not SHEET_URL:
        raise RuntimeError("SHEET_URL이 .env에 설정되어 있지 않습니다.")

    service_account_secret = _get_service_account_secret()
    if service_account_secret:
        client = gspread.service_account_from_dict(service_account_secret)
    else:
        client = gspread.service_account(filename=SERVICE_ACCOUNT_FILE)

    spreadsheet = client.open_by_url(SHEET_URL)

    if worksheet_name:
        return spreadsheet.worksheet(worksheet_name)
    return spreadsheet.sheet1


def get_existing_urls(worksheet_name: str | None = None) -> set[str]:
    """시트의 '원문링크' 컬럼에 이미 저장된 URL 집합을 반환합니다."""
    worksheet = get_worksheet(worksheet_name)
    values = worksheet.get_all_values()

    if not values or "원문링크" not in values[0]:
        return set()

    url_col = values[0].index("원문링크")
    return {row[url_col] for row in values[1:] if len(row) > url_col and row[url_col]}


def append_news(df, worksheet_name: str | None = None) -> None:
    """뉴스 DataFrame을 시트 맨 아래에 추가합니다. 시트가 비어 있으면 헤더도 씁니다."""
    worksheet = get_worksheet(worksheet_name)

    if not worksheet.get_all_values():
        worksheet.append_row(df.columns.tolist())

    worksheet.append_rows(df.values.tolist())


def get_all_news(worksheet_name: str | None = None) -> pd.DataFrame:
    """시트의 전체 데이터를 DataFrame으로 반환합니다.

    각 행이 실제로 위치한 시트 행 번호(헤더 포함, 1-indexed)를 '_row' 컬럼에 담아
    이후 update_row 호출 시 사용할 수 있게 합니다.
    """
    worksheet = get_worksheet(worksheet_name)
    records = worksheet.get_all_records()
    df = pd.DataFrame(records)

    if not df.empty:
        df["_row"] = range(2, len(df) + 2)

    return df


def ensure_columns(columns: list[str], worksheet_name: str | None = None) -> None:
    """시트 헤더에 없는 컬럼을 오른쪽 끝에 추가합니다."""
    worksheet = get_worksheet(worksheet_name)
    header = worksheet.row_values(1)

    missing = [c for c in columns if c not in header]
    if not missing:
        return

    start_col = len(header) + 1
    for offset, column_name in enumerate(missing):
        worksheet.update_cell(1, start_col + offset, column_name)


def update_row(row_number: int, values: dict, worksheet_name: str | None = None) -> None:
    """시트의 row_number(헤더 포함, 1-indexed) 행에서 values에 있는 컬럼들만 업데이트합니다."""
    worksheet = get_worksheet(worksheet_name)
    header = worksheet.row_values(1)

    for column_name, value in values.items():
        if column_name not in header:
            continue
        col_index = header.index(column_name) + 1
        worksheet.update_cell(row_number, col_index, value)


def update_review_status(row_number: int, status: str, worksheet_name: str | None = None) -> None:
    """review_status 컬럼만 업데이트하는 헬퍼."""
    update_row(row_number, {"review_status": status}, worksheet_name)


if __name__ == "__main__":
    ws = get_worksheet()
    print(f"연결 성공: '{ws.spreadsheet.title}' / 시트 '{ws.title}'")
