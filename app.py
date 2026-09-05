import streamlit as st
import json
import time
import re
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
    st.session_state.user_answers = {}
if "exam_active" not in st.session_state:
    st.session_state.exam_active = False
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
    # Clean any accidental spaces or hidden characters
    clean_key = api_key.strip()
    client = genai.Client(api_key=clean_key)
    
    prompt = f"""
    Extract multiple-choice questions from the following text and return them in a strict JSON array.
    Each object must have these exact keys:
    - "question": the question prompt
    - "options": list of 4 options (e.g. ["A) ...", "B) ...", "C) ...", "D) ..."])
    - "correct_answer": the full text or prefix of the correct option (e.g. "A) ...")
    - "explanation": a concise explanation of why the answer is correct

    Raw Text:
    {raw_text[:12000]}
    """
    
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        data = json.loads(response.text)
        return data, None
    except Exception as e:
        return None, str(e)

# --- Sidebar: Controls ---
with st.sidebar:
    st.header("⚙️ Exam Setup")
    api_key = st.text_input("Gemini API Key", type="password", help="Paste your key from Google AI Studio")
    uploaded_file = st.file_uploader("Upload MCQ PDF", type=["pdf"])
    
    time_limit_sec = st.number_input("Timer per Question (Seconds)", min_value=10, max_value=300, value=60, step=5)
    
    st.subheader("Marking Scheme")
    marks_per_q = st.number_input("Marks per Correct Question", min_value=0.5, max_value=5.0, value=1.0, step=0.25)
    negative_mark = st.number_input("Negative Marking Penalty", min_value=0.0, max_value=2.0, value=0.25, step=0.05)
    
    if st.button("Start Exam", use_container_width=True):
        if uploaded_file and api_key.strip():
            with st.spinner("Extracting & preparing questions..."):
                raw_text = extract_text_from_pdf(uploaded_file)
                if not raw_text.strip():
                    st.error("No readable text found in PDF. Make sure it is not a scanned image PDF.")
                else:
                    parsed_questions, err = parse_mcqs_with_ai(raw_text, api_key)
                    if err:
                        st.error(f"API Error: {err}")
                    elif not parsed_questions:
                        st.warning("Could not extract MCQs from this document format.")
                    else:
                        st.session_state.quiz_data = parsed_questions
                        st.session_state.current_index = 0
                        st.session_state.user_answers = {}
                        st.session_state.marks_per_q = marks_per_q
                        st.session_state.negative_mark = negative_mark
                        st.session_state.time_per_q_sec = time_limit_sec
                        st.session_state.exam_active = True
                        st.rerun()
        else:
            st.warning("Please provide both a valid Gemini API Key and upload an MCQ PDF.")

# --- Exam Active Interface ---
if st.session_state.exam_active and st.session_state.quiz_data:
    total_q = len(st.session_state.quiz_data)
    idx = st.session_state.current_index
    current_q = st.session_state.quiz_data[idx]

    col_timer, col_prog = st.columns([1, 1])

    with col_timer:
        timer_duration = st.session_state.time_per_q_sec
        # HTML/JS timer that resets on every question change
        timer_html = f"""
        <div style="font-family: sans-serif; background: #1e1e2f; color: #ff4b4b; padding: 10px 16px; border-radius: 8px; display: inline-block; font-weight: bold; font-size: 1.05rem; border: 1px solid #333;">
            ⏱️ Timer: <span id="timer_display">{timer_duration}s</span>
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

    # Question text
    st.markdown(f"#### **Q{idx + 1}. {current_q['question']}**")

    # Options
    prev_answer = st.session_state.user_answers.get(idx, None)
    selected_option = st.radio(
        "Choose option:",
        options=current_q["options"],
        index=current_q["options"].index(prev_answer) if prev_answer in current_q["options"] else None,
        key=f"q_{idx}"
    )

    if selected_option:
        st.session_state.user_answers[idx] = selected_option

    # Feedback & Explanation
    if idx in st.session_state.user_answers:
        user_choice = st.session_state.user_answers[idx]
        is_correct = (user_choice.strip() == current_q["correct_answer"].strip())

        if is_correct:
            st.success(f"✅ **Correct!** (+{st.session_state.marks_per_q} marks)")
        else:
            st.error(f"❌ **Incorrect!** (-{st.session_state.negative_mark} marks)")
            st.info(f"**Correct Answer:** {current_q['correct_answer']}")

        with st.expander("📖 Explanation", expanded=True):
            st.write(current_q.get("explanation", "No explanation provided."))

    st.markdown("---")

    # Buttons
    btn_col1, btn_col2, btn_col3 = st.columns([1, 1, 1])

    with btn_col1:
        if st.button("⬅ Previous", disabled=(idx == 0), use_container_width=True):
            st.session_state.current_index -= 1
            st.rerun()

    with btn_col2:
        if st.button("Finish Exam 🏁", use_container_width=True):
            st.session_state.exam_active = False
            st.rerun()

    with btn_col3:
        if idx < total_q - 1:
            if st.button("Next ➡", use_container_width=True):
                st.session_state.current_index += 1
                st.rerun()

    # Question Quick-Jump Grid
    st.markdown("##### Quick Navigation")
    grid_cols = st.columns(6)
    for i in range(total_q):
        tag = f"{i+1}✓" if i in st.session_state.user_answers else f"{i+1}"
        if grid_cols[i % 6].button(tag, key=f"nav_grid_{i}", use_container_width=True):
            st.session_state.current_index = i
            st.rerun()

# --- Post-Exam Result Screen ---
elif not st.session_state.exam_active and st.session_state.quiz_data:
    st.title("📊 Examination Scorecard")

    total_q = len(st.session_state.quiz_data)
    attempted = len(st.session_state.user_answers)
    unattempted = total_q - attempted

    correct_count = sum(1 for i, ans in st.session_state.user_answers.items() if ans.strip() == st.session_state.quiz_data[i]["correct_answer"].strip())
    incorrect_count = attempted - correct_count

    positive_score = correct_count * st.session_state.marks_per_q
    negative_penalty = incorrect_count * st.session_state.negative_mark
    net_score = positive_score - negative_penalty
    total_marks = total_q * st.session_state.marks_per_q

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Net Score", f"{net_score:.2f} / {total_marks:.2f}")
    m2.metric("Accuracy", f"{(correct_count / attempted * 100):.1f}%" if attempted > 0 else "0%")
    m3.metric("Correct (+)", f"{correct_count}")
    m4.metric("Incorrect (-)", f"{incorrect_count}")

    st.write(f"- **Total Questions:** {total_q}")
    st.write(f"- **Attempted:** {attempted}")
    st.write(f"- **Unattempted:** {unattempted}")
    st.write(f"- **Marks Gained:** +{positive_score:.2f}")
    st.write(f"- **Marks Deducted:** -{negative_penalty:.2f}")

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
