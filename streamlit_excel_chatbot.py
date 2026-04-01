import io
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

st.set_page_config(page_title="맞춤 식단 챗봇 데모", page_icon="💬", layout="centered")

CSS = """
<style>
.block-container {
    max-width: 860px;
    padding-top: 1.5rem;
    padding-bottom: 3rem;
}
.chat-wrap {
    display: flex;
    width: 100%;
    margin: 0.35rem 0;
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
    border-radius: 18px;
    line-height: 1.55;
    font-size: 16px;
    word-break: keep-all;
    box-shadow: 0 1px 2px rgba(0,0,0,0.08);
}
.chat-bubble.bot {
    background: #f3f4f6;
    color: #111827;
    border-bottom-left-radius: 6px;
}
.chat-bubble.user {
    background: #dbeafe;
    color: #111827;
    border-bottom-right-radius: 6px;
}
.chat-bubble.result {
    background: #ecfeff;
    border: 1px solid #a5f3fc;
}
.chat-label {
    font-size: 12px;
    color: #6b7280;
    margin-bottom: 4px;
}
.option-box {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 16px;
    padding: 12px;
    margin-top: 10px;
}
.result-card {
    border: 1px solid #d1fae5;
    background: #f0fdf4;
    border-radius: 18px;
    padding: 16px;
    margin-top: 12px;
}
.result-title {
    font-size: 22px;
    font-weight: 700;
    margin-bottom: 6px;
}
.path-card {
    border: 1px solid #e5e7eb;
    background: #ffffff;
    border-radius: 16px;
    padding: 14px 16px;
    margin-top: 12px;
}
.small-note {
    font-size: 13px;
    color: #6b7280;
}
.stButton > button {
    width: 100%;
    min-height: 52px;
    border-radius: 14px;
    font-size: 16px;
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


# Header
st.title("💬 맞춤 식단 추천 챗봇 데모")
st.caption("업로드한 엑셀의 질문 트리를 기반으로 실제 채팅창처럼 시연할 수 있는 웹앱입니다.")

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
            tree = parse_tree(file_bytes, selected_sheet)
            st.session_state.workbook_bytes = file_bytes
            st.session_state.file_name = uploaded_file.name
            st.session_state.sheet_name = selected_sheet
            st.session_state.tree = tree
            reset_chat(tree)
        except Exception as e:
            st.error(f"파일을 읽는 중 오류가 발생했습니다: {e}")
            st.stop()

if not st.session_state.tree:
    st.info("먼저 챗봇용 엑셀 파일을 업로드해 주세요.")
    st.stop()


def render_bubble(role: str, text: str) -> None:
    safe_text = text.replace("\n", "<br>")
    st.markdown(
        f"""
        <div class="chat-wrap {role}">
            <div>
                <div class="chat-bubble {role}">{safe_text}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


for msg in st.session_state.history:
    render_bubble(msg["role"], msg["text"])

if st.session_state.result_name:
    st.markdown(
        f"""
        <div class="chat-wrap bot">
            <div class="result-card">
                <div class="small-note">최종 추천 결과</div>
                <div class="result-title">{st.session_state.result_name}</div>
                <div>선택하신 흐름을 바탕으로 가장 잘 맞는 식단을 추천했어요.</div>
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
                <div style="font-size:18px; font-weight:700; margin-bottom:10px;">선택 경로</div>
                {''.join(path_lines) if path_lines else '<div class="small-note">선택 이력이 없습니다.</div>'}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns([1, 1, 1])
    with col3:
        if st.button("이전 선택으로 돌아가기", key="back_from_result"):
            if st.session_state.steps:
                st.session_state.steps.pop()
                st.session_state.result_name = None
                # rebuild history from steps
                tree = st.session_state.tree
                reset_chat(tree)
                previous_steps = st.session_state.steps.copy()
                st.session_state.steps = []
                st.session_state.history = st.session_state.history[:]  # keep intro only
                st.session_state.result_name = None
                current_node = get_start_node(tree)
                if previous_steps:
                    for step in previous_steps:
                        options = tree[current_node]
                        selected_row = next((r for r in options if r.option_text == step.selected_option), None)
                        if not selected_row:
                            break
                        st.session_state.history.append({"role": "user", "text": selected_row.option_text})
                        resolved_next, _ = resolve_route(selected_row.next_node, selected_row.option_text)
                        is_result = resolved_next.startswith("Result-") and resolved_next != "Result-MedRoute"
                        if is_result:
                            st.session_state.steps.append(
                                StepRecord(current_node, selected_row.question, selected_row.option_text, resolved_next, node_result_name(tree, resolved_next))
                            )
                            st.session_state.current_node = resolved_next
                            st.session_state.result_name = node_result_name(tree, resolved_next)
                        else:
                            next_rows = tree.get(resolved_next, [])
                            st.session_state.steps.append(
                                StepRecord(current_node, selected_row.question, selected_row.option_text, resolved_next, None)
                            )
                            if next_rows:
                                if next_rows[0].reaction:
                                    st.session_state.history.append({"role": "bot", "text": next_rows[0].reaction})
                                if next_rows[0].question:
                                    st.session_state.history.append({"role": "bot", "text": next_rows[0].question})
                            st.session_state.current_node = resolved_next
                # and then remove one step again to back from result
                if st.session_state.steps:
                    st.session_state.steps.pop()
                    replay_steps = st.session_state.steps.copy()
                    reset_chat(tree)
                    st.session_state.steps = []
                    for step in replay_steps:
                        options = tree[st.session_state.current_node]
                        selected_row = next((r for r in options if r.option_text == step.selected_option), None)
                        if not selected_row:
                            break
                        st.session_state.history.append({"role": "user", "text": selected_row.option_text})
                        resolved_next, _ = resolve_route(selected_row.next_node, selected_row.option_text)
                        next_rows = tree.get(resolved_next, [])
                        st.session_state.steps.append(StepRecord(st.session_state.current_node, selected_row.question, selected_row.option_text, resolved_next, None))
                        if next_rows:
                            if next_rows[0].reaction:
                                st.session_state.history.append({"role": "bot", "text": next_rows[0].reaction})
                            if next_rows[0].question:
                                st.session_state.history.append({"role": "bot", "text": next_rows[0].question})
                        st.session_state.current_node = resolved_next
            st.rerun()
    with col2:
        if st.button("처음부터 다시 시작", key="restart_result"):
            reset_chat(st.session_state.tree)
            st.rerun()
    st.stop()


current_node = st.session_state.current_node
options = st.session_state.tree.get(current_node, [])
if not options:
    st.warning("현재 노드에 연결된 선택지가 없습니다. 엑셀 구조를 확인해 주세요.")
    st.stop()

st.markdown("<div class='option-box'><div style='font-size:15px; font-weight:600; margin-bottom:8px;'>선택지</div></div>", unsafe_allow_html=True)
for idx, option in enumerate(options):
    left, right = st.columns([1.3, 2.7])
    with right:
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


bottom_left, bottom_mid, bottom_right = st.columns([1, 1, 1])
with bottom_right:
    if st.button("이전 질문으로 돌아가기", disabled=len(st.session_state.steps) == 0):
        replay_until(len(st.session_state.steps) - 1)
        st.rerun()
with bottom_mid:
    if st.button("처음부터 다시 시작"):
        reset_chat(st.session_state.tree)
        st.rerun()
