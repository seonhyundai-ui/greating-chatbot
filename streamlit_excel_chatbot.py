import io
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

st.set_page_config(page_title="맞춤 식단 챗봇", page_icon="💬", layout="centered")

CSS = """
<style>
.block-container {
    max-width: 860px;
    padding-top: 1.2rem;
    padding-bottom: 3rem;
}

html, body, [class*="css"] {
    font-family: -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo",
                 "Pretendard", "Segoe UI", sans-serif;
}

h1 {
    font-size: 30px !important;
    font-weight: 800 !important;
    margin-bottom: 0.2rem !important;
    color: #111827;
}

.chat-wrap {
    display: flex;
    width: 100%;
    margin: 0.45rem 0;
}

.chat-wrap.bot {
    justify-content: flex-start;
}

.chat-wrap.user {
    justify-content: flex-end;
}

.chat-bubble {
    max-width: 78%;
    padding: 14px 16px;
    border-radius: 20px;
    line-height: 1.6;
    font-size: 17px;
    word-break: keep-all;
    box-shadow: 0 6px 18px rgba(17, 24, 39, 0.06);
    border: 1px solid rgba(0,0,0,0.04);
}

.chat-bubble.bot {
    background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
    color: #111827;
    border-bottom-left-radius: 8px;
}

.chat-bubble.user {
    background: linear-gradient(180deg, #dbeafe 0%, #bfdbfe 100%);
    color: #0f172a;
    border-bottom-right-radius: 8px;
}

.result-card {
    border: 1px solid #d1fae5;
    background: linear-gradient(180deg, #f0fdf4 0%, #ecfdf5 100%);
    border-radius: 22px;
    padding: 18px;
    margin-top: 12px;
    box-shadow: 0 10px 24px rgba(16, 185, 129, 0.08);
}

.result-title {
    font-size: 24px;
    font-weight: 800;
    margin-bottom: 8px;
    color: #065f46;
}

.path-card {
    border: 1px solid #e5e7eb;
    background: #ffffff;
    border-radius: 20px;
    padding: 16px 18px;
    margin-top: 12px;
    box-shadow: 0 6px 18px rgba(17, 24, 39, 0.05);
}

.small-note {
    font-size: 13px;
    color: #6b7280;
}

.option-row {
    width: 100%;
    display: flex;
    justify-content: flex-end;
    margin-top: 10px;
}

.option-row > div {
    width: 78%;
    margin-left: auto;
}

.option-row .stButton {
    width: 100%;
}

.option-row .stButton > button {
    width: 100%;
    min-height: 54px;
    border-radius: 16px;
    font-size: 16px;
    font-weight: 700;
    border: none;
    box-shadow: 0 6px 16px rgba(59, 130, 246, 0.18);
    background: linear-gradient(180deg, #3b82f6 0%, #2563eb 100%);
    color: white;
}

.back-btn .stButton > button {
    width: 100%;
    min-height: 48px;
    border-radius: 14px;
    font-size: 15px;
    font-weight: 700;
    border: none;
    background: linear-gradient(180deg, #f59e0b 0%, #d97706 100%);
    color: #ffffff;
    box-shadow: 0 6px 14px rgba(245, 158, 11, 0.22);
}

.restart-btn .stButton > button {
    width: 100%;
    min-height: 48px;
    border-radius: 14px;
    font-size: 15px;
    font-weight: 700;
    border: none;
    background: linear-gradient(180deg, #10b981 0%, #059669 100%);
    color: #ffffff;
    box-shadow: 0 6px 14px rgba(16, 185, 129, 0.22);
}

.data-badge {
    display: inline-block;
    padding: 6px 10px;
    border-radius: 999px;
    background: #eef2ff;
    color: #4338ca;
    font-size: 13px;
    font-weight: 700;
    margin-top: 6px;
    margin-bottom: 8px;
}

.section-gap {
    height: 8px;
}
</style>
"""

REQUIRED_COLUMNS = [
    "현재 노드 ID",
    "리액션 (이전 선택 반영)",
    "질문 내용",
    "선택 옵션",
    "이동할 노드 ID",
    "최종 추천 식단 (결과)",
]

# GitHub 저장소에 함께 올려둘 기본 엑셀 파일명
DEFAULT_EXCEL_FILE = "맞춤 식단 큐레이션 마스터 완성.xlsx"


@dataclass
class OptionRow:
    node_id: str
    reaction: str
    question: str
    option_text: str
    next_node: str
    result: str


@dataclass
class StepRecord:
    node_id: str
    question: str
    selected_option: str
    next_node: str
    result: Optional[str] = None


def init_state() -> None:
    defaults = {
        "workbook_bytes": None,
        "file_name": None,
        "sheet_name": None,
        "tree": None,
        "current_node": None,
        "history": [],
        "steps": [],
        "result_name": None,
        "data_source": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


init_state()
st.markdown(CSS, unsafe_allow_html=True)


def clean_text(value) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


@st.cache_data(show_spinner=False)
def load_workbook(file_bytes: bytes) -> Dict[str, pd.DataFrame]:
    xls = pd.ExcelFile(io.BytesIO(file_bytes))
    return {sheet: pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet) for sheet in xls.sheet_names}


@st.cache_data(show_spinner=False)
def parse_tree(file_bytes: bytes, sheet_name: str) -> Dict[str, List[OptionRow]]:
    df = pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet_name)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"필수 컬럼이 없습니다: {', '.join(missing)}")

    df = df[REQUIRED_COLUMNS].copy()
    for col in REQUIRED_COLUMNS:
        df[col] = df[col].map(clean_text)

    df = df[df["현재 노드 ID"] != ""].copy()

    tree: Dict[str, List[OptionRow]] = {}
    for _, row in df.iterrows():
        item = OptionRow(
            node_id=row["현재 노드 ID"],
            reaction=row["리액션 (이전 선택 반영)"],
            question=row["질문 내용"],
            option_text=row["선택 옵션"],
            next_node=row["이동할 노드 ID"],
            result=row["최종 추천 식단 (결과)"],
        )
        tree.setdefault(item.node_id, []).append(item)
    return tree


def get_start_node(tree: Dict[str, List[OptionRow]]) -> str:
    for candidate in ["Q1(시작)", "Q1", "START", "start"]:
        if candidate in tree:
            return candidate
    return next(iter(tree.keys()))


ROUTER_RULES = {
    ("Result-MedRoute", "고혈압"): "Result-02",
    ("Result-MedRoute", "암"): "Result-03",
}


def resolve_route(next_node: str, selected_option: str) -> Tuple[str, Optional[str]]:
    if next_node != "Result-MedRoute":
        return next_node, None
    text = selected_option
    for (router, keyword), result_node in ROUTER_RULES.items():
        if router == next_node and keyword in text:
            return result_node, None
    if "고혈압" in text:
        return "Result-02", None
    if "암" in text:
        return "Result-03", None
    return next_node, "조건부 결과 연결을 찾지 못했습니다. 라우터 규칙을 확인해주세요."


RESULT_NAME_BY_NODE = {
    "Result-01": "당뇨식단(냉장)",
    "Result-02": "고혈압식단",
    "Result-03": "암환자식단",
    "Result-04": "신장질환식단(투석)",
    "Result-05": "신장질환식단(비투석)",
    "Result-06": "당뇨식단(냉동)",
    "Result-07": "저당식단",
    "Result-08": "칼로리식단",
    "Result-09": "단백질식단",
    "Result-10": "저속식단",
    "Result-11": "마이그리팅",
    "Result-12": "350뷰티핏",
    "Result-13": "프로틴Up",
    "Result-14": "저당플랜",
    "Result-15": "저속도시락",
}


def node_result_name(tree: Dict[str, List[OptionRow]], node_id: str) -> str:
    if node_id in RESULT_NAME_BY_NODE:
        return RESULT_NAME_BY_NODE[node_id]
    rows = tree.get(node_id, [])
    for row in rows:
        if row.result and row.result not in {"-", "(조건부 연결)"}:
            return row.result
    return node_id


def reset_chat(tree: Dict[str, List[OptionRow]]) -> None:
    start_node = get_start_node(tree)
    first_row = tree[start_node][0]
    st.session_state.current_node = start_node
    st.session_state.history = []
    st.session_state.steps = []
    st.session_state.result_name = None
    if first_row.reaction:
        st.session_state.history.append({"role": "bot", "text": first_row.reaction})
    if first_row.question:
        st.session_state.history.append({"role": "bot", "text": first_row.question})


def apply_workbook(file_bytes: bytes, file_name: str, selected_sheet: str) -> None:
    tree = parse_tree(file_bytes, selected_sheet)
    st.session_state.workbook_bytes = file_bytes
    st.session_state.file_name = file_name
    st.session_state.sheet_name = selected_sheet
    st.session_state.tree = tree
    reset_chat(tree)


@st.cache_data(show_spinner=False)
def read_repo_excel(path_str: str) -> bytes:
    return Path(path_str).read_bytes()


def get_default_excel_path() -> Optional[Path]:
    base_dir = Path(__file__).resolve().parent
    candidate = base_dir / DEFAULT_EXCEL_FILE
    return candidate if candidate.exists() else None


def render_bubble(role: str, text: str) -> None:
    safe_text = text.replace("\n", "<br>")
    st.markdown(
        f"""
        <div class="chat-wrap {role}">
            <div class="chat-bubble {role}">{safe_text}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def replay_until(step_count: int) -> None:
    tree = st.session_state.tree
    all_steps = st.session_state.steps[:step_count]
    reset_chat(tree)
    st.session_state.steps = []
    st.session_state.result_name = None

    for step in all_steps:
        current = st.session_state.current_node
        options_here = tree.get(current, [])
        selected_row = next((r for r in options_here if r.option_text == step.selected_option), None)
        if not selected_row:
            break
        st.session_state.history.append({"role": "user", "text": selected_row.option_text})
        resolved_next, _ = resolve_route(selected_row.next_node, selected_row.option_text)
        is_result = resolved_next.startswith("Result-") and resolved_next != "Result-MedRoute"
        if is_result:
            result_name = node_result_name(tree, resolved_next)
            st.session_state.steps.append(StepRecord(current, selected_row.question, selected_row.option_text, resolved_next, result_name))
            st.session_state.current_node = resolved_next
            st.session_state.result_name = result_name
        else:
            next_rows = tree.get(resolved_next, [])
            st.session_state.steps.append(StepRecord(current, selected_row.question, selected_row.option_text, resolved_next, None))
            if next_rows:
                if next_rows[0].reaction:
                    st.session_state.history.append({"role": "bot", "text": next_rows[0].reaction})
                if next_rows[0].question:
                    st.session_state.history.append({"role": "bot", "text": next_rows[0].question})
            st.session_state.current_node = resolved_next


# Header
st.title("💬 맞춤 식단 추천 챗봇")
st.caption("질문에 답하면, 나에게 맞는 식단을 추천해드려요.")

# 기본 엑셀 자동 로드
repo_excel_path = get_default_excel_path()
default_bytes = None
if repo_excel_path:
    default_bytes = read_repo_excel(str(repo_excel_path))

source_options = []
if default_bytes is not None:
    source_options.append("기본 데모 파일 사용")
source_options.append("직접 업로드")

selected_source = st.radio(
    "데이터 소스",
    source_options,
    horizontal=True,
    index=0,
    label_visibility="collapsed",
)

if selected_source == "기본 데모 파일 사용" and default_bytes is not None:
    workbook = load_workbook(default_bytes)
    sheet_names = list(workbook.keys())

    default_sheet_index = 0
    if st.session_state.file_name == DEFAULT_EXCEL_FILE and st.session_state.sheet_name in sheet_names:
        default_sheet_index = sheet_names.index(st.session_state.sheet_name)

    selected_sheet = st.selectbox("시트 선택", sheet_names, index=default_sheet_index)
    st.markdown(f"<div class='data-badge'>기본 파일 연결됨 · {DEFAULT_EXCEL_FILE}</div>", unsafe_allow_html=True)

    needs_reload = (
        st.session_state.workbook_bytes != default_bytes
        or st.session_state.sheet_name != selected_sheet
        or st.session_state.file_name != DEFAULT_EXCEL_FILE
    )

    if needs_reload:
        try:
            apply_workbook(default_bytes, DEFAULT_EXCEL_FILE, selected_sheet)
            st.session_state.data_source = "repo_default"
        except Exception as e:
            st.error(f"기본 엑셀 파일을 읽는 중 오류가 발생했습니다: {e}")
            st.stop()

else:
    uploaded_file = st.file_uploader("엑셀 파일 업로드", type=["xlsx", "xls"])
    if uploaded_file is not None:
        file_bytes = uploaded_file.getvalue()
        workbook = load_workbook(file_bytes)
        sheet_names = list(workbook.keys())
        selected_sheet = st.selectbox("시트 선택", sheet_names, index=0)

        file_changed = (
            st.session_state.workbook_bytes != file_bytes
            or st.session_state.sheet_name != selected_sheet
            or st.session_state.file_name != uploaded_file.name
        )

        if file_changed:
            try:
                apply_workbook(file_bytes, uploaded_file.name, selected_sheet)
                st.session_state.data_source = "uploaded"
            except Exception as e:
                st.error(f"파일을 읽는 중 오류가 발생했습니다: {e}")
                st.stop()

if not st.session_state.tree:
    if default_bytes is None:
        st.info("기본 엑셀 파일이 없어요. GitHub 저장소에 엑셀을 올리거나 직접 업로드해 주세요.")
    else:
        st.info("챗봇 데이터를 불러오는 중입니다.")
    st.stop()

for msg in st.session_state.history:
    render_bubble(msg["role"], msg["text"])

if st.session_state.result_name:
    st.markdown(
        f"""
        <div class="chat-wrap bot">
            <div class="result-card">
                <div class="small-note">최종 추천 결과</div>
                <div class="result-title">{st.session_state.result_name}</div>
                <div>답변 내용을 바탕으로 가장 잘 맞는 식단을 추천했어요.</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    path_lines = []
    for idx, step in enumerate(st.session_state.steps, start=1):
        path_lines.append(
            f"<div style='margin-bottom:10px; font-size:16px; line-height:1.55;'><b>{idx}. {step.question}</b><br>→ 선택: {step.selected_option}</div>"
        )
    st.markdown(
        f"""
        <div class="chat-wrap bot">
            <div class="path-card">
                <div style="font-size:18px; font-weight:700; margin-bottom:10px;">내 답변 요약</div>
                {''.join(path_lines) if path_lines else '<div class="small-note">선택 이력이 없습니다.</div>'}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns([1.2, 1.2, 2.6])
    with col1:
        st.markdown("<div class='back-btn'>", unsafe_allow_html=True)
        if st.button("이전 질문", key="back_from_result"):
            replay_until(len(st.session_state.steps) - 1)
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    with col2:
        st.markdown("<div class='restart-btn'>", unsafe_allow_html=True)
        if st.button("처음으로", key="restart_result"):
            reset_chat(st.session_state.tree)
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)
    st.stop()

current_node = st.session_state.current_node
options = st.session_state.tree.get(current_node, [])
if not options:
    st.warning("현재 노드에 연결된 선택지가 없습니다. 엑셀 구조를 확인해 주세요.")
    st.stop()

for idx, option in enumerate(options):
    st.markdown("<div class='option-row'>", unsafe_allow_html=True)
    if st.button(option.option_text, key=f"option_{current_node}_{idx}"):
        st.session_state.history.append({"role": "user", "text": option.option_text})
        resolved_next, warning_msg = resolve_route(option.next_node, option.option_text)
        if warning_msg:
            st.warning(warning_msg)

        is_result = resolved_next.startswith("Result-") and resolved_next != "Result-MedRoute"
        if is_result:
            result_name = node_result_name(st.session_state.tree, resolved_next)
            st.session_state.steps.append(
                StepRecord(current_node, option.question, option.option_text, resolved_next, result_name)
            )
            st.session_state.current_node = resolved_next
            st.session_state.result_name = result_name
        else:
            next_rows = st.session_state.tree.get(resolved_next, [])
            st.session_state.steps.append(
                StepRecord(current_node, option.question, option.option_text, resolved_next, None)
            )
            if next_rows:
                if next_rows[0].reaction:
                    st.session_state.history.append({"role": "bot", "text": next_rows[0].reaction})
                if next_rows[0].question:
                    st.session_state.history.append({"role": "bot", "text": next_rows[0].question})
            st.session_state.current_node = resolved_next
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<div class='section-gap'></div>", unsafe_allow_html=True)
col1, col2, col3 = st.columns([1.2, 1.2, 2.6])

with col1:
    st.markdown("<div class='back-btn'>", unsafe_allow_html=True)
    if st.button("이전 질문", disabled=len(st.session_state.steps) == 0):
        replay_until(len(st.session_state.steps) - 1)
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

with col2:
    st.markdown("<div class='restart-btn'>", unsafe_allow_html=True)
    if st.button("처음으로"):
        reset_chat(st.session_state.tree)
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)
