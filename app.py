import streamlit as st
import json
import time
import streamlit.components.v1 as components
from pypdf import PdfReader
from google import genai
from google.genai import types

st.set_page_config(page_title="Exam Simulator", layout="wide")

# --- Initialize Session State ---
if "quiz_data" not in st.session_state:
    st.session_state.quiz_data = []
if "current_index" not in st.session_state:
    st.session_state.current_index = 0
if "user_answers" not in st.session_state:
    st.session_state.user_answers = {}  # {index: selected_option}
if "exam_active" not in st.session_state:
    st.session_state.exam_active = False
if "q_start_time" not in st.session_state:
    st.session_state.q_start_time = time.time()
if "time_per_q_sec" not in st.session_state:
    st.session_state.time_per_q_sec = 60
if "marks_per_q" not in st.session_state:
    st.session_state.marks_per_q = 1.0
if "negative_mark" not in st.session_state:
    st.session_state.negative_mark = 0.25

# --- Helper Functions ---
def extract_text_from_pdf(uploaded_file):
    reader = PdfReader(uploaded_file)
    text = ""
    for page in reader.pages:
        extracted = page.extract_text()
        if extracted:
            text += extracted + "\n"
    return text

def parse_mcqs_with_ai(raw_text, api_key):
    client = genai.Client(api_key=api_key)
    prompt = f"""
    Extract all multiple-choice questions from the following text and return them in pure JSON format.
    Return an array of objects where each object has:
    - "question": string
    - "options": list of 4 options (e.g., ["A) Option 1", "B) Option 2", ...])
    - "correct_answer": the exact matching string of the correct option
    - "explanation": brief explanation of why that answer is correct.

    Raw Text:
    {raw_text[:15000]}
    """
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json"
        )
    )
    return json.loads(response.text)

# --- Sidebar: Configuration & Controls ---
with st.sidebar:
    st.header("⚙️ Exam Setup")
    api_key = st.text_input("Gemini API Key", type="password")
    uploaded_file = st.file_uploader("Upload MCQ PDF", type=["pdf"])
    
    time_limit_sec = st.number_input("Timer per Question (Seconds)", min_value=10, max_value=300, value=60, step=5)
    
    st.subheader("Marking Scheme")
    marks_per_q = st.number_input("Marks per Correct Question", min_value=0.5, max_value=5.0, value=1.0, step=0.25)
    negative_mark = st.number_input("Negative Marking Penalty", min_value=0.0, max_value=2.0, value=0.25, step=0.05)
    
    if st.button("Start Exam", use_container_width=True):
        if uploaded_file and api_key:
            with st.spinner("Extracting & parsing questions..."):
                raw_text = extract_text_from_pdf(uploaded_file)
                st.session_state.quiz_data = parse_mcqs_with_ai(raw_text, api_key)
                st.session_state.current_index = 0
                st.session_state.user_answers = {}
                st.session_state.marks_per_q = marks_per_q
                st.session_state.negative_mark = negative_mark
                st.session_state.time_per_q_sec = time_limit_sec
                st.session_state.q_start_time = time.time()
                st.session_state.exam_active = True
                st.rerun()
        else:
            st.warning("Please provide both an API key and an MCQ PDF.")

# --- Exam Active Interface ---
if st.session_state.exam_active and st.session_state.quiz_data:
    total_q = len(st.session_state.quiz_data)
    idx = st.session_state.current_index
    current_q = st.session_state.quiz_data[idx]

    # Top Status Bar: Per-Question Live Timer & Progress
    col_timer, col_prog = st.columns([1, 1])

    with col_timer:
        timer_duration = st.session_state.time_per_q_sec
        timer_html = f"""
        <div style="font-family: sans-serif; background: #1e1e2f; color: #ff4b4b; padding: 10px 16px; border-radius: 8px; display: inline-block; font-weight: bold; font-size: 1.05rem; border: 1px solid #333;">
            ⏱️ Question Timer: <span id="timer_display">{timer_duration}s</span>
        </div>
        <script>
            let timeLeft = {timer_duration};
            const display = document.getElementById('timer_display');
            const countdown = setInterval(function() {{
                timeLeft--;
                if (timeLeft <= 0) {{
                    clearInterval(countdown);
                    display.innerHTML = "TIME UP!";
                    display.style.color = "#ff3333";
                }} else {{
                    display.innerHTML = timeLeft + "s";
                }}
            }}, 1000);
        </script>
        """
        components.html(timer_html, height=55)

    with col_prog:
        st.metric(
            label="Question Progress", 
            value=f"Q {idx + 1} / {total_q}", 
            delta=f"Attempted: {len(st.session_state.user_answers)}"
        )

    st.markdown("---")

    # Display Question
    st.markdown(f"#### **Q{idx + 1}. {current_q['question']}**")

    # Option Selection
    prev_answer = st.session_state.user_answers.get(idx, None)
    selected_option = st.radio(
        "Choose option:",
        options=current_q["options"],
        index=current_q["options"].index(prev_answer) if prev_answer in current_q["options"] else None,
        key=f"q_{idx}"
    )

    if selected_option:
        st.session_state.user_answers[idx] = selected_option

    # Immediate Evaluation & Feedback
    if idx in st.session_state.user_answers:
        user_choice = st.session_state.user_answers[idx]
        is_correct = (user_choice.strip() == current_q["correct_answer"].strip())

        if is_correct:
            st.success(f"✅ **Correct!** (+{st.session_state.marks_per_q} marks)")
        else:
            st.error(f"❌ **Incorrect!** (-{st.session_state.negative_mark} marks)")
            st.info(f"**Correct Answer:** {current_q['correct_answer']}")

        with st.expander("📖 Explanation", expanded=True):
            st.write(current_q.get("explanation", "No detailed explanation provided."))

    st.markdown("---")

    # Navigation Controls
    btn_col1, btn_col2, btn_col3 = st.columns([1, 1, 1])

    with btn_col1:
        if st.button("⬅ Previous", disabled=(idx == 0), use_container_width=True):
            st.session_state.current_index -= 1
            st.session_state.q_start_time = time.time()
            st.rerun()

    with btn_col2:
        if st.button("Finish Exam 🏁", use_container_width=True):
            st.session_state.exam_active = False
            st.rerun()

    with btn_col3:
        if idx < total_q - 1:
            if st.button("Next ➡", use_container_width=True):
                st.session_state.current_index += 1
                st.session_state.q_start_time = time.time()
                st.rerun()

    # Question Quick-Jump Grid
    st.markdown("##### Quick Navigation")
    grid_cols = st.columns(6)
    for i in range(total_q):
        tag = f"{i+1}✓" if i in st.session_state.user_answers else f"{i+1}"
        if grid_cols[i % 6].button(tag, key=f"nav_grid_{i}", use_container_width=True):
            st.session_state.current_index = i
            st.session_state.q_start_time = time.time()
            st.rerun()

# --- Post-Exam Scorecard ---
elif not st.session_state.exam_active and st.session_state.quiz_data:
    st.title("📊 Examination Scorecard")

    total_q = len(st.session_state.quiz_data)
    attempted = len(st.session_state.user_answers)
    unattempted = total_q - attempted

    correct_count = 0
    incorrect_count = 0

    for i, ans in st.session_state.user_answers.items():
        if ans.strip() == st.session_state.quiz_data[i]["correct_answer"].strip():
            correct_count += 1
        else:
            incorrect_count += 1

    positive_score = correct_count * st.session_state.marks_per_q
    negative_penalty = incorrect_count * st.session_state.negative_mark
    net_score = positive_score - negative_penalty
    total_marks = total_q * st.session_state.marks_per_q

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Net Score", f"{net_score:.2f} / {total_marks:.2f}")
    m2.metric("Accuracy", f"{(correct_count / attempted * 100):.1f}%" if attempted > 0 else "0%")
    m3.metric("Correct (+)", f"{correct_count}")
    m4.metric("Incorrect (-)", f"{incorrect_count}")

    st.write(f"- **Attempted:** {attempted} / {total_q}")
    st.write(f"- **Unattempted:** {unattempted}")
    st.write(f"- **Positive Marks Gained:** +{positive_score:.2f}")
    st.write(f"- **Negative Marks Deducted:** -{negative_penalty:.2f}")

    st.markdown("---")
    review_col, restart_col = st.columns(2)
    with review_col:
        if st.button("Review All Questions & Solutions", use_container_width=True):
            st.session_state.exam_active = True
            st.session_state.current_index = 0
            st.rerun()
    with restart_col:
        if st.button("Load Another Test", use_container_width=True):
            st.session_state.quiz_data = []
            st.session_state.user_answers = {}
            st.rerun()

else:
    st.info("Enter your Gemini API key and upload your question PDF in the sidebar to begin.")
