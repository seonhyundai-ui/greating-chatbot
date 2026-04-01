import io
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="엑셀 기반 챗봇 데모", page_icon="💬", layout="centered")

REQUIRED_COLUMNS = [
    "현재 노드 ID",
    "리액션 (이전 선택 반영)",
    "질문 내용",
    "선택 옵션",
    "이동할 노드 ID",
    "최종 추천 식단 (결과)",
]


# 현재 업로드된 식단 엑셀 기준 조건부 라우팅
ROUTER_RULES = {
    "Result-MedRoute": {
        "contains": {
            "고혈압": "고혈압식단",
            "암환자": "암환자식단",
        },
        "default": "전문관리식단",
    }
}


@st.cache_data(show_spinner=False)
def load_workbook(file_bytes: bytes):
    xls = pd.ExcelFile(io.BytesIO(file_bytes))
    return xls.sheet_names


@st.cache_data(show_spinner=False)
def load_sheet(file_bytes: bytes, sheet_name: str) -> pd.DataFrame:
    df = pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet_name)
    df = df.fillna("")
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"필수 컬럼이 없습니다: {', '.join(missing)}")
    return df[REQUIRED_COLUMNS].copy()


def init_state():
    defaults = {
        "chat_started": False,
        "history": [],  # [{node_id, reaction, question, selected_option, next_node, result}]
        "current_node": None,
        "final_result": None,
        "selected_sheet": None,
        "last_file_name": None,
        "file_bytes": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def reset_chat(node_id=None):
    st.session_state.chat_started = node_id is not None
    st.session_state.history = []
    st.session_state.current_node = node_id
    st.session_state.final_result = None


def get_start_node(df: pd.DataFrame):
    nodes = df["현재 노드 ID"].astype(str).str.strip()
    start_candidates = nodes[nodes.str.contains("시작", na=False)].unique().tolist()
    if start_candidates:
        return start_candidates[0]
    return nodes.iloc[0]


def get_node_rows(df: pd.DataFrame, node_id: str) -> pd.DataFrame:
    node_id = str(node_id).strip()
    return df[df["현재 노드 ID"].astype(str).str.strip() == node_id].copy()


def resolve_conditional_result(router_node: str, history: list[str]) -> str:
    rule = ROUTER_RULES.get(router_node)
    if not rule:
        return "결과 미정"
    joined = " | ".join(history)
    for keyword, result_name in rule.get("contains", {}).items():
        if keyword in joined:
            return result_name
    return rule.get("default", "결과 미정")


def select_option(df: pd.DataFrame, row: pd.Series):
    current_node = str(row["현재 노드 ID"]).strip()
    next_node = str(row["이동할 노드 ID"]).strip()
    result_name = str(row["최종 추천 식단 (결과)"]).strip()
    reaction = str(row["리액션 (이전 선택 반영)"]).strip()
    question = str(row["질문 내용"]).strip()
    option = str(row["선택 옵션"]).strip()

    history_item = {
        "node_id": current_node,
        "reaction": reaction,
        "question": question,
        "selected_option": option,
        "next_node": next_node,
        "result": None,
    }

    # 일반 결과 노드
    if result_name and result_name != "-":
        history_item["result"] = result_name
        st.session_state.history.append(history_item)
        st.session_state.final_result = result_name
        st.session_state.current_node = None
        return

    # 조건부 라우팅 결과 노드
    if next_node in ROUTER_RULES:
        temp_history = st.session_state.history + [history_item]
        route_texts = [
            f"{h['question']} -> {h['selected_option']}" for h in temp_history if h.get("selected_option")
        ]
        resolved = resolve_conditional_result(next_node, route_texts)
        history_item["result"] = resolved
        st.session_state.history.append(history_item)
        st.session_state.final_result = resolved
        st.session_state.current_node = None
        return

    st.session_state.history.append(history_item)
    st.session_state.current_node = next_node


def go_back(df: pd.DataFrame):
    if not st.session_state.history:
        return
    st.session_state.history.pop()
    st.session_state.final_result = None
    if not st.session_state.history:
        st.session_state.current_node = get_start_node(df)
        return
    st.session_state.current_node = st.session_state.history[-1]["next_node"]


# ---------- UI ----------
init_state()

st.title("💬 엑셀 기반 결정트리 챗봇")
st.caption("엑셀 파일을 업로드하면 질문 → 선택 → 결과 추천 흐름으로 시연할 수 있습니다.")

uploaded_file = st.file_uploader(
    "엑셀 파일 업로드",
    type=["xlsx", "xlsm", "xls"],
    help="질문/선택지/다음 노드가 정리된 엑셀 파일을 올려주세요.",
)

if uploaded_file is not None:
    file_bytes = uploaded_file.getvalue()
    file_name = uploaded_file.name

    if st.session_state.last_file_name != file_name or st.session_state.file_bytes != file_bytes:
        st.session_state.last_file_name = file_name
        st.session_state.file_bytes = file_bytes
        st.session_state.selected_sheet = None
        reset_chat(None)

    try:
        sheets = load_workbook(file_bytes)
    except Exception as e:
        st.error(f"엑셀 파일을 읽는 중 오류가 발생했습니다: {e}")
        st.stop()

    if not sheets:
        st.error("시트가 없는 엑셀 파일입니다.")
        st.stop()

    default_sheet = st.session_state.selected_sheet or sheets[0]
    selected_sheet = st.selectbox("시트 선택", sheets, index=sheets.index(default_sheet) if default_sheet in sheets else 0)
    st.session_state.selected_sheet = selected_sheet

    try:
        df = load_sheet(file_bytes, selected_sheet)
    except Exception as e:
        st.error(str(e))
        with st.expander("필수 컬럼 형식 보기"):
            st.write(REQUIRED_COLUMNS)
        st.stop()

    start_node = get_start_node(df)

    top1, top2 = st.columns([1, 1])
    with top1:
        if st.button("🚀 챗봇 시작", use_container_width=True):
            reset_chat(start_node)
    with top2:
        if st.button("🔄 처음부터 다시", use_container_width=True):
            reset_chat(start_node if st.session_state.chat_started else None)

    st.divider()

    # 대화 히스토리 표시
    for idx, item in enumerate(st.session_state.history, start=1):
        if item["reaction"]:
            with st.chat_message("assistant"):
                st.markdown(item["reaction"])
        with st.chat_message("assistant"):
            st.markdown(item["question"])
        with st.chat_message("user"):
            st.markdown(item["selected_option"])

    # 현재 질문 표시
    if st.session_state.chat_started and st.session_state.final_result is None and st.session_state.current_node:
        node_rows = get_node_rows(df, st.session_state.current_node)

        if node_rows.empty:
            st.error(f"현재 노드 '{st.session_state.current_node}' 를 찾을 수 없습니다.")
        else:
            first = node_rows.iloc[0]
            reaction = str(first["리액션 (이전 선택 반영)"]).strip()
            question = str(first["질문 내용"]).strip()

            if reaction:
                with st.chat_message("assistant"):
                    st.markdown(reaction)
            with st.chat_message("assistant"):
                st.markdown(f"### {question}")

            st.write("선택지를 눌러 진행하세요.")
            for i, (_, row) in enumerate(node_rows.iterrows()):
                label = str(row["선택 옵션"]).strip() or f"선택지 {i+1}"
                if st.button(label, key=f"opt_{st.session_state.current_node}_{i}", use_container_width=True):
                    select_option(df, row)
                    st.rerun()

            if st.session_state.history:
                if st.button("⬅️ 이전 질문으로 돌아가기", use_container_width=True):
                    go_back(df)
                    st.rerun()

    # 결과 표시
    if st.session_state.final_result is not None:
        st.success(f"추천 결과: **{st.session_state.final_result}**")

        with st.container(border=True):
            st.markdown("### 선택 경로")
            if not st.session_state.history:
                st.write("기록이 없습니다.")
            else:
                for i, item in enumerate(st.session_state.history, start=1):
                    st.markdown(
                        f"**{i}. {item['question']}**  \n→ 선택: {item['selected_option']}"
                    )

        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("⬅️ 이전 선택으로 돌아가기", use_container_width=True):
                go_back(df)
                st.rerun()
        with col2:
            if st.button("🔄 처음부터 다시 시작", use_container_width=True):
                reset_chat(start_node)
                st.rerun()

else:
    st.info("먼저 챗봇 마스터 엑셀 파일을 업로드해 주세요.")
    with st.expander("필수 컬럼 보기"):
        st.write(REQUIRED_COLUMNS)
