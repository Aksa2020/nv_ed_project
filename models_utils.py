import streamlit as st
from groq import Groq
from io import BytesIO
import requests
import PyPDF2
import base64
import json
import re
import os
from config import GROQ_API_KEY

# ============================================================
# CONFIGURATION
# ============================================================
GROQ_API_KEY = st.secrets.get("GROQ_API_KEY", "")
SCOUT_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
ANALYSIS_MODEL = "openai/gpt-oss-120b"
# GROQ_API_KEY = os.getenv("GROQ_API_KEY") or GROQ_API_KEY
# SCOUT_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
# ANALYSIS_MODEL = "openai/gpt-oss-120b"

client = Groq(api_key=GROQ_API_KEY)


# ============================================================
# HELPER FUNCTION: Unified call for both models
# ============================================================
def groq_chat_completion(model, messages, temperature=0.4, max_tokens=1000, stream=False):
    """Unified helper for Groq model calls."""
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_completion_tokens=max_tokens,
            top_p=1,
            stream=stream,
        )

        if stream:
            full_response = ""
            placeholder = st.empty()
            for chunk in completion:
                delta = chunk.choices[0].delta.content or ""
                full_response += delta
                placeholder.markdown(full_response)
            return full_response
        else:
            return completion.choices[0].message.content

    except Exception as e:
        st.error(f"❌ Groq API Error: {str(e)}")
        return None


# ============================================================
# AGENT 1: ASSESSMENT AGENT
# ============================================================
class AssessmentAgent:
    """Handles OCR (text extraction) and exam paper analysis."""

    # -------------------- 1️⃣ Extract text from PDF --------------------
    def extract_text_from_pdf(self, pdf_file):
        """Extract text from PDF file"""
        try:
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            text = ""
            
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
            
            return text.strip() if text else None
        
        except Exception as e:
            st.error(f"❌ Error extracting text from PDF: {str(e)}")
            return None

    # -------------------- 2️⃣ Extract text from image --------------------
    def extract_text_from_paper(self, image_file):
        """Extract text from uploaded exam paper using vision model."""
        try:
            image_bytes = image_file.read()
            image_file.seek(0)
            img_base64 = base64.b64encode(image_bytes).decode("utf-8")

            extraction_prompt = """Extract all visible text from this student's handwritten exam paper.
Preserve question and answer structure clearly.
Format:
Q1: [Question text] [Marks]
Student Answer: [Answer text]
Q2: [Question text] [Marks]
Student Answer: [Answer text]
Do NOT add commentary or corrections."""

            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": extraction_prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{img_base64}"
                            },
                        },
                    ],
                }
            ]

            with st.spinner("🔍 Extracting text from exam paper..."):
                extracted_text = groq_chat_completion(SCOUT_MODEL, messages, max_tokens=2000, temperature=0.3)

            return extracted_text.strip() if extracted_text else None

        except Exception as e:
            st.error(f"❌ Error extracting text: {str(e)}")
            return None

    # -------------------- 3️⃣ Analyze paper --------------------
    def analyze_student_paper(self, extracted_text, subject, curriculum, student_class):
        """Analyze student's exam paper and provide structured feedback."""
        try:
            analysis_prompt = f"""
You are an educational assessment assistant for {student_class}.

STUDENT INFO:
- Class: {student_class}
- Subject: {subject}
- Curriculum Topics: {curriculum}

STUDENT ANSWERS:
{extracted_text}

TASK:
Provide a detailed analysis in this format:
1. OVERALL PERFORMANCE SUMMARY INCLUDING OBTAINED MARKS
2. QUESTION-BY-QUESTION ANALYSIS
3. STRENGTHS IDENTIFIED
4. AREAS FOR IMPROVEMENT
   - IMPORTANT: List ONLY the topic names from the curriculum above that need improvement
   - Only add one main topic name from curriculum related to one improvement 
   - Use simple bullet points with just the topic name
   - NO explanations, NO descriptions, NO additional text
   - Format: Just write the topic name from the curriculum
   - Example:
     - For addittion there should be one exact match topic name 
        - Adding 2-digit numbers without regrouping
                OR
        - Word problem with addition or subtraction of whole numbers 
5. PERSONALIZED RECOMMENDATIONS
6. ENCOURAGEMENT & NEXT STEPS
"""

            messages = [{"role": "user", "content": [{"type": "text", "text": analysis_prompt}]}]

            with st.spinner("🧠 Analyzing student's answers..."):
                analysis = groq_chat_completion(ANALYSIS_MODEL, messages, max_tokens=1500, temperature=0.7)

            return analysis

        except Exception as e:
            st.error(f"❌ Error analyzing paper: {str(e)}")
            return None


# ============================================================
# AGENT 2: TUTOR AGENT
# ============================================================
class TutorAgent:
    """Handles personalized learning, practice questions, and feedback."""

    # -------------------- 1️⃣ Learning Content --------------------
    def generate_learning_content(self, weak_area, subject, student_class="", curriculum=""):
        """Generate simple, engaging learning content."""
        try:
            curriculum_context = ""
            if curriculum:
                curriculum_context = f"""
CURRICULUM REFERENCE:
{curriculum}

Use the curriculum above as a guide to ensure the learning content aligns with what students are expected to learn.
"""
            prompt = f"""
You are a friendly teacher for {student_class or 'students'}.

TOPIC: {weak_area}
SUBJECT: {subject}

{curriculum_context}

Create fun, simple learning content including:
1. Brief explanation (age-appropriate)
2. Real-life example
3. Memory trick or tip
4. Motivational line

Use emojis and markdown formatting to keep it engaging.
"""
            messages = [{"role": "user", "content": [{"type": "text", "text": prompt}]}]

            with st.spinner(f"📚 Generating learning content for {weak_area}..."):
                content = groq_chat_completion(ANALYSIS_MODEL, messages, max_tokens=600, temperature=0.7)
            return content

        except Exception as e:
            st.error(f"❌ Error generating learning content: {str(e)}")
            return "Unable to generate learning content."

    # -------------------- 🆕 1.5️⃣ Interactive Chat --------------------
    def chat_about_topic(self, topic, subject, learning_content, chat_history, user_message, student_class=""):
        """
        Interactive chat about a specific learning topic
        
        Args:
            topic: The topic being discussed
            subject: The subject
            learning_content: The generated learning material
            chat_history: List of previous messages [{"role": "student/tutor", "content": "..."}]
            user_message: Current user question
            student_class: Student's class/grade level
        
        Returns:
            AI response (streaming)
        """
        try:
            # Build conversation context
            context = f"""You are a friendly, patient, and encouraging AI tutor helping a {student_class or 'school'} student understand a topic.

TOPIC: {topic}
SUBJECT: {subject}

LEARNING MATERIAL PROVIDED TO STUDENT:
---
{learning_content}
---

YOUR ROLE:
- Answer questions about this topic clearly and simply
- Use age-appropriate language for {student_class or 'school students'}
- Provide examples and analogies that relate to their daily life
- Be encouraging and supportive - celebrate their curiosity!
- If the student is confused, explain the concept in a different way
- Break down complex ideas into smaller, digestible parts
- Use emojis to keep responses friendly and engaging
- Keep responses concise (2-4 paragraphs maximum)
- If they ask something unrelated to the topic, gently guide them back

CONVERSATION SO FAR:
"""
            
            # Add chat history (last 10 messages to keep context manageable)
            recent_history = chat_history[-10:] if len(chat_history) > 10 else chat_history
            
            for msg in recent_history:
                role_display = "Student" if msg['role'] == "student" else "Tutor"
                context += f"\n{role_display}: {msg['content']}"
            
            # Add current question
            context += f"\n\nStudent: {user_message}\n\nTutor:"
            
            messages = [
                {"role": "user", "content": [{"type": "text", "text": context}]}
            ]
            
            # Use streaming for better UX (no spinner needed as it shows progressive response)
            response = groq_chat_completion(
                ANALYSIS_MODEL, 
                messages, 
                max_tokens=800, 
                temperature=0.7,
                stream=True  # Enable streaming
            )
            
            return response if response else "I'm having trouble responding right now. Could you please rephrase your question? 🤔"
            
        except Exception as e:
            print(f"❌ Chat error: {str(e)}")
            import traceback
            traceback.print_exc()
            return "I apologize, but I'm having technical difficulties. Please try asking your question again! 😊"

    # -------------------- 2️⃣ Practice Questions --------------------
    def generate_practice_questions(self, weak_area, subject, student_class="", num_questions=3):
        """Generate structured practice questions."""
        try:
            prompt = f"""
Create {num_questions} practice questions for {student_class or 'school'} students.
TOPIC: {weak_area}
SUBJECT: {subject}

Each question should include:
- Question
- Correct Answer
- Short Explanation

Format:
Q1: [Question]
Answer: [Answer text]
Explanation: [Short explanation]
"""
            messages = [{"role": "user", "content": [{"type": "text", "text": prompt}]}]

            with st.spinner(f"🧩 Generating practice questions for {weak_area}..."):
                response_text = groq_chat_completion(ANALYSIS_MODEL, messages, max_tokens=700, temperature=0.8)

            return self._parse_practice_questions(response_text)

        except Exception as e:
            st.error(f"❌ Error generating practice questions: {str(e)}")
            return []

    def _parse_practice_questions(self, response_text):
        questions = []
        if not response_text:
            return questions
        q_pattern = r'Q\d+:\s*(.+?)(?=Answer:|$)'
        a_pattern = r'Answer:\s*(.+?)(?=Explanation:|Q\d+:|$)'
        e_pattern = r'Explanation:\s*(.+?)(?=Q\d+:|$)'
        q_matches = re.finditer(q_pattern, response_text, re.DOTALL)
        for q_match in q_matches:
            question_text = q_match.group(1).strip()
            answer_match = re.search(a_pattern, response_text[q_match.end():], re.DOTALL)
            explanation_match = re.search(e_pattern, response_text[q_match.end():], re.DOTALL)
            questions.append({
                "question": question_text,
                "correct_answer": answer_match.group(1).strip() if answer_match else "",
                "explanation": explanation_match.group(1).strip() if explanation_match else "",
            })
        return questions

    # -------------------- 3️⃣ Evaluate Answer --------------------
    def evaluate_answer(self, subject, question, answer, correct_answer, explanation=""):
        """Evaluate student's answer with kind feedback."""
        try:
            prompt = f"""
You are an encouraging teacher evaluating a student's response.

QUESTION: {question}
CORRECT ANSWER: {correct_answer}
EXPLANATION: {explanation}
STUDENT ANSWER: {answer}

Give feedback in this EXACT format:
1. First line MUST be one of: CORRECT / PARTIALLY_CORRECT / INCORRECT
2. Then provide kind, detailed feedback
3. End with encouragement

Example:
INCORRECT
You're close! The long hand on the 6 means "30 minutes past"...
Keep practicing - you're making great progress!
"""
            messages = [{"role": "user", "content": [{"type": "text", "text": prompt}]}]

            with st.spinner("✅ Evaluating your answer..."):
                feedback = groq_chat_completion(ANALYSIS_MODEL, messages, max_tokens=400, temperature=0.5)

            # ✅ IMPROVED DETECTION - Check the START of feedback for explicit markers
            feedback_lower = feedback.lower().strip()
            
            # Check for explicit markers at the beginning
            if feedback_lower.startswith("correct"):
                is_correct = True
            elif feedback_lower.startswith("partially"):
                is_correct = False  # Treat partial as incorrect for point calculation
            elif feedback_lower.startswith("incorrect") or feedback_lower.startswith("wrong"):
                is_correct = False
            else:
                # Fallback: More sophisticated word boundary detection
                import re
                
                # Negative indicators (check first to avoid false positives)
                if re.search(r'\b(incorrect|wrong|not correct|not right)\b', feedback_lower):
                    is_correct = False
                # Positive indicators (only if no negative found)
                elif re.search(r'\b(^correct|right|well done|excellent|perfect|great job)\b', feedback_lower):
                    is_correct = True
                else:
                    # If unclear, default to incorrect
                    is_correct = False

            return {"feedback": feedback, "is_correct": is_correct}

        except Exception as e:
            st.error(f"❌ Error evaluating answer: {str(e)}")
            return {"feedback": "Unable to evaluate answer.", "is_correct": False}

        
    # -------------------- 4️⃣ Generate Quiz --------------------
    def generate_quiz_questions(self, subject, topic, student_class, num_questions=5):
        """Generate quiz questions for a given topic"""
        try:
            prompt = f"""
Create {num_questions} quiz questions for {student_class} students.
SUBJECT: {subject}
TOPIC: {topic}

Generate a mix of:
- 40% MCQ questions (with 4 options each)
- 30% Short answer questions (1-2 sentences)
- 30% Long answer questions (paragraph)

For each question, provide in this EXACT format:

Q1:
Type: mcq
Question: [Your question here]
Options: ["Option A", "Option B", "Option C", "Option D"]
Answer: [Correct option]
Marks: [1-5]

Q2:
Type: short_answer
Question: [Your question here]
Answer: [Expected answer]
Marks: [1-3]

Q3:
Type: long_answer
Question: [Your question here]
Answer: [Expected answer key points]
Marks: [3-5]

Continue this format for all {num_questions} questions.
"""
        
            messages = [{"role": "user", "content": [{"type": "text", "text": prompt}]}]
        
            print(f"🔍 Generating {num_questions} questions for {topic}...")
            response = groq_chat_completion(ANALYSIS_MODEL, messages, max_tokens=1500, temperature=0.7)
        
            if not response:
                print("❌ No response from AI model")
                return []
        
            print(f"✅ Raw response received: {len(response)} characters")
        
            # Parse the response
            questions = self._parse_quiz_questions_structured(response)
        
            if not questions:
                print("⚠️ Failed to parse, trying fallback parser...")
                questions = self._parse_quiz_questions(response)
        
            print(f"📊 Parsed {len(questions)} questions successfully")
            return questions
    
        except Exception as e:
            print(f"❌ Error generating quiz: {str(e)}")
            import traceback
            traceback.print_exc()
            return []

    
    def _parse_quiz_questions_structured(self, response_text):
        """Enhanced parser for structured quiz questions"""
        questions = []
    
        if not response_text:
            return questions
    
        # Split by question markers
        question_blocks = re.split(r'\n(?=Q\d+:)', response_text)
    
        for block in question_blocks:
            if not block.strip():
                continue
        
            try:    
                q_dict = {}
            
                # Extract type
                type_match = re.search(r'Type:\s*(mcq|short_answer|long_answer)', block, re.IGNORECASE)
                q_dict['type'] = type_match.group(1).lower() if type_match else 'short_answer'
            
                # Extract question
                q_match = re.search(r'Question:\s*(.+?)(?=\n(?:Options|Answer|Marks|$))', block, re.DOTALL)
                if not q_match:
                    continue
                q_dict['question'] = q_match.group(1).strip()
            
                # Extract options for MCQ
                if q_dict['type'] == 'mcq':
                    options_match = re.search(r'Options:\s*\[(.+?)\]', block, re.DOTALL)
                    if options_match:
                        options_str = options_match.group(1)
                        # Parse options
                        q_dict['options'] = [opt.strip(' "\'') for opt in re.findall(r'"([^"]+)"|\'([^\']+)\'', options_str)]
                        if len(q_dict['options']) < 4:
                            # Fallback: split by comma
                            q_dict['options'] = [opt.strip(' "\'') for opt in options_str.split(',')]
                    else:
                        q_dict['options'] = []
            
                # Extract answer
                ans_match = re.search(r'Answer:\s*(.+?)(?=\nMarks|$)', block, re.DOTALL)
                q_dict['answer'] = ans_match.group(1).strip() if ans_match else ""
            
                # Extract marks
                marks_match = re.search(r'Marks:\s*(\d+)', block)
                q_dict['marks'] = int(marks_match.group(1)) if marks_match else 2
            
                questions.append(q_dict)
        
            except Exception as e:
                print(f"⚠️ Error parsing question block: {e}")
                continue
    
        return questions
    
    # -------------------- 5️⃣ Auto-evaluate Quiz --------------------
    def auto_evaluate_quiz(self, questions, student_answers):
        """Automatically evaluate quiz answers"""
        try:
            total_score = 0
            feedback_list = []
            
            for i, q in enumerate(questions):
                student_ans = student_answers.get(str(i), "")
                correct_ans = q.get('correct_answer', q.get('answer', ''))
                marks = q.get('marks', 1)
                
                # Simple evaluation
                if q['type'] == 'mcq':
                    if student_ans.lower() == correct_ans.lower():
                        total_score += marks
                        feedback_list.append(f"Q{i+1}: Correct! ({marks}/{marks})")
                    else:
                        feedback_list.append(f"Q{i+1}: Incorrect. Correct answer: {correct_ans} (0/{marks})")
                else:
                    # Use AI to evaluate
                    result = self.evaluate_answer("", q['question'], student_ans, correct_ans)
                    if result['is_correct']:
                        total_score += marks
                        feedback_list.append(f"Q{i+1}: {result['feedback']} ({marks}/{marks})")
                    else:
                        partial = marks // 2
                        total_score += partial
                        feedback_list.append(f"Q{i+1}: {result['feedback']} ({partial}/{marks})")
            
            return {
                'score': total_score,
                'feedback': '\n'.join(feedback_list)
            }
        
        except Exception as e:
            st.error(f"❌ Error evaluating quiz: {str(e)}")
            return {'score': 0, 'feedback': 'Evaluation failed'}