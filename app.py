from datetime import datetime, timedelta
from io import BytesIO
import streamlit as st
import hashlib
import re
import time
import os

import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import textwrap

from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors

# Local imports
from models_utils import AssessmentAgent, TutorAgent
from image_utils import get_similar_images
from database import Database

# ===============================================================
# PAGE CONFIG
# ===============================================================
st.set_page_config(
    page_title="Student Personalized Learning System",
    page_icon="📚",
    layout="wide"
)

# ===============================================================
# SESSION STATE SETUP - COMPLETE VERSION
# ===============================================================
def initialize_session_state():
    """Initialize all session state variables"""
    defaults = {
        'logged_in': False,
        'user': None,
        'extracted_text': None,
        'current_subject': None,
        'show_signup': False,
        'quiz_start_time': None,
        'quiz_answers': {},
        'current_quiz': None,
        'practice_questions': None,
        'practice_topic': None,
        'generated_questions': None,
    }
    
    for key, default in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default


initialize_session_state()

# ===============================================================
# INITIALIZE COMPONENTS
# ===============================================================
db = Database()
assessment = AssessmentAgent()
tutor = TutorAgent()

# ===============================================================
# HELPER FUNCTIONS
# ===============================================================
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def validate_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_password(password):
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"
    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter"
    if not re.search(r'[0-9]', password):
        return False, "Password must contain at least one number"
    return True, "Password is strong"

def generate_progress_pdf(student_data, progress_data, gamification_data):
    """Generate PDF report of student progress"""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()
    
    title = Paragraph(f"<b>Progress Report - {student_data['full_name']}</b>", styles['Title'])
    elements.append(title)
    elements.append(Spacer(1, 12))
    
    # Student Info
    info_data = [
        ['Email:', student_data['email']],
        ['Class:', student_data['class']],
        ['Level:', str(gamification_data.get('level', 'N/A'))],
        ['Total Points:', str(gamification_data.get('total_points', 0))],
        ['Current Streak:', f"{gamification_data.get('current_streak', 0)} days"],
    ]
    info_table = Table(info_data)
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 12))
    
    if progress_data:
        elements.append(Paragraph("<b>Subject Performance</b>", styles['Heading2']))
        progress_table_data = [['Subject', 'Topic', 'Accuracy', 'Attempts']]
        for p in progress_data:
            accuracy = round((p['correct_attempts'] / p['attempts']) * 100, 1) if p['attempts'] else 0
            progress_table_data.append([
                p['subject'],
                p['topic'],
                f"{accuracy}%",
                str(p['attempts'])
            ])
        
        progress_table = Table(progress_table_data)
        progress_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        elements.append(progress_table)
    
    doc.build(elements)
    buffer.seek(0)
    return buffer

# ===============================================================
# AUTH PAGES
# ===============================================================
def signup_page():
    st.title("🎓 Create Your Account")
    st.subheader("Student / Teacher / Parent Registration")

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("signup_form"):
            full_name = st.text_input("Full Name*")
            email = st.text_input("Email*")
            password = st.text_input("Password*", type="password")
            confirm_password = st.text_input("Confirm Password*", type="password")

            role = st.selectbox("Role*", ['student', 'teacher', 'parent'])
            student_class = st.selectbox("Select Class*", [f"Grade {i}" for i in range(1, 13)])

            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                submit_button = st.form_submit_button("Sign Up")
            with col_btn2:
                back_button = st.form_submit_button("Back to Login")

            if back_button:
                st.session_state.show_signup = False
                st.rerun()

            if submit_button:
                errors = []
                if not full_name.strip():
                    errors.append("Please enter your full name.")
                if not validate_email(email):
                    errors.append("Invalid email format.")
                valid, msg = validate_password(password)
                if not valid:
                    errors.append(msg)
                if password != confirm_password:
                    errors.append("Passwords do not match.")

                if errors:
                    for e in errors:
                        st.error(e)
                else:
                    if db.get_user_by_email(email):
                        st.error("An account with this email already exists.")
                    else:
                        user_data = {
                            'full_name': full_name.strip(),
                            'email': email.lower().strip(),
                            'password_hash': hash_password(password),
                            'role': role,
                            'class': student_class
                        }
                        if db.create_user(user_data):
                            st.success("🎉 Account created! Please log in.")
                            st.session_state.show_signup = False
                            st.rerun()
                        else:
                            st.error("Account creation failed. Try again.")

def login_page():
    st.title("🎓 Student Personalized Learning System")
    st.subheader("Login to Your Account")

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")

        col_login, col_signup = st.columns(2)
        with col_login:
            if st.button("Login"):
                if not email or not password:
                    st.warning("Enter both email and password.")
                else:
                    user = db.get_user_by_email(email)
                    if user and (user['password_hash'] == hash_password(password) or user['password_hash'] == password):
                        st.session_state.logged_in = True
                        st.session_state.user = user
                        st.rerun()
                    else:
                        st.error("Invalid credentials.")
        with col_signup:
            if st.button("Sign Up"):
                st.session_state.show_signup = True
                st.rerun()

# ===============================================================
# STUDENT DASHBOARD
# ===============================================================

def student_dashboard():
    user = st.session_state.user
    
    gamification = db.get_student_gamification(user['id'])
    if not gamification:
        db._initialize_gamification(user['id'])
        gamification = db.get_student_gamification(user['id'])    
    st.title(f"Welcome, {user['full_name']}! 📚")
    # ... rest of the code
    badges = db.get_student_badges(user['id'])
    notifications = db.get_user_notifications(user['id'], unread_only=True)

    with st.sidebar:
        st.subheader("👤 User Info")
        st.write(f"**Email:** {user['email']}")
        st.write(f"**Class:** {user['class']}")
        st.write(f"**Role:** {user['role'].title()}")
        
        if gamification:
            st.markdown("---")
            st.subheader("🎮 Gamification")
            st.write(f"**Level:** {gamification['level']}")
            st.write(f"**Points:** {gamification['total_points']}")
            st.write(f"**Streak:** 🔥 {gamification['current_streak']} days")
            
            current_points = gamification['total_points']
            next_level_points = gamification['level'] * 100
            progress = min((current_points % 100) / 100, 1.0)
            st.progress(progress)
            st.caption(f"{100 - (current_points % 100)} points to Level {gamification['level'] + 1}")
        
        if badges:
            st.markdown("---")
            st.subheader("🏆 Recent Badges")
            for badge in badges[:3]:
                st.write(f"{badge['badge_icon']} {badge['badge_name']}")
        
        if notifications:
            st.markdown("---")
            st.subheader(f"🔔 Notifications ({len(notifications)})")
            for notif in notifications[:3]:
                with st.expander(notif['title']):
                    st.write(notif['message'])
                    if st.button("Mark Read", key=f"notif_{notif['id']}"):
                        db.mark_notification_read(notif['id'])
                        st.rerun()
        
        st.markdown("---")
        if st.button("Logout"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📄 Paper Analysis", 
        "📘 Personalized Learning", 
        "✏️ Practice & Feedback",
        "🎯 Quizzes",
        "🏆 Achievements",
        "📚 Curriculum"
    ])

    # ==================== TAB 1: Paper Analysis ====================
    with tab1:
        st.header("📄 Analyze Exam Paper")

        student_class = st.session_state.user["class"]
        subjects = db.get_all_subjects_for_class(student_class)
        
        if subjects:
            subject = st.selectbox("Select Subject", subjects)
        else:
            st.warning(f"No subjects found for {student_class}. Please add curriculum first.")
            st.stop()

        uploaded_file = st.file_uploader(
            "Upload your paper (image or PDF)", 
            type=["jpg", "jpeg", "png", "pdf"]
        )

        if uploaded_file and st.button("🔍 Extract & Analyze Paper"):
            with st.spinner("Extracting and analyzing..."):
                # Extract text based on file type
                if uploaded_file.type == "application/pdf":
                    extracted_text = assessment.extract_text_from_pdf(uploaded_file)
                else:
                    extracted_text = assessment.extract_text_from_paper(uploaded_file)
                
                if not extracted_text:
                    st.error("Failed to extract text. Please try again.")
                else:
                    st.session_state.extracted_text = extracted_text
                    st.text_area("📝 Extracted Text", extracted_text, height=250)

                    # FETCH CURRICULUM FOR ANALYSIS
                    curriculum = db.get_curriculum(student_class, subject)
                    
                    if not curriculum:
                        st.warning("⚠️ Curriculum not found for this subject. Analysis may be less accurate.")
                        curriculum = "No curriculum available - Please add curriculum for better analysis."
                    
                    # PASS CURRICULUM TO ANALYZE FUNCTION
                    analysis = assessment.analyze_student_paper(
                        extracted_text=extracted_text,
                        subject=subject,
                        curriculum=curriculum,  
                        student_class=student_class
                    )
                    
                    if analysis:
                        st.markdown("### 📊 Analysis Results")
                        st.markdown(analysis)
                        
                        # Save analysis to database
                        db.save_paper_analysis(
                            student_class, user["id"], user["full_name"], 
                            subject, extracted_text, analysis
                        )
                        st.success("✅ Analysis saved successfully! +10 points earned!")
                    else:
                        st.error("❌ Failed to analyze paper. Please try again.")
        
        st.divider()
        st.subheader("📚 Past Analyses")
        history = db.get_student_analysis_history(user["id"])
        if history:
            for record in history:
                with st.expander(f"{record['subject']} — {record['created_at']}"):
                    st.write(record["analysis_by_model"])
        else:
            st.info("No previous analyses found.")

    # ==================== TAB 2: Personalized Learning ====================
    with tab2:
        st.header("📘 Personalized Learning")

        student_id = user["id"]
        student_class = user["class"]

        # Get all weak topics
        weak_topics = db.get_weak_topics_history(student_id)

        if not weak_topics:
            st.info("No weak topics found. Analyze a paper first!")
            st.stop()

        # Extract unique subjects from weak topics
        available_subjects = sorted(set([t["subject"] for t in weak_topics if t.get("subject")]))
        
        if not available_subjects:
            st.warning("No subjects found in weak topics.")
            st.stop()
        
        # Subject dropdown filter
        col1, col2 = st.columns([2, 3])
        with col1:
            selected_subject = st.selectbox(
                "📚 Select Subject", 
                available_subjects,
                key="personalized_subject_filter"
            )
        
        # Filter topics by selected subject
        filtered_topics = [t["weak_area"] for t in weak_topics if t["subject"] == selected_subject]
        
        if not filtered_topics:
            st.warning(f"No weak topics found for {selected_subject}.")
            st.stop()
        
        # Remove duplicates and sort
        filtered_topics = sorted(set(filtered_topics))
        
        with col2:
            selected_topic = st.selectbox(
                "📌 Select Weak Topic", 
                filtered_topics,
                key="personalized_topic_select"
            )

        # Generate button
        if st.button("✨ Generate Learning Material", width='stretch'):
            with st.spinner("Generating personalized learning content..."):
                # Fetch curriculum for learning content
                curriculum = db.get_curriculum(student_class, selected_subject)
                
                if not curriculum:
                    st.warning(f"⚠️ No curriculum found for {selected_subject}. Generating content without curriculum reference.")
                    curriculum = ""
                
                # Generate learning content
                learning_content = tutor.generate_learning_content(
                    weak_area=selected_topic,
                    subject=selected_subject,
                    student_class=student_class,
                    curriculum=curriculum
                )

            if learning_content:
                # Store learning content in session state
                st.session_state["learning_content"] = learning_content
                st.session_state["learning_topic"] = selected_topic
                st.session_state["learning_subject"] = selected_subject
                
                # Initialize chat history
                if "chat_history" not in st.session_state:
                    st.session_state["chat_history"] = []
                
                # Fetch related images
                with st.spinner("🖼️ Finding relevant images..."):
                    from image_utils import get_similar_images
                    
                    similar_images = get_similar_images(
                        db=db,
                        topic=selected_topic,
                        subject=selected_subject,
                        top_k=2
                    )
                    
                    # Store images in session state
                    st.session_state["learning_images"] = similar_images
                
                st.rerun()
            else:
                st.error("❌ Unable to generate learning material. Please try again later.")

        # Display content if it exists in session state
        if "learning_content" in st.session_state:
            # Check if content matches currently selected subject/topic
            if (st.session_state.get("learning_subject") == selected_subject and 
                st.session_state.get("learning_topic") == selected_topic):
                
                st.markdown("---")
                st.markdown("### 📘 Personalized Learning Material")
                
                # Display images if available
                if st.session_state.get("learning_images"):
                    st.markdown("#### 🖼️ Related Visual Resources")
                    
                    images = st.session_state["learning_images"]
                    
                    # Display images in columns
                    if len(images) == 1:
                        col_img = st.columns(1)
                        cols = [col_img]
                    else:
                        cols = st.columns(len(images))
                    
                    for idx, img in enumerate(images):
                        with cols[idx]:
                            try:
                                # Display image
                                st.image(
                                    img['image_path'], 
                                    caption=f"{img['file_name']}\nRelevance: {img['similarity_score']*100:.1f}%",
                                    width='stretch'
                                )
                            except Exception as e:
                                st.error(f"❌ Could not load image: {img['file_name']}")
                                print(f"Image loading error: {e}")
                    
                    st.markdown("---")
                
                # Display learning content
                st.markdown(st.session_state["learning_content"])

                st.markdown("---")
                
                # ==================== NEW: CHAT FEATURE ====================
                st.markdown("### 💬 Chat with AI Tutor")
                st.caption("Ask questions about this topic to understand it better!")
                
                # Initialize chat history if not exists
                if "chat_history" not in st.session_state:
                    st.session_state["chat_history"] = []
                
                # Display chat history
                chat_container = st.container()
                with chat_container:
                    if st.session_state["chat_history"]:
                        for message in st.session_state["chat_history"]:
                            if message["role"] == "student":
                                with st.chat_message("user", avatar="🧑‍🎓"):
                                    st.markdown(message["content"])
                            else:
                                with st.chat_message("assistant", avatar="👨‍🏫"):
                                    st.markdown(message["content"])
                    else:
                        st.info("💡 Start by asking a question about this topic!")
                
                # Chat input
                user_question = st.chat_input(
                    "Ask a question about this topic...",
                    key=f"chat_input_{selected_topic}"
                )
                
                if user_question:
                    # Add user message to history
                    st.session_state["chat_history"].append({
                        "role": "student",
                        "content": user_question
                    })
                    
                    # Display user message immediately
                    with st.chat_message("user", avatar="🧑‍🎓"):
                        st.markdown(user_question)
                    
                    # Get AI response
                    with st.chat_message("assistant", avatar="👨‍🏫"):
                        with st.spinner("Thinking..."):
                            ai_response = tutor.chat_about_topic(
                                topic=st.session_state["learning_topic"],
                                subject=st.session_state["learning_subject"],
                                learning_content=st.session_state["learning_content"],
                                chat_history=st.session_state["chat_history"][:-1],  # Exclude current question
                                user_message=user_question
                            )
                        
                        # Display response (streaming already handled in function)
                        if not ai_response:
                            ai_response = "I'm having trouble responding. Please try again!"
                    
                    # Add AI response to history
                    st.session_state["chat_history"].append({
                        "role": "tutor",
                        "content": ai_response
                    })
                    
                    # Award points for engagement
                    db.add_points(student_id, 3, f"Asked question about {selected_topic}")
                    
                    st.rerun()
                
                # Clear chat button
                col_clear_chat, col_space = st.columns([1, 3])
                with col_clear_chat:
                    if st.button("🗑️ Clear Chat", key="clear_chat_btn"):
                        st.session_state["chat_history"] = []
                        st.success("Chat cleared!")
                        st.rerun()
                
                st.markdown("---")
                
                # Action buttons
                col_save, col_clear = st.columns([1, 1])
                
                with col_save:
                    if st.button("✅ Mark as Learned & Save", width='stretch'):
                        success = db.save_learned_topic(
                            student_id=student_id,
                            class_name=student_class,
                            subject=st.session_state["learning_subject"],
                            topic=st.session_state["learning_topic"],
                            content=st.session_state["learning_content"]
                        )
                    
                        if success:
                            st.success(f"✅ '{st.session_state['learning_topic']}' saved! +15 points earned!")
                            # Clear session state
                            del st.session_state["learning_content"]
                            del st.session_state["learning_topic"]
                            del st.session_state["learning_subject"]
                            if "learning_images" in st.session_state:
                                del st.session_state["learning_images"]
                            if "chat_history" in st.session_state:
                                del st.session_state["chat_history"]
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error("❌ Failed to save this topic. Please try again later.")
                
                with col_clear:
                    if st.button("🔄 Generate New Material", width='stretch'):
                        # Clear session state to allow new generation
                        del st.session_state["learning_content"]
                        del st.session_state["learning_topic"]
                        del st.session_state["learning_subject"]
                        if "learning_images" in st.session_state:
                            del st.session_state["learning_images"]
                        if "chat_history" in st.session_state:
                            del st.session_state["chat_history"]
                        st.rerun()
            else:
                # Content exists but for different subject/topic
                st.info(f"💡 You have unsaved learning material for {st.session_state.get('learning_subject')} - {st.session_state.get('learning_topic')}. Please save or clear it first.")
                
                if st.button("🗑️ Clear Previous Material", width='content'):
                    del st.session_state["learning_content"]
                    del st.session_state["learning_topic"]
                    del st.session_state["learning_subject"]
                    if "learning_images" in st.session_state:
                        del st.session_state["learning_images"]
                    if "chat_history" in st.session_state:
                        del st.session_state["chat_history"]
                    st.rerun()
    # ==================== TAB 3: Practice & Feedback ====================
    with tab3:
        st.header("✏️ Practice & Feedback")

        student_id = user["id"]
        student_class = user["class"]

        learned_records = db.get_learned_topics(student_id, student_class)

        
        if not learned_records:
            st.info("No subjects available yet. Learn topics first from the 'Personalized Learning' tab.")
            st.stop()
        
        subjects = sorted(list({rec["subject"] for rec in learned_records if rec.get("subject")}))
        subject = st.selectbox("Select Subject", subjects, key="practice_subject")
        topics = [rec["topic"] for rec in learned_records if rec["subject"] == subject]

        if not topics:
            st.warning(f"No topics found for {subject}.")
            st.stop()

        topic = st.selectbox("Select Topic for Practice", topics)

        # Generate questions button
        col1, col2 = st.columns([1, 3])
        with col1:
            if st.button("🧩 Generate Questions", key="gen_practice", width='stretch'):
                with st.spinner("Generating practice questions..."):
                    questions = tutor.generate_practice_questions(topic, subject, student_class)
                    if questions:
                        st.session_state["practice_questions"] = questions
                        st.session_state["practice_topic"] = topic
                        st.success(f"✅ Generated {len(questions)} questions!")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("❌ Failed to generate questions.")

        # Display questions if they exist and match current topic
        if (st.session_state.get("practice_questions") and 
            st.session_state.get("practice_topic") == topic):
            
            st.markdown("---")
            st.markdown("### 📝 Practice Questions")

            for i, q in enumerate(st.session_state["practice_questions"], start=1):
                st.markdown(f"Q{i}. {q['question']}")
                
                # Create unique key for each question
                answer_key = f"practice_ans_{topic}_{i}"
                
                # Use session state to preserve answers
                if answer_key not in st.session_state:
                    st.session_state[answer_key] = ""
                
                student_answer = st.text_area(
                    f"Your Answer:", 
                    value=st.session_state[answer_key],
                    key=f"textarea_{answer_key}",
                    height=100
                )
                
                # Update session state
                st.session_state[answer_key] = student_answer
                
                col_check, col_show = st.columns([1, 2])
                
                with col_check:
                    if st.button(f"✅ Check", key=f"check_{topic}_{i}"):
                        if not student_answer.strip():
                            st.warning("Please write an answer first!")
                        else:
                            with st.spinner("Evaluating..."):
                                result = tutor.evaluate_answer(
                                    subject=subject,
                                    question=q["question"],
                                    answer=student_answer,
                                    correct_answer=q.get("correct_answer", ""),
                                    explanation=q.get("explanation", "")
                                )

                            if result and "feedback" in result:
                                st.markdown(f"**💬 Feedback:** {result['feedback']}")
                                
                                # Save to database
                                db.save_practice_result(
                                    student_id, subject, topic,
                                    q["question"], student_answer, result["feedback"]
                                )
                                
                                points_earned = 5 if result.get('is_correct') else 2
                                st.success(f"📊 +{points_earned} points earned!")
                            else:
                                st.error("❌ Evaluation failed.")
                
                st.markdown("---")

        # Progress section
        st.subheader("📈 Your Practice Progress")
        progress = db.get_student_progress(student_id, subject)
        
        if progress:
            progress_data = []
            for p in progress:
                accuracy = round((p['correct_attempts'] / p['attempts']) * 100, 1) if p['attempts'] else 0
                progress_data.append({
                    'Topic': p['topic'],
                    'Accuracy': f"{accuracy}%",
                    'Correct': p['correct_attempts'],
                    'Total': p['attempts']
                })
            
            progress_df = pd.DataFrame(progress_data)
            st.dataframe(progress_df, width='stretch')
        else:
            st.info("No practice results yet. Start answering questions!")

    # ==================== TAB 4: Quizzes ====================
    with tab4:
        # Check if currently taking a quiz
        if st.session_state.get('current_quiz'):
            quiz_id = st.session_state['current_quiz']
            start_time = st.session_state.get('quiz_start_time', time.time())
            
            # Get quiz details
            student_class = user["class"]
            quizzes = db.get_quizzes_for_class(student_class)
            quiz = next((q for q in quizzes if q['id'] == quiz_id), None)
            
            if not quiz:
                st.error("Quiz not found")
                st.session_state.pop('current_quiz', None)
                st.session_state.pop('quiz_start_time', None)
                st.rerun()
            
            st.header(f"📝 {quiz['title']}")
            
            # Timer
            elapsed_time = int(time.time() - start_time)
            remaining_time = max(quiz['duration_minutes'] * 60 - elapsed_time, 0)
            
            # Display timer
            timer_placeholder = st.empty()
            with timer_placeholder.container():
                col1, col2 = st.columns([3, 1])
                with col2:
                    mins, secs = divmod(remaining_time, 60)
                    if remaining_time < 60:
                        st.error(f"⏱️ {mins}:{secs:02d}")
                    elif remaining_time < 300:
                        st.warning(f"⏱️ {mins}:{secs:02d}")
                    else:
                        st.info(f"⏱️ {mins}:{secs:02d}")
            
            # Auto-submit if time's up
            if remaining_time == 0:
                st.error("⏰ Time's up! Auto-submitting...")
                time_taken = quiz['duration_minutes'] * 60
                attempt_id = db.submit_quiz_attempt(
                    quiz_id, user['id'], 
                    st.session_state.get('quiz_answers', {}), 
                    time_taken
                )
                st.session_state.pop('current_quiz', None)
                st.session_state.pop('quiz_start_time', None)
                st.session_state['quiz_answers'] = {}
                time.sleep(2)
                st.rerun()
            
            # Get questions
            questions = db.get_quiz_questions(quiz_id)
            
            if not questions:
                st.error("No questions found for this quiz")
                st.stop()
            
            st.divider()
            
            # Display questions
            for i, q in enumerate(questions):
                st.markdown(f"**Q{i+1}. {q['question_text']}** ({q['marks']} marks)")
                
                answer_key = str(q['id'])
                
                if q['question_type'] == 'mcq':
                    options = q.get('options', [])
                    if not options:
                        st.error("No options available for this question")
                        continue
                    
                    current_answer = st.session_state.get('quiz_answers', {}).get(answer_key)
                    
                    answer = st.radio(
                        "Select your answer:",
                        options,
                        key=f"quiz_q_{q['id']}_{i}",
                        index=options.index(current_answer) if current_answer in options else None
                    )
                    
                    if answer:
                        if 'quiz_answers' not in st.session_state:
                            st.session_state['quiz_answers'] = {}
                        st.session_state['quiz_answers'][answer_key] = answer
                
                elif q['question_type'] == 'short_answer':
                    answer = st.text_input(
                        "Your answer:",
                        value=st.session_state.get('quiz_answers', {}).get(answer_key, ""),
                        key=f"quiz_q_{q['id']}_{i}"
                    )
                    if answer:
                        if 'quiz_answers' not in st.session_state:
                            st.session_state['quiz_answers'] = {}
                        st.session_state['quiz_answers'][answer_key] = answer
                
                else:  # long_answer
                    answer = st.text_area(
                        "Your answer:",
                        value=st.session_state.get('quiz_answers', {}).get(answer_key, ""),
                        key=f"quiz_q_{q['id']}_{i}",
                        height=150
                    )
                    if answer:
                        if 'quiz_answers' not in st.session_state:
                            st.session_state['quiz_answers'] = {}
                        st.session_state['quiz_answers'][answer_key] = answer
                
                st.markdown("---")
            
            # Submit button
            st.markdown("###")
            col1, col2, col3 = st.columns([1, 1, 1])
            with col2:
                if st.button("✅ Submit Quiz", type="primary", width='stretch'):
                    answered = len(st.session_state.get('quiz_answers', {}))
                    total = len(questions)
                    
                    if answered < total:
                        st.warning(f"⚠️ You've answered {answered}/{total} questions. Submit anyway?")
                        if st.button("Yes, Submit", key="confirm_submit"):
                            time_taken = int(time.time() - start_time)
                            attempt_id = db.submit_quiz_attempt(
                                quiz_id, user['id'], 
                                st.session_state.get('quiz_answers', {}), 
                                time_taken
                            )
                            if attempt_id:
                                st.success("✅ Quiz submitted! +20 points!")
                                st.session_state.pop('current_quiz', None)
                                st.session_state.pop('quiz_start_time', None)
                                st.session_state['quiz_answers'] = {}
                                time.sleep(2)
                                st.rerun()
                    else:
                        time_taken = int(time.time() - start_time)
                        attempt_id = db.submit_quiz_attempt(
                            quiz_id, user['id'], 
                            st.session_state.get('quiz_answers', {}), 
                            time_taken
                        )
                        if attempt_id:
                            st.success("✅ Quiz submitted successfully! +20 points!")
                            st.session_state.pop('current_quiz', None)
                            st.session_state.pop('quiz_start_time', None)
                            st.session_state['quiz_answers'] = {}
                            time.sleep(2)
                            st.rerun()
                        else:
                            st.error("Failed to submit quiz")
        
        else:
            # Show available quizzes
            st.header("🎯 Available Quizzes")
            
            student_class = user["class"]
            quizzes = db.get_quizzes_for_class(student_class)
            
            if not quizzes:
                st.info("No quizzes available at the moment.")
            else:
                for quiz in quizzes:
                    with st.expander(f"📝 {quiz['title']} - {quiz['subject']}", expanded=False):
                        col1, col2, col3 = st.columns(3)
                        col1.metric("⏱️ Duration", f"{quiz['duration_minutes']} min")
                        col2.metric("📊 Total Marks", quiz['total_marks'])
                        
                        deadline = quiz.get('deadline')
                        if deadline:
                            if datetime.now() > deadline:
                                col3.error("⏰ Deadline Passed")
                                continue
                            else:
                                col3.info(f"📅 Due: {deadline.strftime('%d %b %Y')}")
                        
                        st.write(f"**👨‍🏫 Teacher:** {quiz.get('teacher_name', 'Unknown')}")
                        
                        # Check if already attempted
                        attempts = db.get_student_quiz_attempts(user['id'], quiz['id'])
                        
                        if attempts and attempts[0].get('score') is not None:
                            score = attempts[0].get('score', 0)
                            total = attempts[0]['total_marks']
                            percentage = round((score / total * 100), 1) if total > 0 else 0
                            
                            st.success(f"✅ Completed - Score: {score}/{total} ({percentage}%)")
                            
                            if attempts[0].get('feedback'):
                                st.write("**📝 Feedback:**")
                                st.info(attempts[0]['feedback'])
                        else:
                            col_start, col_space = st.columns([1, 2])
                            with col_start:
                                if st.button("▶️ Start Quiz", key=f"start_{quiz['id']}", width='stretch'):
                                    st.session_state['current_quiz'] = quiz['id']
                                    st.session_state['quiz_start_time'] = time.time()
                                    st.session_state['quiz_answers'] = {}
                                    st.rerun()

    # ==================== TAB 5: Achievements ====================
    with tab5:
        st.header("🏆 Your Achievements")
        
        if gamification:
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("🎯 Level", gamification['level'])
            col2.metric("⭐ Total Points", gamification['total_points'])
            col3.metric("🔥 Current Streak", f"{gamification['current_streak']} days")
            col4.metric("💪 Longest Streak", f"{gamification['longest_streak']} days")
            
            # Performance trend
            st.subheader("📈 Performance Trend (Last 30 Days)")
            trend_data = db.get_student_performance_trend(user['id'], days=30)
            
            if trend_data:
                df = pd.DataFrame(trend_data)
                fig = px.line(df, x='date', y='avg_score', 
                             title='Quiz Performance Over Time',
                             labels={'avg_score': 'Average Score (%)', 'date': 'Date'},
                             markers=True)
                fig.update_traces(line_color='#1f77b4', line_width=4)
                fig.update_yaxes(range=[0, 100])
                st.plotly_chart(fig, width='stretch')
            else:
                st.info("Complete quizzes to see your performance trend!")
        
        st.divider()
        st.subheader("🏅 Badges Earned")
        
        if badges:
            # Display in a grid
            cols = st.columns(4)
            for idx, badge in enumerate(badges):
                with cols[idx % 4]:
                    st.markdown(f"<div style='text-align: center; padding: 20px; background-color: #f0f2f6; border-radius: 10px; margin: 10px 0;'>"
                              f"<div style='font-size: 48px;'>{badge['badge_icon']}</div>"
                              f"<div style='font-weight: bold; margin-top: 10px;'>{badge['badge_name']}</div>"
                              f"<div style='font-size: 12px; color: #666;'>{badge['badge_description']}</div>"
                              f"<div style='font-size: 11px; color: #999; margin-top: 5px;'>{badge['earned_at'].strftime('%Y-%m-%d')}</div>"
                              f"</div>", unsafe_allow_html=True)
        else:
            st.info("🎯 Keep learning to earn badges!")
        
        # Export Progress Report
        st.divider()
        st.subheader("📊 Export Progress Report")
        
        col_export1, col_export2 = st.columns([1, 3])
        with col_export1:
            if st.button("📥 Generate PDF Report", width='stretch'):
                # ✅ ADD THIS CHECK
                if not gamification:
                    st.error("❌ Cannot generate report: Gamification data not available.")
                else:
                    with st.spinner("Generating report..."):
                        progress_data = db.get_student_progress(user['id'])
                        pdf_buffer = generate_progress_pdf(user, progress_data, gamification)  # ✅ Pass gamification directly
                        
                        st.download_button(
                            label="📄 Download PDF",
                            data=pdf_buffer,
                            file_name=f"progress_report_{user['full_name'].replace(' ', '_')}.pdf",
                            mime="application/pdf",
                            width='stretch'
                        )

    # ==================== TAB 6: Curriculum ====================
    with tab6:
        st.header("📚 View Curriculum")
        student_class = user["class"]
    
        # Create two columns for better layout
        col_header1, col_header2 = st.columns([3, 1])
    
        with col_header1:
            st.subheader("Available Subjects")
    
        with col_header2:
            if st.button("🔄 Refresh", width='stretch'):
                st.rerun()
    
        # Add New Subject Section
        with st.expander("➕ Request New Subject Curriculum", expanded=False):
            st.markdown("**Can't find your subject?** Add it here and your teacher will be notified.")
        
            new_subject = st.text_input(
                "Enter Subject Name",
                placeholder="e.g., Physics, Chemistry, Biology",
                key="new_subject_input"
            )
        
            if st.button("📌 Add Subject", key="add_new_subject"):
                if new_subject and new_subject.strip():
                    success, message = db.add_subject_for_class(student_class, new_subject.strip())
                
                    if success:
                        st.success(f"✅ {message}")
                        st.info("📧 Your teacher will be notified to add curriculum content.")
                        time.sleep(2)
                        st.rerun()
                    else:
                        st.warning(f"⚠️ {message}")
                else:
                    st.error("Please enter a subject name!")
    
        st.markdown("---")
    
        # View Existing Curriculum
        subjects = db.get_all_subjects_for_class(student_class)
    
        if not subjects:
            st.info("📭 No subjects available for your class yet.")
            st.markdown("**💡 Tip:** Use the 'Request New Subject' section above to add subjects!")
            st.stop()
    
        subject = st.selectbox(
            "Select Subject to View", 
            subjects, 
            key="curr_view_subject"
        )
    
        if st.button("📖 View Curriculum", width='content'):
            with st.spinner("Loading curriculum..."):
                curriculum = db.get_curriculum(student_class, subject)
        
            if curriculum:
                st.markdown("### 📄 Curriculum Content")
            
                # Check if it's a pending curriculum
                if "pending" in curriculum.lower() or "contact your teacher" in curriculum.lower():
                    st.warning("⏳ Curriculum content is pending. Your teacher will add it soon!")
            
                st.text_area("", curriculum, height=400, disabled=True, key="curriculum_display")
            
                # Download options
                st.markdown("###")
                col_dl1, col_dl2, col_dl3 = st.columns([1, 1, 2])
            
                with col_dl1:
                    if st.button("⬇️ Download as PDF", width='stretch'):
                        from reportlab.lib.pagesizes import letter
                        from reportlab.pdfgen import canvas
                        from reportlab.lib.utils import simpleSplit
                    
                        buffer = BytesIO()
                        pdf = canvas.Canvas(buffer, pagesize=letter)
                    
                        # Title
                        pdf.setFont("Helvetica-Bold", 16)
                        pdf.drawString(100, 750, f"Curriculum: {subject} - Class {student_class}")
                    
                        # Subtitle
                        pdf.setFont("Helvetica", 10)
                        pdf.drawString(100, 730, f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
                    
                        # Content
                        pdf.setFont("Helvetica", 10)
                        y = 700
                    
                        for line in curriculum.split('\n'):
                            if y < 50:
                                pdf.showPage()
                                pdf.setFont("Helvetica", 10)
                                y = 750
                        
                            wrapped_lines = simpleSplit(line or " ", "Helvetica", 10, 400)
                            for wrapped_line in wrapped_lines:
                                pdf.drawString(100, y, wrapped_line)
                                y -= 15
                    
                        pdf.save()
                        buffer.seek(0)
                    
                        st.download_button(
                            label="📥 Download PDF",
                            data=buffer,
                            file_name=f"{subject.replace(' ', '_')}_Class_{student_class}_Curriculum.pdf",
                            mime="application/pdf",
                            width='stretch'
                        )
            
                with col_dl2:
                    # Download as TXT
                    txt_data = f"Curriculum: {subject} - Class {student_class}\n"
                    txt_data += f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
                    txt_data += "="*50 + "\n\n"
                    txt_data += curriculum
                
                    st.download_button(
                        label="📥 Download TXT",
                        data=txt_data,
                        file_name=f"{subject.replace(' ', '_')}_Class_{student_class}_Curriculum.txt",
                        mime="text/plain",
                        width='stretch'
                    )
            else:
                st.warning("⚠️ Curriculum not available for this subject yet.")
                st.info("💡 Your teacher hasn't added content for this subject. Please check back later!")
    
# ===============================================================
# TEACHER DASHBOARD
# ===============================================================
def teacher_dashboard():
    user = st.session_state.user
    st.title(f"Welcome, {user['full_name']} 👩‍🏫")

    with st.sidebar:
        st.subheader("👤 Teacher Info")
        st.write(f"**Email:** {user['email']}")
        st.write(f"**Class:** {user['class']}")
        st.markdown("---")
        if st.button("Logout"):
            st.session_state.logged_in = False
            st.session_state.user = None
            st.rerun()

    tab1, tab2, tab3, tab4 = st.tabs([
        "✏️ Manage Curriculum", 
        "📊 Class Analytics",
        "🎯 Create Quiz",
        "📝 Grade Quizzes"
    ])

    # Manage Curriculum
    with tab1:
        st.header("✏️ Add or Edit Curriculum")
        selected_class = st.selectbox("Select Class", [f"Grade {i}" for i in range(1, 13)])
        subject = st.text_input("Subject Name")
        curriculum_text = st.text_area("Curriculum Content", height=300)

        if st.button("💾 Save Curriculum"):
            if not selected_class or not subject or not curriculum_text.strip():
                st.warning("Please fill in all fields.")
            else:
                if db.save_curriculum(selected_class, subject, curriculum_text):
                    st.success("✅ Curriculum saved successfully!")
                else:
                    st.error("❌ Failed to save curriculum.")
        
        st.divider()
        st.subheader("📜 View Existing Curricula")
        view_class = st.selectbox("Select Class to View", [f"Grade {i}" for i in range(1, 13)], key="view_class")
        subjects = db.get_all_subjects_for_class(view_class)
        if subjects:
            view_subject = st.selectbox("Select Subject", subjects)
            curriculum = db.get_curriculum(view_class, view_subject)
            if curriculum:
                st.text_area("Curriculum Content", curriculum, height=300, disabled=True, key="view_curr")
        else:
            st.info("No curricula found for this class.")

    # Class Analytics
    with tab2:
        st.header("📊 Class Analytics Dashboard")
        
        analytics_class = st.selectbox("Select Class", [f"Grade {i}" for i in range(1, 13)], key="analytics_class")
        
        # Create two sub-tabs: Class Overview and Individual Student
        analytics_tab1, analytics_tab2 = st.tabs(["📈 Class Overview", "👤 Individual Student Progress"])
        
        # ==================== CLASS OVERVIEW TAB ====================
        with analytics_tab1:
            if st.button("📈 Generate Class Analytics", key="gen_class_analytics"):
                with st.spinner("Generating class analytics..."):
                    analytics = db.get_class_analytics(analytics_class)
                    
                    if analytics:
                        # Overview Metrics
                        col1, col2, col3, col4 = st.columns(4)
                        col1.metric("👥 Total Students", analytics['total_students'])
                        col2.metric("⭐ Avg Points", analytics['avg_points'])
                        col3.metric("🔥 Avg Streak", f"{analytics['avg_streak']} days")
                        col4.metric("📝 Avg Quiz Score", f"{analytics['avg_quiz_score']}%")
                        
                        st.divider()
                        
                        # Recent Activity
                        col5, col6 = st.columns(2)
                        col5.metric("📄 Papers (30 days)", analytics['recent_papers'])
                        col6.metric("🎯 Avg Quiz Performance", f"{analytics['avg_quiz_score']}%")
                        
                        # Top Performers
                        st.subheader("🏆 Top Performers")
                        if analytics['top_performers']:
                            top_df = pd.DataFrame(analytics['top_performers'])
                            st.dataframe(top_df, width='stretch')
                        else:
                            st.info("No student data available yet.")
                        
                        # Subject-wise Performance
                        st.subheader("📚 Subject-wise Performance")
                        if analytics['subject_performance']:
                            subject_df = pd.DataFrame(analytics['subject_performance'])
                            subject_df = subject_df.sort_values(by='avg_accuracy', ascending=False)

                            fig = px.bar(
                                subject_df,
                                x='subject',
                                y='avg_accuracy',
                                title='📊 Subject-Wise Average Accuracy',
                                labels={'avg_accuracy': 'Accuracy (%)', 'subject': 'Subject'},
                                color='avg_accuracy',
                                color_continuous_scale='Tealrose',
                                hover_data=['student_count', 'total_attempts', 'correct_attempts'],
                                text='avg_accuracy'
                            )

                            fig.update_traces(
                                texttemplate='%{text:.1f}%',
                                textposition='outside',
                                marker_line_color='white',
                                marker_line_width=1.5
                            )

                            fig.update_layout(
                                height=600,
                                plot_bgcolor='rgba(0,0,0,0)',
                                paper_bgcolor='rgba(0,0,0,0)',
                                xaxis_title='Subject',
                                yaxis_title='Accuracy (%)',
                                title_font=dict(size=22, family='Arial Black'),
                                font=dict(size=12),
                                yaxis=dict(range=[0, 100], tickfont=dict(size=12)),
                                margin=dict(l=40, r=40, t=70, b=50),
                                coloraxis_colorbar=dict(title='Accuracy %'),
                            )

                            st.plotly_chart(fig, width='stretch')

                            st.dataframe(
                                subject_df[['subject', 'student_count', 'total_attempts', 'correct_attempts', 'avg_accuracy']],
                                width='stretch',
                                hide_index=True
                            )
                        else:
                            st.info("No subject performance data available yet.")
                    else:
                        st.warning("No analytics data available for this class.")
        
        # ==================== INDIVIDUAL STUDENT TAB ====================
        with analytics_tab2:
            st.subheader("👤 Individual Student Progress")
            
            # Get all students in selected class
            students = db.get_students_in_class(analytics_class)
            
            if not students:
                st.info(f"No students found in {analytics_class}")
            else:
                # Create student selector
                student_names = [s['full_name'] for s in students]
                selected_student_idx = st.selectbox(
                    "Select Student",
                    range(len(student_names)),
                    format_func=lambda x: student_names[x],
                    key="individual_student_select"
                )
                
                selected_student = students[selected_student_idx]
                student_id = selected_student['id']
                
                st.markdown(f"### 📋 Progress Report: **{selected_student['full_name']}**")
                st.caption(f"Email: {selected_student['email']}")
                
                # Get comprehensive student data
                gamification = db.get_student_gamification(student_id)
                
                if gamification:
                    st.divider()
                    st.markdown("#### 🎮 Gamification Stats")
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("🎯 Level", gamification['level'])
                    col2.metric("⭐ Total Points", gamification['total_points'])
                    col3.metric("🔥 Current Streak", f"{gamification['current_streak']} days")
                    col4.metric("💪 Longest Streak", f"{gamification['longest_streak']} days")
                
                # ==================== PAPER REPORTS ====================
                st.divider()
                st.markdown("#### 📄 Paper Analysis Reports")
                
                paper_reports = db.get_student_paper_reports(student_id)
                
                if paper_reports:
                    paper_df = pd.DataFrame(paper_reports)
                    
                    # Display as styled dataframe
                    st.dataframe(
                        paper_df[['subject', 'date', 'obtained_marks', 'total_marks', 'percentage']],
                        width='stretch',
                        hide_index=True,
                        column_config={
                            "subject": "Subject",
                            "date": "Date",
                            "obtained_marks": "Marks Obtained",
                            "total_marks": "Total Marks",
                            "percentage": "Percentage"
                        }
                    )
                    
                    # Summary statistics
                    col_paper1, col_paper2, col_paper3 = st.columns(3)
                    col_paper1.metric("📝 Total Papers", len(paper_reports))
                    
                    # Calculate average if percentages are numeric
                    numeric_percentages = [float(p['percentage']) for p in paper_reports if p['percentage'] != 'N/A']
                    if numeric_percentages:
                        avg_percentage = round(sum(numeric_percentages) / len(numeric_percentages), 1)
                        col_paper2.metric("📊 Average Score", f"{avg_percentage}%")
                else:
                    st.info("No paper analyses submitted yet.")
                
                # ==================== QUIZ REPORTS ====================
                st.divider()
                st.markdown("#### 🎯 Quiz Performance")
                
                quiz_summary = db.get_student_quiz_summary(student_id)
                
                if quiz_summary:
                    quiz_df = pd.DataFrame(quiz_summary)
                    
                    st.dataframe(
                        quiz_df[['title', 'subject', 'date', 'obtained_marks', 'total_marks', 'percentage', 'time_taken']],
                        width='stretch',
                        hide_index=True,
                        column_config={
                            "title": "Quiz Title",
                            "subject": "Subject",
                            "date": "Date",
                            "obtained_marks": "Score",
                            "total_marks": "Total",
                            "percentage": "Percentage (%)",
                            "time_taken": "Time Taken"
                        }
                    )
                    
                    # Quiz statistics
                    col_quiz1, col_quiz2, col_quiz3 = st.columns(3)
                    col_quiz1.metric("🎯 Total Quizzes", len(quiz_summary))
                    
                    avg_quiz_percentage = round(sum([q['percentage'] for q in quiz_summary]) / len(quiz_summary), 1)
                    col_quiz2.metric("📊 Average Score", f"{avg_quiz_percentage}%")
                    
                    # Performance visualization
                    if len(quiz_summary) > 1:
                        fig_quiz = px.line(
                            quiz_df,
                            x='date',
                            y='percentage',
                            title='Quiz Performance Trend',
                            markers=True,
                            labels={'percentage': 'Score (%)', 'date': 'Date'}
                        )
                        fig_quiz.update_traces(line_color='#1f77b4', line_width=3)
                        fig_quiz.update_layout(height=400, yaxis=dict(range=[0, 100]))
                        st.plotly_chart(fig_quiz, width='stretch')
                else:
                    st.info("No quizzes attempted yet.")
                
                # ==================== WEAK TOPICS & PROGRESS ====================
                st.divider()
                st.markdown("#### 🎯 Weak Topics & Progress")
                
                weak_topics_progress = db.get_student_weak_topics_with_progress(student_id)
                
                if weak_topics_progress:
                    topics_df = pd.DataFrame(weak_topics_progress)
                    
                    st.dataframe(
                        topics_df,
                        width='stretch',
                        hide_index=True,
                        column_config={
                            "subject": "Subject",
                            "topic": "Weak Topic",
                            "attempts": "Attempts",
                            "correct_attempts": "Correct",
                            "accuracy": "Accuracy (%)",
                            "last_practiced": "Last Practiced",
                            "status": "Status"
                        }
                    )
                    
                    # Progress visualization
                    if len(topics_df) > 0:
                        fig_weak = px.bar(
                            topics_df,
                            x='topic',
                            y='accuracy',
                            color='status',
                            title='Progress in Weak Topics',
                            labels={'accuracy': 'Accuracy (%)', 'topic': 'Topic'},
                            color_discrete_map={
                                'Improving': '#28a745',
                                'Needs Practice': '#ffc107',
                                'Not Started': '#dc3545'
                            }
                        )
                        fig_weak.update_layout(height=400, yaxis=dict(range=[0, 100]))
                        st.plotly_chart(fig_weak, width='stretch')
                    
                    # Summary stats
                    col_weak1, col_weak2, col_weak3 = st.columns(3)
                    col_weak1.metric("📋 Total Weak Topics", len(weak_topics_progress))
                    
                    improving_count = len([t for t in weak_topics_progress if t['status'] == 'Improving'])
                    col_weak2.metric("✅ Improving", improving_count)
                    
                    not_started = len([t for t in weak_topics_progress if t['status'] == 'Not Started'])
                    col_weak3.metric("❌ Not Started", not_started)
                else:
                    st.info("No weak topics identified yet.")
                
                # ==================== EXPORT BUTTON ====================
                st.divider()
                if st.button("📥 Export Student Report (PDF)", key="export_individual"):
                    st.info("PDF export feature coming soon!")
    # Create Quiz
    with tab3:
        st.header("🎯 Create New Quiz")
        
        quiz_class = st.selectbox("Select Class", [f"Grade {i}" for i in range(1, 13)], key="quiz_class")
        
        subjects = db.get_all_subjects_for_class(quiz_class)
        if not subjects:
            st.warning("Please add curriculum for this class first.")
            st.stop()
        
        quiz_subject = st.selectbox("Select Subject", subjects, key="quiz_subject")
        quiz_title = st.text_input("Quiz Title")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            duration = st.number_input("Duration (minutes)", min_value=5, max_value=180, value=30)
        with col2:
            total_marks = st.number_input("Total Marks", min_value=1, max_value=100, value=20)
        with col3:
            deadline = st.date_input("Deadline")
        
        deadline_time = st.time_input("Deadline Time", value=None)
        
        st.subheader("Generate Questions")
        
        col_topic, col_num = st.columns(2)
        with col_topic:
            topic = st.text_input("Topic for Questions")
        with col_num:
            num_questions = st.number_input("Number of Questions", min_value=1, max_value=20, value=5)
        
        if st.button("🤖 Auto-Generate Questions"):
            if not topic:
                st.warning("Please enter a topic.")
            else:
                with st.spinner("Generating quiz questions..."):
                    questions = tutor.generate_quiz_questions(
                        quiz_subject, topic, quiz_class, num_questions
                    )
                    
                    if questions:
                        st.session_state['generated_questions'] = questions
                        st.success(f"✅ Generated {len(questions)} questions!")
                    else:
                        st.error("Failed to generate questions.")
                        # IMPORTANT: Remove the key if generation failed
                        if 'generated_questions' in st.session_state:
                            del st.session_state['generated_questions']

        # Display and edit generated questions
        if 'generated_questions' in st.session_state and st.session_state['generated_questions']:
            st.subheader("📝 Review & Edit Questions")
            
            edited_questions = []
            for i, q in enumerate(st.session_state['generated_questions']):
                with st.expander(f"Question {i+1}", expanded=True):
                    q_text = st.text_area(f"Question", value=q.get('question', ''), key=f"q_text_{i}")
                    q_type = st.selectbox("Type", ['mcq', 'short_answer', 'long_answer'], 
                                         index=['mcq', 'short_answer', 'long_answer'].index(q.get('type', 'short_answer')),
                                         key=f"q_type_{i}")
                    
                    if q_type == 'mcq':
                        st.write("Options:")
                        options = []
                        for j in range(4):
                            opt_value = q.get('options', ['', '', '', ''])[j] if j < len(q.get('options', [])) else ''
                            opt = st.text_input(f"Option {j+1}", value=opt_value, key=f"q_opt_{i}_{j}")
                            if opt:
                                options.append(opt)
                        q['options'] = options
                    
                    q_answer = st.text_input("Correct Answer", value=q.get('answer', ''), key=f"q_ans_{i}")
                    q_marks = st.number_input("Marks", min_value=1, max_value=20, value=q.get('marks', 2), key=f"q_marks_{i}")
                    
                    edited_questions.append({
                        'question': q_text,
                        'type': q_type,
                        'options': q.get('options') if q_type == 'mcq' else None,
                        'answer': q_answer,
                        'marks': q_marks
                    })
            
            if st.button("📤 Create Quiz", type="primary"):
                if not quiz_title:
                    st.error("Please enter a quiz title.")
                elif not edited_questions:
                    st.error("Please generate questions first.")
                else:
                    # Combine date and time for deadline
                    if deadline_time:
                        deadline_dt = datetime.combine(deadline, deadline_time)
                    else:
                        deadline_dt = datetime.combine(deadline, datetime.min.time())
                    
                    quiz_id = db.create_quiz(
                        teacher_id=user['id'],
                        class_name=quiz_class,
                        subject=quiz_subject,
                        title=quiz_title,
                        duration_minutes=duration,
                        total_marks=total_marks,
                        deadline=deadline_dt,
                        questions=edited_questions
                    )
                    
                    if quiz_id:
                        st.success("✅ Quiz created successfully! Students have been notified.")
                        st.session_state.pop('generated_questions')
                        st.rerun()
                    else:
                        st.error("Failed to create quiz.")

    # Grade Quizzes
    with tab4:
        st.header("📝 Grade Quiz Submissions")
        
        # Get all quizzes by this teacher
        grade_class = st.selectbox("Select Class", [f"Grade {i}" for i in range(1, 13)], key="grade_class")
        quizzes = db.get_quizzes_for_class(grade_class)
        
        teacher_quizzes = [q for q in quizzes if q['teacher_id'] == user['id']]
        
        if not teacher_quizzes:
            st.info("You haven't created any quizzes yet.")
            st.stop()
        
        quiz_titles = [f"{q['title']} - {q['subject']}" for q in teacher_quizzes]
        selected_quiz_idx = st.selectbox("Select Quiz", range(len(quiz_titles)), 
                                         format_func=lambda x: quiz_titles[x])
        
        selected_quiz = teacher_quizzes[selected_quiz_idx]
        
        # Get all attempts for this quiz
        st.subheader(f"Submissions for: {selected_quiz['title']}")
        
        # Get students in this class
        students = db.search_students(class_name=grade_class)
        
        for student in students:
            attempts = db.get_student_quiz_attempts(student['id'], selected_quiz['id'])
            
            if attempts:
                attempt = attempts[0]
                with st.expander(f"{student['full_name']} - {attempt['score'] or 'Not Graded'}/{attempt['total_marks']}"):
                    st.write(f"**Submitted:** {attempt['submitted_at']}")
                    st.write(f"**Time Taken:** {attempt['time_taken']} seconds")
                    
                    if attempt['score'] is not None:
                        st.success(f"✅ Graded: {attempt['score']}/{attempt['total_marks']}")
                        if attempt['feedback']:
                            st.write("**Feedback:**", attempt['feedback'])
                    else:
                        st.warning("⏳ Pending grading")
                        
                        # Manual grading interface
                        score = st.number_input(
                            "Score", 
                            min_value=0, 
                            max_value=int(attempt['total_marks']), 
                            key=f"score_{attempt['id']}"
                        )
                        feedback = st.text_area(
                            "Feedback", 
                            key=f"feedback_{attempt['id']}"
                        )
                        
                        if st.button(f"✅ Submit Grade", key=f"submit_grade_{attempt['id']}"):
                            if db.evaluate_quiz_attempt(attempt['id'], score, feedback):
                                st.success("✅ Grade submitted successfully!")
                                st.rerun()
                            else:
                                st.error("Failed to submit grade.")
            else:
                st.write(f"{student['full_name']}: ❌ Not attempted")


# ===============================================================
# PARENT DASHBOARD
# ===============================================================
def parent_dashboard():
    user = st.session_state.user
    st.title(f"Welcome, {user['full_name']} 👨‍👩‍👧‍👦")

    with st.sidebar:
        st.subheader("👤 Parent Info")
        st.write(f"**Email:** {user['email']}")
        st.markdown("---")
        if st.button("Logout"):
            st.session_state.logged_in = False
            st.session_state.user = None
            st.rerun()

    tab1, tab2 = st.tabs(["👨‍👩‍👧 Link Students", "📊 Monitor Progress"])

    # Link Students
    with tab1:
        st.header("👨‍👩‍👧 Link Your Children")
        
        st.subheader("Search for Student")
        
        search_method = st.radio("Search by:", ["Email", "Class"])
        
        if search_method == "Email":
            # --- Search by Email ---
            student_email = st.text_input("Enter student's email")
            search_triggered = st.button("🔍 Search")

            students = []
            if search_triggered and student_email:
                students = db.search_students(email=student_email)
                st.session_state['search_results'] = students
            elif 'search_results' in st.session_state:
                students = st.session_state['search_results']
            
            if students:
                st.write("### Matching Students:")
                for student in students:
                    col1, col2 = st.columns([3, 1])
                    col1.write(f"**{student['full_name']}** - {student['class']}")
                    with col2:
                        if st.button(f"Link {student['id']}", key=f"link_{student['id']}"):
                            st.write(f"Linking parent={user['id']} to student={student['id']}")
                            if db.link_parent_student(user['id'], student['id']):
                                st.success(f"✅ Linked to {student['full_name']}!")
                                del st.session_state['search_results']
                                st.rerun()
                            else:
                                st.error("❌ Failed to link student.")
        # else:
        #     st.info("No student found yet. Try searching by email.")

        else:
            student_class = st.selectbox("Select Class", [f"Grade {i}" for i in range(1, 13)])
            if st.button("🔍 Search"):
                students = db.search_students(class_name=student_class)
                
                if students:
                    for student in students:
                        col1, col2 = st.columns([3, 1])
                        col1.write(f"**{student['full_name']}** ({student['email']})")
                        with col2:
                            if st.button("Link", key=f"link_{student['id']}"):
                                if db.link_parent_student(user['id'], student['id']):
                                    st.success(f"✅ Linked to {student['full_name']}!")
                                    st.rerun()
                                else:
                                    st.error("Failed to link student.")
                else:
                    st.info("No students found in this class.")
        
        st.divider()
        st.subheader("📋 Linked Students")
        linked_students = db.get_parent_students(user['id'])
        
        if linked_students:
            for student in linked_students:
                st.write(f"✅ {student['full_name']} - {student['class']}")
        else:
            st.info("No linked students yet.")

    # Monitor Progress
    with tab2:
        st.header("📊 Monitor Student Progress")
        
        linked_students = db.get_parent_students(user['id'])
        
        if not linked_students:
            st.info("Please link students first to monitor their progress.")
            st.stop()
        
        student_names = [s['full_name'] for s in linked_students]
        selected_student_idx = st.selectbox("Select Student", range(len(student_names)),
                                           format_func=lambda x: student_names[x])
        
        selected_student = linked_students[selected_student_idx]
        student_id = selected_student['id']
        
        # Get comprehensive overview
        overview = db.get_student_overview_for_parent(student_id)
        
        if overview:
            st.subheader(f"📈 {overview['full_name']}'s Progress")
            
            # Overview metrics
            col1, col2, col3, col4 = st.columns(4)
            
            gamification = overview.get('gamification')
            if gamification:
                col1.metric("🎯 Level", gamification['level'])
                col2.metric("⭐ Points", gamification['total_points'])
                col3.metric("🔥 Streak", f"{gamification['current_streak']} days")
            
            col4.metric("📊 Avg Score", f"{overview.get('average_score', 0)}%")
            
            st.divider()
            
            # Recent Activity
            col5, col6 = st.columns(2)
            col5.metric("📄 Papers (30 days)", overview.get('recent_papers', 0))
            col6.metric("🎯 Quizzes (30 days)", overview.get('recent_quizzes', 0))
            
            # Performance Trend
            st.subheader("📈 Performance Trend")
            trend_data = db.get_student_performance_trend(student_id, days=30)
            
            if trend_data:
                df = pd.DataFrame(trend_data)

                # Create the base line figure
                fig = go.Figure()

                # Add smooth line with gradient and glow effect
                fig.add_trace(go.Scatter(
                    x=df['date'],
                    y=df['avg_score'],
                    mode='lines+markers',
                    line=dict(color='limegreen', width=4, shape='spline'),
                    marker=dict(size=10, color='green', line=dict(color='white', width=2)),
                    fill='tozeroy',  # fill area under curve
                    fillcolor='rgba(50, 205, 50, 0.2)',  # soft green fill
                    hovertemplate='<b>Date:</b> %{x}<br><b>Average Score:</b> %{y:.1f}%',
                    name='Performance Trend'
                ))

                # Set up the layout for beauty + interactivity
                fig.update_layout(
                    title=dict(text='📈 Quiz Performance Over Time', x=0.5, font=dict(size=24, color='#333')),
                    xaxis_title='Date',
                    yaxis_title='Average Score (%)',
                    yaxis=dict(range=[0, 110], gridcolor='rgba(200,200,200,0.3)'),
                    xaxis=dict(showgrid=True, gridcolor='rgba(200,200,200,0.2)'),
                    plot_bgcolor='rgba(240,248,255,0.8)',  
                    paper_bgcolor='white',
                    hovermode='x unified',
                    font=dict(family='Arial', size=14, color='#333'),
                    margin=dict(l=40, r=30, t=60, b=40),
                )

                # Add subtle animation
                fig.update_traces(
                    line_shape='spline',
                    mode='lines+markers'
                )
            
                st.plotly_chart(fig, width='stretch')

            else:
                st.info("Complete quizzes to see your performance trend!")

            
            # Subject-wise Progress
            st.subheader("📚 Subject-wise Progress")
            progress = db.get_student_progress(student_id)
            
            if progress:
                progress_data = []
                for p in progress:
                    accuracy = round((p['correct_attempts'] / p['attempts']) * 100, 1) if p['attempts'] else 0
                    # Wrap topic names for better readability
                    wrapped_topic = "<br>".join(textwrap.wrap(p['topic'], width=12))  # breaks lines after 12 characters
                    progress_data.append({
                        'Subject': p['subject'],
                        'Topic': wrapped_topic,
                        'Accuracy': accuracy,
                        'Attempts': p['attempts']
                    })

                progress_df = pd.DataFrame(progress_data)
                st.dataframe(progress_df, width='stretch')

                if len(progress_df) > 0:
                    progress_df['Short Topic'] = progress_df['Topic'].apply(lambda x: x[:45] + '...' if len(x) > 45 else x)
                    fig = px.bar(
                        progress_df,
                        x='Short Topic',
                        y='Accuracy',
                        color='Subject',
                        text='Accuracy',
                        title='📊 Topic-wise Accuracy',
                        color_discrete_sequence=px.colors.qualitative.Set2,
                        labels={'Accuracy': 'Accuracy (%)', 'Topic': 'Topic'},
                        height=480
                    )

                    fig.update_traces(
                        width=0.4,
                        texttemplate='%{text:.1f}%',
                        textposition='outside',
                        marker_line=dict(color='rgba(255,255,255,0.9)', width=1.5),
                        opacity=0.9,
                        hovertemplate='<b>Topic:</b> %{x}<br><b>Subject:</b> %{customdata[0]}<br><b>Accuracy:</b> %{y:.1f}%',
                        customdata=progress_df[['Subject']]
                    )

                    fig.update_layout(
                        bargap=0.35,
                        bargroupgap=0.15,
                        plot_bgcolor='rgba(240,248,255,0.8)',
                        paper_bgcolor='white',
                        yaxis=dict(title='Accuracy (%)', range=[0, 200]),
                        title_font=dict(size=22, color='#333', family='Arial'),
                        font=dict(size=12, color='#333'),
                        hovermode='x unified',
                        margin=dict(l=40, r=20, t=70, b=60),
                        legend=dict(
                            orientation='h',
                            yanchor='bottom',
                            y=1.02,
                            xanchor='center',
                            x=0.5,
                            title=''
                        )
                    )

                    # Disable x-axis angle since we now wrap text
                    fig.update_xaxes(tickangle=0)

                    st.plotly_chart(
                        fig,
                        width='stretch',
                        config={"displayModeBar": False, "responsive": True}
                    )
                else:
                    st.info("No practice data available yet.")
            # Recent Quiz Results
            st.subheader("🎯 Recent Quiz Results")
            quiz_attempts = db.get_student_quiz_attempts(student_id)
            
            if quiz_attempts:
                quiz_data = []
                for attempt in quiz_attempts[:5]:  # Show last 5
                    if attempt['score'] is not None:
                        percentage = round((attempt['score'] / attempt['total_marks']) * 100, 1)
                        quiz_data.append({
                            'Quiz': attempt['title'],
                            'Subject': attempt['subject'],
                            'Score': f"{attempt['score']}/{attempt['total_marks']}",
                            'Percentage': f"{percentage}%",
                            'Date': attempt['submitted_at'].strftime('%Y-%m-%d')
                        })
                
                if quiz_data:
                    quiz_df = pd.DataFrame(quiz_data)
                    st.dataframe(quiz_df, width='stretch')
                else:
                    st.info("No graded quizzes yet.")
            else:
                st.info("No quiz attempts yet.")
            
            # Download report button
            st.divider()
            if st.button("📥 Download Progress Report (PDF)"):
                with st.spinner("Generating report..."):
                    pdf_buffer = generate_progress_pdf(
                        selected_student, 
                        progress, 
                        gamification or {}
                    )
                    
                    st.download_button(
                        label="📄 Download PDF Report",
                        data=pdf_buffer,
                        file_name=f"progress_report_{selected_student['full_name'].replace(' ', '_')}.pdf",
                        mime="application/pdf"
                    )


# ===============================================================
# MAIN LOGIC
# ===============================================================
def main():
    if not st.session_state.logged_in:
        if st.session_state.show_signup:
            signup_page()
        else:
            login_page()
    else:
        role = st.session_state.user['role']
        if role == 'student':
            student_dashboard()
        elif role == 'teacher':
            teacher_dashboard()
        elif role == 'parent':
            parent_dashboard()
        else:
            st.error("Unknown role type.")

if __name__ == "__main__":
    main()