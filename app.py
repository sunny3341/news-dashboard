import os
from datetime import datetime

import anthropic
import pandas as pd
import plotly.express as px
import streamlit as st

from collect import CATEGORY_GUIDE, CLAUDE_MODEL, IMPORTANCE_GUIDE, REVIEW_REASON_GUIDE, claude_client
from sheets import ensure_columns, get_all_news, update_row

st.set_page_config(page_title="취업 뉴스 자동 리포트", page_icon="📰", layout="wide")

CATEGORY_COLORS = {
    "채용공고": "#2a78d6",
    "채용설명회/이벤트": "#eb6834",
    "사업동향": "#1baf7a",
    "재무/실적": "#eda100",
    "인사/조직개편": "#e87ba4",
    "산업/정책 동향": "#008300",
    "리스크/이슈": "#4a3aa7",
    "기타": "#898781",
}
CATEGORY_ORDER = list(CATEGORY_COLORS.keys())
REPORT_STATUSES = ["approved", "edited"]
DECIDED_STATUSES = ["approved", "edited", "rejected"]

STATUS_ORDER = ["pending", "approved", "edited", "rejected"]
STATUS_LABELS = {"pending": "검토 대기", "approved": "승인", "edited": "수정됨", "rejected": "반려"}
STATUS_COLORS = {"pending": "#898781", "approved": "#0ca30c", "edited": "#2a78d6", "rejected": "#d03b3b"}

REJECT_REASONS = list(REVIEW_REASON_GUIDE.keys())

SORT_OPTIONS = {
    "중요도 높은순": ("중요도 점수", False),
    "검토 필요도 높은순": ("검토 필요도", False),
    "날짜 최신순": ("날짜", False),
    "날짜 과거순": ("날짜", True),
}

BAR_COLOR = "#2a78d6"
INDUSTRY_SUMMARY_MIN_ARTICLES = 3

READ_ONLY_MODE = os.getenv("READ_ONLY_MODE", "False").strip().lower() == "true"
READ_ONLY_BANNER = "ℹ️ 현재 읽기 전용 모드입니다. 실제 검토(승인/수정/반려)는 별도 환경에서 진행됩니다."


def notify_read_only():
    st.toast("읽기 전용 모드입니다. 실제 반영되지 않았습니다.", icon="ℹ️")


@st.cache_data(ttl=60, show_spinner=False)
def load_data() -> pd.DataFrame:
    df = get_all_news()
    if df.empty:
        return df

    df["날짜"] = pd.to_datetime(df["날짜"], errors="coerce")
    if "중요도 점수" in df.columns:
        df["중요도 점수"] = pd.to_numeric(df["중요도 점수"], errors="coerce")
    if "검토 필요도" in df.columns:
        df["검토 필요도"] = pd.to_numeric(df["검토 필요도"], errors="coerce")

    return df


def refresh():
    load_data.clear()


def sort_dataframe(df: pd.DataFrame, sort_label: str) -> pd.DataFrame:
    column, ascending = SORT_OPTIONS[sort_label]
    return df.sort_values(column, ascending=ascending, na_position="last")


def filter_today(df: pd.DataFrame, checkbox_key: str) -> pd.DataFrame:
    only_today = st.checkbox("오늘 새로 수집된 기사만 보기", key=checkbox_key)
    if only_today and "수집일" in df.columns:
        today_str = datetime.now().strftime("%Y-%m-%d")
        return df[df["수집일"] == today_str]
    return df


def render_info_captions():
    st.caption(
        "검토 필요도: AI가 이 기사의 분류 결과에 대해 사람의 검토가 얼마나 필요하다고 판단했는지 "
        "나타내는 값(0~1). 높을수록 검토가 더 필요합니다"
    )
    st.caption("날짜는 기사가 실제 발행된 날짜이며, 수집일은 이 기사를 자동으로 수집한 날짜입니다")
    st.caption("중요도 점수: 1(참고 수준) ~ 5(핵심 이슈)")
    with st.expander("중요도 판단 기준 자세히 보기"):
        st.markdown(IMPORTANCE_GUIDE)
    with st.expander("카테고리 기준 보기"):
        st.markdown(CATEGORY_GUIDE)
    with st.expander("반려 사유 기준 보기"):
        st.markdown("\n".join(f"- {reason}: {desc}" for reason, desc in REVIEW_REASON_GUIDE.items()))


def compute_rejection_rate(df: pd.DataFrame, group_col: str) -> pd.DataFrame:
    decided = df[df["review_status"].isin(DECIDED_STATUSES)]
    grouped = (
        decided.groupby(group_col)["review_status"]
        .agg(반려율=lambda s: (s == "rejected").mean() * 100, 검토건수="count")
        .reset_index()
    )
    grouped.columns = [group_col, "반려율(%)", "검토건수"]
    return grouped


def render_overview(df: pd.DataFrame):
    st.subheader("전체 현황")
    col1, col2 = st.columns(2)

    with col1:
        st.caption("일별 수집 기사 수")
        daily = (
            df.dropna(subset=["날짜"])
            .groupby(df["날짜"].dt.date)
            .size()
            .reset_index(name="기사 수")
        )
        daily.columns = ["날짜", "기사 수"]

        if daily.empty:
            st.info("날짜 정보가 있는 기사가 없습니다.")
        else:
            fig = px.line(daily, x="날짜", y="기사 수", markers=True)
            fig.update_traces(line_color=BAR_COLOR)
            fig.update_layout(margin=dict(t=10, b=10, l=10, r=10))
            st.plotly_chart(fig, width="stretch")

    with col2:
        st.caption("카테고리별 분포")
        counts = (
            df["카테고리"]
            .value_counts()
            .reindex(CATEGORY_ORDER)
            .dropna()
            .reset_index()
        )
        counts.columns = ["카테고리", "기사 수"]

        if counts.empty:
            st.info("카테고리 정보가 있는 기사가 없습니다.")
        else:
            fig = px.pie(
                counts,
                names="카테고리",
                values="기사 수",
                color="카테고리",
                color_discrete_map=CATEGORY_COLORS,
                category_orders={"카테고리": CATEGORY_ORDER},
            )
            # 카테고리가 8종이라 색상만으로 구분하기 어려울 수 있어 라벨을 항상 표시
            fig.update_traces(textinfo="label+percent")
            fig.update_layout(margin=dict(t=10, b=10, l=10, r=10))
            st.plotly_chart(fig, width="stretch")


def render_review_actions(row: pd.Series, key_prefix: str, show_approve: bool = True):
    """기사 하나에 대한 승인/수정/반려 컨트롤. 어떤 탭에서든 재사용 가능하도록 key_prefix로 위젯 키를 구분한다."""
    row_number = int(row["_row"])

    editor_key = f"{key_prefix}_editor_{row_number}"
    reject_key = f"{key_prefix}_reject_{row_number}"

    if show_approve:
        approve_col, edit_col, reject_col = st.columns(3)
        if approve_col.button("승인", key=f"{key_prefix}_approve_{row_number}", width="stretch"):
            if READ_ONLY_MODE:
                notify_read_only()
            else:
                update_row(row_number, {"review_status": "approved"})
                refresh()
                st.rerun()
    else:
        edit_col, reject_col = st.columns(2)

    if edit_col.button("수정", key=f"{key_prefix}_edit_{row_number}", width="stretch"):
        st.session_state[editor_key] = not st.session_state.get(editor_key, False)

    if reject_col.button("반려", key=f"{key_prefix}_rejectbtn_{row_number}", width="stretch"):
        st.session_state[reject_key] = not st.session_state.get(reject_key, False)

    if st.session_state.get(reject_key):
        reason = st.selectbox("반려 사유", REJECT_REASONS, key=f"{key_prefix}_reason_{row_number}")
        if st.button("반려 확정", key=f"{key_prefix}_confirm_reject_{row_number}"):
            if READ_ONLY_MODE:
                notify_read_only()
            else:
                ensure_columns(["반려 사유"])
                update_row(row_number, {"review_status": "rejected", "반려 사유": reason})
                st.session_state[reject_key] = False
                refresh()
                st.rerun()

    if st.session_state.get(editor_key):
        edit_df = pd.DataFrame(
            [
                {
                    "기업명": row.get("기업명", ""),
                    "카테고리": row.get("카테고리", ""),
                    "중요도 점수": row.get("중요도 점수", ""),
                    "요약": row.get("요약", ""),
                }
            ]
        )
        edited = st.data_editor(
            edit_df,
            column_config={
                "카테고리": st.column_config.SelectboxColumn(options=CATEGORY_ORDER),
                "중요도 점수": st.column_config.NumberColumn(min_value=1, max_value=5, step=1),
            },
            hide_index=True,
            key=f"{key_prefix}_dataeditor_{row_number}",
        )

        if st.button("저장", key=f"{key_prefix}_save_{row_number}"):
            if READ_ONLY_MODE:
                notify_read_only()
            else:
                edited_row = edited.iloc[0]
                update_row(
                    row_number,
                    {
                        "기업명": edited_row["기업명"],
                        "카테고리": edited_row["카테고리"],
                        "중요도 점수": int(edited_row["중요도 점수"]),
                        "요약": edited_row["요약"],
                        "review_status": "edited",
                    },
                )
                st.session_state[editor_key] = False
                refresh()
                st.rerun()


def render_pending_tab(df: pd.DataFrame):
    if READ_ONLY_MODE:
        st.info(READ_ONLY_BANNER)

    render_info_captions()

    pending = df[df["review_status"] == "pending"].copy()
    pending = filter_today(pending, "pending_today_filter")

    if pending.empty:
        st.info("검토 대기 중인 기사가 없습니다.")
        return

    sort_label = st.selectbox("정렬 기준", list(SORT_OPTIONS.keys()), key="pending_sort")
    pending = sort_dataframe(pending, sort_label)

    pending_row_numbers = [int(r) for r in pending["_row"]]
    selected_rows = [rn for rn in pending_row_numbers if st.session_state.get(f"pending_select_{rn}", False)]

    if selected_rows:
        st.info(f"{len(selected_rows)}건 선택됨")
        bulk_col1, bulk_col2, bulk_col3 = st.columns([1, 1, 2])

        if bulk_col1.button("선택 일괄 승인", key="bulk_approve"):
            if READ_ONLY_MODE:
                notify_read_only()
            else:
                for rn in selected_rows:
                    update_row(rn, {"review_status": "approved"})
                refresh()
                st.rerun()

        bulk_reason = bulk_col3.selectbox("일괄 반려 사유", REJECT_REASONS, key="bulk_reject_reason")

        if bulk_col2.button("선택 일괄 반려", key="bulk_reject"):
            if READ_ONLY_MODE:
                notify_read_only()
            else:
                ensure_columns(["반려 사유"])
                for rn in selected_rows:
                    update_row(rn, {"review_status": "rejected", "반려 사유": bulk_reason})
                refresh()
                st.rerun()

        st.divider()

    pending_rows = list(pending.iterrows())
    for i in range(0, len(pending_rows), 2):
        cols = st.columns(2)
        for col, (_, row) in zip(cols, pending_rows[i : i + 2]):
            row_number = int(row["_row"])

            with col, st.container(border=True):
                st.checkbox("선택", key=f"pending_select_{row_number}")
                st.markdown(f"**[{row.get('뉴스 제목', '(제목 없음)')}]({row.get('원문링크', '')})**")
                st.caption(
                    f"{row.get('기업명', '')} · {row.get('카테고리', '')} · "
                    f"중요도 {row.get('중요도 점수', '')} · 검토 필요도 {row.get('검토 필요도', '')}"
                )
                st.write(row.get("요약", ""))

                render_review_actions(row, key_prefix="pending")


def render_all_tab(df: pd.DataFrame):
    render_info_captions()
    st.warning("AI 1차 결과이며 검수되지 않았습니다")

    all_df = filter_today(df, "all_today_filter")

    if all_df.empty:
        st.info("표시할 기사가 없습니다.")
        return

    sort_label = st.selectbox("정렬 기준", list(SORT_OPTIONS.keys()), key="all_sort")
    sorted_df = sort_dataframe(all_df, sort_label)

    st.caption(f"{len(sorted_df)}건")

    display_df = sorted_df.copy()
    display_df["날짜"] = display_df["날짜"].dt.strftime("%Y-%m-%d")

    display_cols = [
        c
        for c in [
            "날짜",
            "수집일",
            "검색 키워드",
            "기업명",
            "뉴스 제목",
            "카테고리",
            "산업",
            "직무",
            "중요도 점수",
            "검토 필요도",
            "review_status",
            "요약",
            "원문링크",
        ]
        if c in display_df.columns
    ]

    st.dataframe(
        display_df[display_cols],
        width="stretch",
        hide_index=True,
        column_config={"원문링크": st.column_config.LinkColumn("원문링크")},
    )


def render_report_tab(df: pd.DataFrame):
    if READ_ONLY_MODE:
        st.info(READ_ONLY_BANNER)

    render_info_captions()

    report_df = df[df["review_status"].isin(REPORT_STATUSES)].copy()

    if report_df.empty:
        st.info("승인되거나 수정된 기사가 아직 없습니다.")
        return

    filter_row1_col1, filter_row1_col2, filter_row1_col3 = st.columns(3)
    filter_row2_col1, filter_row2_col2, filter_row2_col3 = st.columns(3)

    companies = sorted(c for c in report_df["기업명"].dropna().unique() if c)
    selected_companies = filter_row1_col1.multiselect("기업명", companies)

    categories = [c for c in CATEGORY_ORDER if c in report_df["카테고리"].unique()]
    selected_categories = filter_row1_col2.multiselect("카테고리", categories)

    industries = sorted(i for i in report_df["산업"].dropna().unique() if i)
    selected_industries = filter_row1_col3.multiselect("산업", industries)

    job_function_options = sorted(
        {
            jf.strip()
            for jf_str in report_df["직무"].dropna()
            for jf in str(jf_str).split(",")
            if jf.strip()
        }
    )
    selected_job_functions = filter_row2_col1.multiselect("직무", job_function_options)

    valid_dates = report_df["날짜"].dropna()
    date_range = None
    if not valid_dates.empty:
        date_range = filter_row2_col2.date_input(
            "기간",
            value=(valid_dates.min().date(), valid_dates.max().date()),
        )

    sort_label = filter_row2_col3.selectbox("정렬 기준", list(SORT_OPTIONS.keys()), key="report_sort")

    filtered = report_df
    if selected_companies:
        filtered = filtered[filtered["기업명"].isin(selected_companies)]
    if selected_categories:
        filtered = filtered[filtered["카테고리"].isin(selected_categories)]
    if selected_industries:
        filtered = filtered[filtered["산업"].isin(selected_industries)]
    if selected_job_functions:
        selected_set = set(selected_job_functions)
        filtered = filtered[
            filtered["직무"].apply(
                lambda jf_str: bool({jf.strip() for jf in str(jf_str).split(",") if jf.strip()} & selected_set)
            )
        ]
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start, end = date_range
        filtered = filtered[
            filtered["날짜"].dt.date.between(start, end) | filtered["날짜"].isna()
        ]

    filtered = sort_dataframe(filtered, sort_label)

    st.caption(f"{len(filtered)}건")

    display_df = filtered.copy()
    display_df["날짜"] = display_df["날짜"].dt.strftime("%Y-%m-%d")

    display_cols = [
        c
        for c in [
            "날짜",
            "검색 키워드",
            "기업명",
            "뉴스 제목",
            "카테고리",
            "산업",
            "직무",
            "중요도 점수",
            "검토 필요도",
            "review_status",
            "요약",
            "원문링크",
        ]
        if c in display_df.columns
    ]

    st.dataframe(
        display_df[display_cols],
        width="stretch",
        hide_index=True,
        column_config={"원문링크": st.column_config.LinkColumn("원문링크")},
    )

    st.divider()
    st.subheader("상태 변경")

    report_rows = list(filtered.iterrows())
    for i in range(0, len(report_rows), 2):
        cols = st.columns(2)
        for col, (_, row) in zip(cols, report_rows[i : i + 2]):
            with col, st.container(border=True):
                st.markdown(f"**[{row.get('뉴스 제목', '(제목 없음)')}]({row.get('원문링크', '')})**")
                st.caption(f"{row.get('기업명', '')} · {row.get('카테고리', '')} · 중요도 {row.get('중요도 점수', '')}")
                st.write(row.get("요약", ""))

                render_review_actions(row, key_prefix="report", show_approve=False)


def render_quality_tab(df: pd.DataFrame):
    if READ_ONLY_MODE:
        st.info(READ_ONLY_BANNER)

    st.subheader("검토 현황")

    status_counts = (
        df["review_status"]
        .value_counts()
        .reindex(STATUS_ORDER)
        .fillna(0)
        .reset_index()
    )
    status_counts.columns = ["review_status", "기사 수"]
    status_counts["상태"] = status_counts["review_status"].map(STATUS_LABELS)

    if status_counts["기사 수"].sum() == 0:
        st.info("데이터가 없습니다.")
    else:
        fig = px.pie(
            status_counts,
            names="상태",
            values="기사 수",
            color="상태",
            color_discrete_map={STATUS_LABELS[s]: STATUS_COLORS[s] for s in STATUS_ORDER},
            category_orders={"상태": [STATUS_LABELS[s] for s in STATUS_ORDER]},
            hole=0.45,
        )
        fig.update_traces(textinfo="label+percent")
        fig.update_layout(margin=dict(t=10, b=10, l=10, r=10))
        st.plotly_chart(fig, width="stretch")

    st.divider()
    st.subheader("검토 필요도 분포")
    priority_df = df.dropna(subset=["검토 필요도"]).copy()

    if priority_df.empty:
        st.info("검토 필요도 데이터가 없습니다.")
    else:
        priority_df["상태"] = priority_df["review_status"].map(STATUS_LABELS)
        fig = px.histogram(
            priority_df,
            x="검토 필요도",
            color="상태",
            color_discrete_map={STATUS_LABELS[s]: STATUS_COLORS[s] for s in STATUS_ORDER},
            category_orders={"상태": [STATUS_LABELS[s] for s in STATUS_ORDER]},
            nbins=20,
        )
        fig.update_layout(margin=dict(t=10, b=10, l=10, r=10), bargap=0.05)
        st.plotly_chart(fig, width="stretch")

        st.subheader("검토 필요도 구간별 반려율")
        bin_edges = [i / 10 for i in range(11)]
        bin_labels = [f"{bin_edges[i]:.1f}-{bin_edges[i + 1]:.1f}" for i in range(len(bin_edges) - 1)]
        priority_df["검토 필요도 구간"] = pd.cut(
            priority_df["검토 필요도"], bins=bin_edges, labels=bin_labels, include_lowest=True
        )

        bin_rate = compute_rejection_rate(priority_df, "검토 필요도 구간").dropna(subset=["반려율(%)"])
        if bin_rate.empty:
            st.info("아직 승인/수정/반려 처리된 기사가 없어 이 차트는 표시할 수 없습니다.")
        else:
            fig = px.bar(
                bin_rate,
                x="검토 필요도 구간",
                y="반려율(%)",
                hover_data=["검토건수"],
                category_orders={"검토 필요도 구간": bin_labels},
            )
            fig.update_traces(marker_color=STATUS_COLORS["rejected"])
            fig.update_layout(margin=dict(t=10, b=10, l=10, r=10))
            st.plotly_chart(fig, width="stretch")

    decided = df[df["review_status"].isin(DECIDED_STATUSES)].copy()

    if decided.empty:
        st.info("아직 승인/수정/반려 처리된 기사가 없어 반려율 관련 차트는 표시할 수 없습니다.")
        return

    st.divider()
    st.subheader("중요도별 반려율")
    imp_rate = compute_rejection_rate(decided, "중요도 점수").sort_values("중요도 점수")
    if imp_rate.empty:
        st.info("데이터가 없습니다.")
    else:
        fig = px.bar(imp_rate, x="중요도 점수", y="반려율(%)", hover_data=["검토건수"])
        fig.update_traces(marker_color=STATUS_COLORS["rejected"])
        fig.update_layout(margin=dict(t=10, b=10, l=10, r=10))
        st.plotly_chart(fig, width="stretch")

    st.subheader("검색 키워드별 반려율")
    kw_rate = compute_rejection_rate(decided, "검색 키워드").sort_values("반려율(%)")
    if kw_rate.empty:
        st.info("데이터가 없습니다.")
    else:
        fig = px.bar(kw_rate, x="반려율(%)", y="검색 키워드", orientation="h", hover_data=["검토건수"])
        fig.update_traces(marker_color=STATUS_COLORS["rejected"])
        fig.update_yaxes(autorange="reversed")
        fig.update_layout(margin=dict(t=10, b=10, l=10, r=10))
        st.plotly_chart(fig, width="stretch")

    st.subheader("수집일별 검토 필요도 평균 추이")
    collected_priority_df = df.dropna(subset=["검토 필요도"])
    if collected_priority_df.empty:
        st.info("검토 필요도 데이터가 없습니다.")
    else:
        # 수집일은 문자열(YYYY-MM-DD) 그대로 묶어서, 실제 수집이 있었던 날짜만 표시한다.
        daily_priority = (
            collected_priority_df.groupby("수집일")["검토 필요도"]
            .mean()
            .reset_index(name="평균 검토 필요도")
        )
        fig = px.line(daily_priority, x="수집일", y="평균 검토 필요도", markers=True)
        fig.update_traces(line_color=BAR_COLOR)
        fig.update_layout(margin=dict(t=10, b=10, l=10, r=10))
        st.plotly_chart(fig, width="stretch")

    st.subheader("수집일별 반려율 추이")
    st.caption("그날 수집된 기사 전체(대기 포함) 중 현재 반려 상태인 기사의 비율입니다.")
    if df.empty:
        st.info("데이터가 없습니다.")
    else:
        daily_collected_reject = (
            df.groupby("수집일")["review_status"]
            .apply(lambda s: (s == "rejected").mean() * 100)
            .reset_index(name="반려율(%)")
        )
        fig = px.line(daily_collected_reject, x="수집일", y="반려율(%)", markers=True)
        fig.update_traces(line_color=STATUS_COLORS["rejected"])
        fig.update_layout(margin=dict(t=10, b=10, l=10, r=10))
        st.plotly_chart(fig, width="stretch")

    st.subheader("검토 필요도와 반려 여부")
    decided_priority = decided.dropna(subset=["검토 필요도"]).copy()
    if decided_priority.empty:
        st.info("검토 필요도 데이터가 없습니다.")
    else:
        decided_priority["반려 여부"] = decided_priority["review_status"].map(
            lambda s: "반려" if s == "rejected" else "반려 아님"
        )
        fig = px.box(
            decided_priority,
            x="반려 여부",
            y="검토 필요도",
            color="반려 여부",
            color_discrete_map={"반려 아님": STATUS_COLORS["approved"], "반려": STATUS_COLORS["rejected"]},
            category_orders={"반려 여부": ["반려 아님", "반려"]},
            points="all",
        )
        fig.update_layout(margin=dict(t=10, b=10, l=10, r=10), showlegend=False)
        st.plotly_chart(fig, width="stretch")

    st.divider()
    st.subheader("반려된 기사 목록")
    rejected = df[df["review_status"] == "rejected"].copy()

    if rejected.empty:
        st.info("반려된 기사가 없습니다.")
    else:
        reasons = sorted(r for r in rejected["반려 사유"].dropna().unique() if r)
        selected_reasons = st.multiselect("반려 사유 필터", reasons, key="rejected_reason_filter")

        if selected_reasons:
            rejected = rejected[rejected["반려 사유"].isin(selected_reasons)]

        st.caption(f"{len(rejected)}건")

        rejected_rows = list(rejected.iterrows())
        for i in range(0, len(rejected_rows), 2):
            cols = st.columns(2)
            for col, (_, row) in zip(cols, rejected_rows[i : i + 2]):
                with col, st.container(border=True):
                    st.markdown(f"**{row.get('뉴스 제목', '(제목 없음)')}**")
                    st.caption(
                        f"{row.get('카테고리', '')} · 중요도 {row.get('중요도 점수', '')} · "
                        f"반려 사유: {row.get('반려 사유', '')}"
                    )
                    st.write(row.get("요약", ""))

                    render_rejected_actions(row, key_prefix="rejectlist")


def render_rejected_actions(row: pd.Series, key_prefix: str):
    """반려된 기사 전용 컨트롤: 승인으로 변경(그대로/수정 후) 또는 반려 사유만 변경."""
    row_number = int(row["_row"])

    approve_open_key = f"{key_prefix}_approve_open_{row_number}"
    reason_open_key = f"{key_prefix}_reason_open_{row_number}"

    approve_col, reason_col = st.columns(2)

    if approve_col.button("승인으로 변경", key=f"{key_prefix}_approve_btn_{row_number}", width="stretch"):
        st.session_state[approve_open_key] = not st.session_state.get(approve_open_key, False)

    if reason_col.button("반려 사유 변경", key=f"{key_prefix}_reason_btn_{row_number}", width="stretch"):
        st.session_state[reason_open_key] = not st.session_state.get(reason_open_key, False)

    if st.session_state.get(approve_open_key):
        mode = st.radio(
            "승인 방식 선택",
            ["그대로 승인", "수정 후 승인"],
            key=f"{key_prefix}_approve_mode_{row_number}",
            horizontal=True,
        )

        if mode == "그대로 승인":
            if st.button("승인 확정", key=f"{key_prefix}_approve_confirm_{row_number}"):
                if READ_ONLY_MODE:
                    notify_read_only()
                else:
                    update_row(row_number, {"review_status": "approved"})
                    st.session_state[approve_open_key] = False
                    refresh()
                    st.rerun()
        else:
            edit_df = pd.DataFrame(
                [
                    {
                        "기업명": row.get("기업명", ""),
                        "카테고리": row.get("카테고리", ""),
                        "중요도 점수": row.get("중요도 점수", ""),
                        "요약": row.get("요약", ""),
                    }
                ]
            )
            edited = st.data_editor(
                edit_df,
                column_config={
                    "카테고리": st.column_config.SelectboxColumn(options=CATEGORY_ORDER),
                    "중요도 점수": st.column_config.NumberColumn(min_value=1, max_value=5, step=1),
                },
                hide_index=True,
                key=f"{key_prefix}_approve_editor_{row_number}",
            )

            if st.button("저장 후 승인", key=f"{key_prefix}_approve_save_{row_number}"):
                if READ_ONLY_MODE:
                    notify_read_only()
                else:
                    edited_row = edited.iloc[0]
                    update_row(
                        row_number,
                        {
                            "기업명": edited_row["기업명"],
                            "카테고리": edited_row["카테고리"],
                            "중요도 점수": int(edited_row["중요도 점수"]),
                            "요약": edited_row["요약"],
                            "review_status": "approved",
                        },
                    )
                    st.session_state[approve_open_key] = False
                    refresh()
                    st.rerun()

    if st.session_state.get(reason_open_key):
        current_reason = row.get("반려 사유", "")
        default_index = REJECT_REASONS.index(current_reason) if current_reason in REJECT_REASONS else 0
        new_reason = st.selectbox(
            "새 반려 사유",
            REJECT_REASONS,
            index=default_index,
            key=f"{key_prefix}_new_reason_{row_number}",
        )

        if st.button("반려 사유 저장", key=f"{key_prefix}_reason_confirm_{row_number}"):
            if READ_ONLY_MODE:
                notify_read_only()
            else:
                update_row(row_number, {"반려 사유": new_reason})
                st.session_state[reason_open_key] = False
                refresh()
                st.rerun()


def summarize_industry_issues(summaries: list[str]) -> str:
    joined = "\n\n".join(f"- {s}" for s in summaries)
    prompt = (
        "다음은 같은 산업에 속한 여러 뉴스 기사의 요약입니다.\n\n"
        f"{joined}\n\n"
        "이 요약들에서 공통적으로 나타나는 핵심 이슈나 트렌드를 한국어로 3~5개로 정리해주세요.\n"
        "마크다운 헤더(#, ##) 없이, 강조할 부분만 굵게 표시하고 나머지는 일반 텍스트로 작성해주세요."
    )

    response = claude_client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return next(b.text for b in response.content if b.type == "text")


def render_industry_summary_section(df: pd.DataFrame):
    st.header("산업별 핵심 이슈 요약")

    industries = sorted(i for i in df["산업"].dropna().unique() if i and i != "기타")
    if not industries:
        st.info("데이터가 없습니다.")
        return

    selected_industry = st.selectbox("산업 선택", industries, key="industry_summary_select")

    industry_df = df[(df["산업"] == selected_industry) & (df["review_status"].isin(REPORT_STATUSES))]
    count = len(industry_df)

    if count < INDUSTRY_SUMMARY_MIN_ARTICLES:
        st.info(
            f"검토 완료된 기사가 부족해 요약을 생성할 수 없습니다 "
            f"(현재 {count}건 / 최소 {INDUSTRY_SUMMARY_MIN_ARTICLES}건 필요)"
        )
        return

    if st.button("요약 생성", key="industry_summary_generate"):
        summaries = industry_df["요약"].dropna().tolist()
        links = [link for link in industry_df["원문링크"].dropna().tolist() if link]

        with st.spinner("요약 생성 중..."):
            try:
                result_text = summarize_industry_issues(summaries)
            except anthropic.APIError as e:
                st.error(f"요약 생성 중 오류가 발생했습니다: {e}")
            else:
                st.session_state["industry_summary_result"] = {
                    "industry": selected_industry,
                    "text": result_text,
                    "links": links,
                }

    result = st.session_state.get("industry_summary_result")
    if result and result["industry"] == selected_industry:
        with st.container(border=True):
            st.markdown('<div style="font-size:1.5rem; line-height:1.6;">', unsafe_allow_html=True)
            st.markdown(result["text"])
            st.markdown("</div>", unsafe_allow_html=True)

        st.caption("참고한 기사 원문 링크")
        for link in result["links"]:
            st.markdown(f"- {link}")


def render_insights_tab(df: pd.DataFrame):
    st.caption("※ 기타로 분류된 기사는 이 탭의 차트에서 제외됩니다.")

    st.subheader("기업별 언급 빈도 Top 10")
    top_companies = df["기업명"].dropna()
    top_companies = top_companies[~top_companies.isin(["", "기타"])].value_counts().head(10).reset_index()
    top_companies.columns = ["기업명", "기사 수"]

    if top_companies.empty:
        st.info("데이터가 없습니다.")
    else:
        fig = px.bar(top_companies.sort_values("기사 수"), x="기사 수", y="기업명", orientation="h")
        fig.update_traces(marker_color=BAR_COLOR)
        fig.update_yaxes(autorange="reversed")
        fig.update_layout(margin=dict(t=10, b=10, l=10, r=10))
        st.plotly_chart(fig, width="stretch")

    st.subheader("산업별 기사 수")
    industry_counts = df["산업"].dropna()
    industry_counts = industry_counts[~industry_counts.isin(["", "기타"])].value_counts().reset_index()
    industry_counts.columns = ["산업", "기사 수"]

    if industry_counts.empty:
        st.info("데이터가 없습니다.")
    else:
        fig = px.bar(industry_counts.sort_values("기사 수"), x="기사 수", y="산업", orientation="h")
        fig.update_traces(marker_color=BAR_COLOR)
        fig.update_yaxes(autorange="reversed")
        fig.update_layout(margin=dict(t=10, b=10, l=10, r=10))
        st.plotly_chart(fig, width="stretch")

    st.subheader("산업 × 카테고리 히트맵")
    heat_source = df[
        (df["산업"].notna())
        & (~df["산업"].isin(["", "기타"]))
        & (df["카테고리"].notna())
        & (df["카테고리"] != "기타")
    ]
    if heat_source.empty:
        st.info("데이터가 없습니다.")
    else:
        pivot = pd.crosstab(heat_source["산업"], heat_source["카테고리"])
        pivot = pivot.reindex(columns=[c for c in CATEGORY_ORDER if c in pivot.columns])
        pivot = pivot.loc[pivot.sum(axis=1).sort_values(ascending=False).index]
        fig = px.imshow(pivot, color_continuous_scale="Blues", aspect="auto", labels=dict(color="기사 수"))
        fig.update_layout(margin=dict(t=10, b=10, l=10, r=10))
        st.plotly_chart(fig, width="stretch")

    st.divider()
    render_industry_summary_section(df)


def main():
    st.title("📰 취업 뉴스 자동 리포트")
    st.caption("Google Sheets에 수집된 뉴스를 검토하고 리포트로 정리합니다.")

    if st.button("새로고침"):
        refresh()

    df = load_data()

    if df.empty:
        st.warning("시트에 데이터가 없습니다. `collect.py`를 먼저 실행해주세요.")
        return

    render_overview(df)
    st.divider()

    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        ["검토 대기함", "전체 보기(미검수 포함)", "최종 리포트", "AI 성능/검토 현황", "뉴스 인사이트"]
    )
    with tab1:
        render_pending_tab(df)
    with tab2:
        render_all_tab(df)
    with tab3:
        render_report_tab(df)
    with tab4:
        render_quality_tab(df)
    with tab5:
        render_insights_tab(df)


if __name__ == "__main__":
    main()
