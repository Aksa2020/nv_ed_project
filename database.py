from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
from config import DB_CONFIG
import streamlit as st
import psycopg2
import json
import re

class Database:
    def __init__(self):
        # Read database configuration from Streamlit secrets
        self.config = {
            "host": st.secrets.get("DB_HOST"),
            "port": st.secrets.get("DB_PORT"),
            "database": st.secrets.get("DB_NAME"),
            "user": st.secrets.get("DB_USER"),
            "password": st.secrets.get("DB_PASSWORD")
        }
        
        # Validate database configuration
        if not all([self.config["host"], self.config["database"], 
                   self.config["user"], self.config["password"]]):
            st.error("❌ Database configuration incomplete. Please check your secrets.toml file.")
            st.stop()

    def connect(self):
        """Create database connection"""
        try:
            conn = psycopg2.connect(**self.config)
            return conn
        except Exception as e:
            print(f"Database connection error: {e}")
            st.error(f"❌ Database connection failed: {str(e)}")
            return None


    # ==================== USER MANAGEMENT ====================
    
    def create_user(self, user_data):
        """Create a new user account"""
        conn = None
        cursor = None
        try:
            conn = self.connect()
            cursor = conn.cursor()
        
            # Teachers don't need class or parent_id
            if user_data['role'] == 'teacher':
                query = """
                    INSERT INTO user_details (full_name, email, password_hash, role)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                """
                cursor.execute(query, (
                    user_data['full_name'],
                    user_data['email'],
                    user_data['password_hash'],
                    user_data['role']
                ))
            else:
                # Students need class and possibly parent_id
                query = """
                    INSERT INTO user_details (full_name, email, password_hash, role, class, parent_id)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                """
                cursor.execute(query, (
                    user_data['full_name'],
                    user_data['email'],
                    user_data['password_hash'],
                    user_data['role'],
                    user_data.get('class'),
                    user_data.get('parent_id')
                ))
        
            result = cursor.fetchone()
        
            if result is None:
                raise Exception("Failed to create user - no ID returned")
        
            user_id = result[0]
        
            # Initialize gamification only for students
            if user_data['role'] == 'student':
                cursor.execute("""
                INSERT INTO student_gamification (student_id)
                VALUES (%s)
                ON CONFLICT (student_id) DO NOTHING
            """, (user_id,))        
            conn.commit()
        
            return True
        
        except Exception as e:
            if conn:
                conn.rollback()
            print(f"Error creating user: {e}")
            import traceback
            traceback.print_exc()
            return False
        
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
    
    def get_user_by_email(self, email):
        """Get user details by email"""
        try:
            conn = self.connect()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            query = "SELECT * FROM user_details WHERE email = %s"
            cursor.execute(query, (email,))
            
            user = cursor.fetchone()
            
            cursor.close()
            conn.close()
            
            return dict(user) if user else None
            
        except Exception as e:
            print(f"Error fetching user: {e}")
            return None
    
    # ==================== CURRICULUM MANAGEMENT ====================
    
    def save_curriculum(self, class_name, subject, curriculum_text):
        """Save or update curriculum for a class and subject"""
        try:
            conn = self.connect()
            cursor = conn.cursor()
            
            query = """
                INSERT INTO curriculum (class, subject, curriculum, updated_at)
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (class, subject) 
                DO UPDATE SET curriculum = EXCLUDED.curriculum, updated_at = CURRENT_TIMESTAMP
            """
            
            cursor.execute(query, (class_name, subject, curriculum_text))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            return True
            
        except Exception as e:
            print(f"Error saving curriculum: {e}")
            return False
    
    def get_curriculum(self, class_name, subject):
        """Get curriculum for a specific class and subject"""
        try:
            conn = self.connect()
            cursor = conn.cursor()
            
            query = "SELECT curriculum FROM curriculum WHERE class = %s AND subject = %s"
            cursor.execute(query, (class_name, subject))
            
            result = cursor.fetchone()
            
            cursor.close()
            conn.close()
            
            return result[0] if result else None
            
        except Exception as e:
            print(f"Error fetching curriculum: {e}")
            return None
    
    def get_all_subjects_for_class(self, class_name):
        """Get all subjects that have curriculum for a specific class"""
        try:
            conn = self.connect()
            cursor = conn.cursor()
            
            query = """
                SELECT DISTINCT subject 
                FROM curriculum 
                WHERE class = %s
                ORDER BY subject
            """
            
            cursor.execute(query, (class_name,))
            results = cursor.fetchall()
            
            subjects = [row[0] for row in results]
            
            cursor.close()
            conn.close()
            
            return subjects
            
        except Exception as e:
            print(f"Error fetching subjects: {e}")
            return []
    
    def get_all_curricula(self):
        """Get all curricula for teacher dashboard"""
        try:
            conn = self.connect()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            query = "SELECT * FROM curriculum ORDER BY class, subject"
            cursor.execute(query)
            results = cursor.fetchall()
            
            cursor.close()
            conn.close()
            
            return [dict(row) for row in results]
            
        except Exception as e:
            print(f"Error fetching curricula: {e}")
            return []
    
    # ==================== PAPER ANALYSIS ====================
    
    def save_paper_analysis(self, class_name, student_id, student_name, subject, student_paper, analysis):
        """Save paper analysis to database"""
        try:
            conn = self.connect()
            cursor = conn.cursor()
            
            query = """
                INSERT INTO paper_analysis (class, student_id, student_name, subject, student_paper, analysis_by_model)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """
            
            cursor.execute(query, (class_name, student_id, student_name, subject, student_paper, analysis))
            
            analysis_id = cursor.fetchone()[0]
            
            # Award points for paper submission
            self.add_points(student_id, 10, "Paper Analysis Completed")
            
            conn.commit()
            cursor.close()
            conn.close()
            
            return analysis_id
            
        except Exception as e:
            print(f"Error saving paper analysis: {e}")
            return None
    
    def get_student_analysis_history(self, student_id):
        """Get all paper analyses for a student"""
        try:
            conn = self.connect()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            query = """
                SELECT * FROM paper_analysis 
                WHERE student_id = %s 
                ORDER BY created_at DESC
            """
            
            cursor.execute(query, (student_id,))
            results = cursor.fetchall()
            
            cursor.close()
            conn.close()
            
            return [dict(row) for row in results]
            
        except Exception as e:
            print(f"Error fetching analysis history: {e}")
            return []
    
    # ==================== WEAK TOPICS MANAGEMENT ====================
    
    def get_weak_topics_history(self, student_id):
        """Extract weak areas from past paper analyses for a student"""
        try:
            conn = self.connect()
            cursor = conn.cursor()
            
            query = """
                SELECT id, subject, analysis_by_model, created_at
                FROM paper_analysis
                WHERE student_id = %s
                ORDER BY created_at DESC
            """
            
            cursor.execute(query, (student_id,))
            results = cursor.fetchall()
            
            weak_topics = []
            
            for row in results:
                analysis_id, subject, analysis_text, created_at = row
                
                if analysis_text:
                    weak_areas = self._extract_weak_areas_from_analysis(analysis_text)
                    
                    for weak_area in weak_areas:
                        weak_topics.append({
                            'analysis_id': analysis_id,
                            'subject': subject,
                            'weak_area': weak_area,
                            'created_at': created_at
                        })
            
            cursor.close()
            conn.close()
            
            return weak_topics
            
        except Exception as e:
            print(f"Error fetching weak topics: {e}")
            return []
    
    def _extract_weak_areas_from_analysis(self, analysis_text):
        """
        Enhanced helper method to extract weak areas from analysis text.
        Now optimized for curriculum-based topic names without explanations.
        """
        weak_areas = []
        
        # Find the "AREAS FOR IMPROVEMENT" section
        match = re.search(
            r"AREAS?\s+FOR\s+IMPROVEMENT[:\-–]*\s*([\s\S]*?)(?=\d+\.\s+[A-Z]|\Z)",
            analysis_text,
            re.IGNORECASE
        )
        
        if not match:
            return weak_areas
        
        weak_section = match.group(1).strip()
        
        if not weak_section:
            return weak_areas
        
        # Split by lines
        lines = weak_section.split('\n')
        
        for line in lines:
            line = line.strip()
            
            # Skip empty lines or lines with only asterisks/bullets
            if not line or re.match(r'^[\*•\-]+$', line):
                continue
            
            # Stop at encouragement text
            if line.startswith("You're") or re.search(r'[A-Z][a-z]+.*!$', line):
                break
            
            # Stop at table markup
            if line.startswith('|'):
                break
            
            # Stop at numbered recommendations
            if re.match(r'^\d+[\.)]\s+[A-Z]', line):
                break
            
            # Remove bullet markers
            cleaned_line = re.sub(r'^[•\-*]\s*', '', line).strip()
            
            # Only add if it's a reasonable topic name (not empty after cleaning)
            if cleaned_line and len(cleaned_line) < 100:
                weak_areas.append(cleaned_line)
        
        return weak_areas
    
    def save_learned_topic(self, student_id, class_name, subject, topic, content):
        """Save learned topic for a student"""
        print(f"🔍 DEBUG: Attempting to save - student_id={student_id}, class={class_name}, subject={subject}, topic={topic}")
        print(f"🔍 DEBUG: Content length: {len(content) if content else 0}")
    
        try:
            conn = self.connect()
            cursor = conn.cursor()
        
            print(f"🔍 DEBUG: Connection established, executing INSERT...")
        
            cursor.execute("""
                INSERT INTO learned_topics (student_id, class, subject, topic, learned_content)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (student_id, subject, topic)
                DO UPDATE SET learned_content = EXCLUDED.learned_content,
                            created_at = CURRENT_TIMESTAMP;
            """, (student_id, class_name, subject, topic, content))
        
            print(f"🔍 DEBUG: Query executed, rows affected: {cursor.rowcount}")
        
            conn.commit()
            print("🔍 DEBUG: Commit successful")
        
            cursor.close()
            conn.close()
            print("✅ Learned topic saved successfully.")
            return True
        except Exception as e:
            print(f"❌ Error saving learned topic: {e}")
            import traceback
            traceback.print_exc()
            return False

    def get_learned_topics(self, student_id, class_name):
        """Get topics learned by the student for a specific class"""
        try:
            conn = self.connect()
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            cursor.execute("""
                SELECT topic, learned_content, created_at, subject, class
                FROM learned_topics
                WHERE student_id = %s AND class = %s
                ORDER BY created_at DESC
            """, (student_id, class_name))

            results = cursor.fetchall()

            cursor.close()
            conn.close()

            return [dict(row) for row in results]

        except Exception as e:
            print(f"Error fetching learned topics: {e}")
            return []

    
    # ==================== STUDENT PROGRESS TRACKING ====================
    
    def save_practice_result(self, student_id, subject, topic, question, answer, feedback):
        """Save student's practice question result and update progress tracking"""
        try:
            conn = self.connect()
            cursor = conn.cursor()
            
            # ✅ IMPROVED DETECTION - Same logic as evaluate_answer
            feedback_lower = feedback.lower().strip()
            
            # Check for explicit markers at the beginning
            if feedback_lower.startswith("correct"):
                is_correct = True
            elif feedback_lower.startswith("partially"):
                is_correct = False
            elif feedback_lower.startswith("incorrect") or feedback_lower.startswith("wrong"):
                is_correct = False
            else:
                # Fallback with word boundaries
                import re
                if re.search(r'\b(incorrect|wrong|not correct|not right)\b', feedback_lower):
                    is_correct = False
                elif re.search(r'\b(^correct|right|well done|excellent|perfect|great job)\b', feedback_lower):
                    is_correct = True
                else:
                    is_correct = False
            
            cursor.execute("""
                SELECT id, attempts, correct_attempts
                FROM student_progress
                WHERE student_id = %s AND subject = %s AND topic = %s
            """, (student_id, subject, topic))
            
            result = cursor.fetchone()
            
            if result:
                progress_id, attempts, correct_attempts = result
                new_attempts = attempts + 1
                new_correct = correct_attempts + (1 if is_correct else 0)
                
                cursor.execute("""
                    UPDATE student_progress
                    SET attempts = %s, 
                        correct_attempts = %s,
                        last_feedback = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (new_attempts, new_correct, feedback, progress_id))
            else:
                cursor.execute("SELECT class FROM user_details WHERE id = %s", (student_id,))
                class_result = cursor.fetchone()
                student_class = class_result[0] if class_result else 'Unknown'
                
                cursor.execute("""
                    INSERT INTO student_progress (student_id, class, subject, topic, attempts, correct_attempts, last_feedback)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (student_id, student_class, subject, topic, 1, (1 if is_correct else 0), feedback))
            
            # Award points for practicing
            points = 5 if is_correct else 2
            self.add_points(student_id, points, f"Practice: {topic}")
            
            conn.commit()
            cursor.close()
            conn.close()
            
            return True
            
        except Exception as e:
            print(f"Error saving practice result: {e}")
            return False
        
    def get_student_progress(self, student_id, subject=None):
        """Get student's practice progress"""
        try:
            conn = self.connect()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            if subject:
                query = """
                    SELECT * FROM student_progress 
                    WHERE student_id = %s AND subject = %s
                    ORDER BY updated_at DESC
                """
                cursor.execute(query, (student_id, subject))
            else:
                query = """
                    SELECT * FROM student_progress 
                    WHERE student_id = %s
                    ORDER BY updated_at DESC
                """
                cursor.execute(query, (student_id,))
            
            results = cursor.fetchall()
            
            cursor.close()
            conn.close()
            
            return [dict(row) for row in results]
            
        except Exception as e:
            print(f"Error fetching student progress: {e}")
            return []

    # Add these methods to the Database class in database.py

    def get_students_in_class(self, class_name):
        """Get all students in a specific class"""
        try:
            conn = self.connect()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute("""
                SELECT id, full_name, email
                FROM user_details
                WHERE role = 'student' AND class = %s
                ORDER BY full_name
            """, (class_name,))
            
            results = cursor.fetchall()
            
            cursor.close()
            conn.close()
            
            return [dict(row) for row in results]
            
        except Exception as e:
            print(f"Error fetching students: {e}")
            return []

    def get_student_paper_reports(self, student_id):
        """Get summary of all paper analyses for a student"""
        try:
            conn = self.connect()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute("""
                SELECT 
                    id,
                    subject,
                    created_at,
                    analysis_by_model
                FROM paper_analysis
                WHERE student_id = %s
                ORDER BY created_at DESC
            """, (student_id,))
            
            results = cursor.fetchall()
            
            # Extract marks and percentages from analysis
            paper_reports = []
            for row in results:
                analysis = row['analysis_by_model']
                
                # Try to extract marks from analysis text
                marks_match = re.search(r'(\d+)\s*(?:out of|/)\s*(\d+)', analysis, re.IGNORECASE)
                percentage_match = re.search(r'(\d+(?:\.\d+)?)\s*%', analysis)
                
                obtained_marks = marks_match.group(1) if marks_match else "N/A"
                total_marks = marks_match.group(2) if marks_match else "N/A"
                percentage = percentage_match.group(1) if percentage_match else "N/A"
                
                paper_reports.append({
                    'id': row['id'],
                    'subject': row['subject'],
                    'date': row['created_at'].strftime('%Y-%m-%d'),
                    'obtained_marks': obtained_marks,
                    'total_marks': total_marks,
                    'percentage': percentage
                })
            
            cursor.close()
            conn.close()
            
            return paper_reports
            
        except Exception as e:
            print(f"Error fetching paper reports: {e}")
            return []

    def get_student_quiz_summary(self, student_id):
        """Get summary of all quiz attempts for a student"""
        try:
            conn = self.connect()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute("""
                SELECT 
                    qa.id,
                    q.title,
                    q.subject,
                    qa.score,
                    qa.total_marks,
                    qa.submitted_at,
                    qa.time_taken
                FROM quiz_attempts qa
                JOIN quizzes q ON qa.quiz_id = q.id
                WHERE qa.student_id = %s AND qa.score IS NOT NULL
                ORDER BY qa.submitted_at DESC
            """, (student_id,))
            
            results = cursor.fetchall()
            
            quiz_summary = []
            for row in results:
                percentage = round((row['score'] / row['total_marks']) * 100, 1) if row['total_marks'] > 0 else 0
                
                quiz_summary.append({
                    'id': row['id'],
                    'title': row['title'],
                    'subject': row['subject'],
                    'obtained_marks': row['score'],
                    'total_marks': row['total_marks'],
                    'percentage': percentage,
                    'date': row['submitted_at'].strftime('%Y-%m-%d'),
                    'time_taken': f"{row['time_taken'] // 60}m {row['time_taken'] % 60}s"
                })
            
            cursor.close()
            conn.close()
            
            return quiz_summary
            
        except Exception as e:
            print(f"Error fetching quiz summary: {e}")
            return []

    def get_student_weak_topics_with_progress(self, student_id):
        """Get weak topics and practice progress for each"""
        try:
            conn = self.connect()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Get weak topics from paper analysis
            weak_topics = self.get_weak_topics_history(student_id)
            
            # Get progress for each weak topic
            topics_with_progress = []
            seen_topics = set()
            
            for topic_data in weak_topics:
                topic = topic_data['weak_area']
                subject = topic_data['subject']
                
                # Skip duplicates
                topic_key = f"{subject}:{topic}"
                if topic_key in seen_topics:
                    continue
                seen_topics.add(topic_key)
                
                # Get practice progress for this topic
                cursor.execute("""
                    SELECT 
                        attempts,
                        correct_attempts,
                        last_feedback,
                        updated_at
                    FROM student_progress
                    WHERE student_id = %s AND subject = %s AND topic = %s
                """, (student_id, subject, topic))
                
                progress = cursor.fetchone()
                
                if progress:
                    accuracy = round((progress['correct_attempts'] / progress['attempts']) * 100, 1) if progress['attempts'] > 0 else 0
                    
                    topics_with_progress.append({
                        'subject': subject,
                        'topic': topic,
                        'attempts': progress['attempts'],
                        'correct_attempts': progress['correct_attempts'],
                        'accuracy': accuracy,
                        'last_practiced': progress['updated_at'].strftime('%Y-%m-%d'),
                        'status': 'Improving' if accuracy >= 70 else 'Needs Practice'
                    })
                else:
                    topics_with_progress.append({
                        'subject': subject,
                        'topic': topic,
                        'attempts': 0,
                        'correct_attempts': 0,
                        'accuracy': 0,
                        'last_practiced': 'Never',
                        'status': 'Not Started'
                    })
            
            cursor.close()
            conn.close()
            
            return topics_with_progress
            
        except Exception as e:
            print(f"Error fetching weak topics with progress: {e}")
            return []


    def _initialize_gamification(self, student_id):
        """Initialize gamification record for a student (if missing)"""
        try:
            conn = self.connect()
            cursor = conn.cursor()
        
            cursor.execute("""
                INSERT INTO student_gamification (student_id)
                VALUES (%s)
                ON CONFLICT (student_id) DO NOTHING
            """, (student_id,))
        
            conn.commit()
            cursor.close()
            conn.close()
        
            return True
        except Exception as e:
            print(f"Error initializing gamification: {e}")
            return False
    # ==================== GAMIFICATION ====================
    
    def add_points(self, student_id, points, reason):
        """Add points to student and check for badges"""
        try:
            conn = self.connect()
            cursor = conn.cursor()
            
            # Update streak
            cursor.execute("""
                SELECT last_activity_date, current_streak, longest_streak
                FROM student_gamification
                WHERE student_id = %s
            """, (student_id,))
            
            result = cursor.fetchone()
            if result:
                last_date, current_streak, longest_streak = result
                today = datetime.now().date()
                
                if last_date:
                    days_diff = (today - last_date).days
                    if days_diff == 1:
                        current_streak += 1
                    elif days_diff > 1:
                        current_streak = 1
                else:
                    current_streak = 1
                
                longest_streak = max(longest_streak, current_streak)
                
                cursor.execute("""
                    UPDATE student_gamification
                    SET total_points = total_points + %s,
                        current_streak = %s,
                        longest_streak = %s,
                        last_activity_date = %s,
                        level = FLOOR((total_points + %s) / 100) + 1,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE student_id = %s
                """, (points, current_streak, longest_streak, today, points, student_id))
                
                # Check for badge achievements
                self._check_and_award_badges(cursor, student_id, points, current_streak)
            
            conn.commit()
            cursor.close()
            conn.close()
            
            return True
            
        except Exception as e:
            print(f"Error adding points: {e}")
            return False
    
    def _check_and_award_badges(self, cursor, student_id, new_points, current_streak):
        """Check and award badges based on achievements"""
        try:
            # Get current stats
            cursor.execute("""
                SELECT total_points, level FROM student_gamification
                WHERE student_id = %s
            """, (student_id,))
            
            result = cursor.fetchone()
            if not result:
                return
            
            total_points, level = result
            
            badges_to_award = []
            
            # Point-based badges
            if total_points >= 100 and not self._has_badge(cursor, student_id, "Century"):
                badges_to_award.append(("Century", "Earned 100 points", "🏆"))
            
            if total_points >= 500 and not self._has_badge(cursor, student_id, "Champion"):
                badges_to_award.append(("Champion", "Earned 500 points", "🏅"))
            
            if total_points >= 1000 and not self._has_badge(cursor, student_id, "Legend"):
                badges_to_award.append(("Legend", "Earned 1000 points", "👑"))
            
            # Streak-based badges
            if current_streak >= 7 and not self._has_badge(cursor, student_id, "Week Warrior"):
                badges_to_award.append(("Week Warrior", "7-day learning streak", "🔥"))
            
            if current_streak >= 30 and not self._has_badge(cursor, student_id, "Month Master"):
                badges_to_award.append(("Month Master", "30-day learning streak", "⭐"))
            
            # Level-based badges
            if level >= 5 and not self._has_badge(cursor, student_id, "Rising Star"):
                badges_to_award.append(("Rising Star", "Reached Level 5", "🌟"))
            
            if level >= 10 and not self._has_badge(cursor, student_id, "Superstar"):
                badges_to_award.append(("Superstar", "Reached Level 10", "💫"))
            
            # Award badges
            for badge_name, description, icon in badges_to_award:
                cursor.execute("""
                    INSERT INTO badges (student_id, badge_name, badge_description, badge_icon)
                    VALUES (%s, %s, %s, %s)
                """, (student_id, badge_name, description, icon))
                
                # Create notification
                cursor.execute("""
                    INSERT INTO notifications (user_id, title, message, notification_type)
                    VALUES (%s, %s, %s, %s)
                """, (student_id, "New Badge Earned!", f"Congratulations! You earned the '{badge_name}' badge: {description}", "achievement"))
            
        except Exception as e:
            print(f"Error checking badges: {e}")
    
    def _has_badge(self, cursor, student_id, badge_name):
        """Check if student already has a badge"""
        cursor.execute("""
            SELECT id FROM badges
            WHERE student_id = %s AND badge_name = %s
        """, (student_id, badge_name))
        return cursor.fetchone() is not None
    
    def get_student_gamification(self, student_id):
        """Get student's gamification stats"""
        try:
            conn = self.connect()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute("""
                SELECT * FROM student_gamification
                WHERE student_id = %s
            """, (student_id,))
            
            result = cursor.fetchone()
            
            cursor.close()
            conn.close()
            
            return dict(result) if result else None
            
        except Exception as e:
            print(f"Error fetching gamification: {e}")
            return None
    
    def get_student_badges(self, student_id):
        """Get all badges earned by student"""
        try:
            conn = self.connect()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute("""
                SELECT * FROM badges
                WHERE student_id = %s
                ORDER BY earned_at DESC
            """, (student_id,))
            
            results = cursor.fetchall()
            
            cursor.close()
            conn.close()
            
            return [dict(row) for row in results]
            
        except Exception as e:
            print(f"Error fetching badges: {e}")
            return []
    
    # ==================== QUIZ MANAGEMENT ====================
    
    def create_quiz(self, teacher_id, class_name, subject, title, duration_minutes, total_marks, deadline, questions):
        """Create a new quiz with questions"""
        try:
            conn = self.connect()
            cursor = conn.cursor()
            
            # Insert quiz
            cursor.execute("""
                INSERT INTO quizzes (teacher_id, class, subject, title, duration_minutes, total_marks, deadline)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (teacher_id, class_name, subject, title, duration_minutes, total_marks, deadline))
            
            quiz_id = cursor.fetchone()[0]
            
            # Insert questions
            for i, q in enumerate(questions, 1):
                cursor.execute("""
                    INSERT INTO quiz_questions (quiz_id, question_text, question_type, options, correct_answer, marks, order_num)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (quiz_id, q['question'], q['type'], json.dumps(q.get('options')), q['answer'], q['marks'], i))
            
            # Notify students
            cursor.execute("""
                SELECT id FROM user_details
                WHERE role = 'student' AND class = %s
            """, (class_name,))
            
            students = cursor.fetchall()
            for student in students:
                cursor.execute("""
                    INSERT INTO notifications (user_id, title, message, notification_type)
                    VALUES (%s, %s, %s, %s)
                """, (student[0], "New Quiz Available", f"Quiz '{title}' for {subject} is now available!", "quiz"))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            return quiz_id
            
        except Exception as e:
            print(f"Error creating quiz: {e}")
            return None
    
    def get_quizzes_for_class(self, class_name, subject=None):
        """Get all quizzes for a class"""
        try:
            conn = self.connect()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            if subject:
                cursor.execute("""
                    SELECT q.*, u.full_name as teacher_name
                    FROM quizzes q
                    JOIN user_details u ON q.teacher_id = u.id
                    WHERE q.class = %s AND q.subject = %s
                    ORDER BY q.created_at DESC
                """, (class_name, subject))
            else:
                cursor.execute("""
                    SELECT q.*, u.full_name as teacher_name
                    FROM quizzes q
                    JOIN user_details u ON q.teacher_id = u.id
                    WHERE q.class = %s
                    ORDER BY q.created_at DESC
                """, (class_name,))
            
            results = cursor.fetchall()
            
            cursor.close()
            conn.close()
            
            return [dict(row) for row in results]
            
        except Exception as e:
            print(f"Error fetching quizzes: {e}")
            return []
    
    
    
    def get_quiz_questions(self, quiz_id):
        """Get all questions for a quiz"""
        try:
            conn = self.connect()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
        
            cursor.execute("""
                SELECT * FROM quiz_questions
                WHERE quiz_id = %s
                ORDER BY order_num
            """, (quiz_id,))
        
            results = cursor.fetchall()
        
            # Parse JSON options if they exist
            questions = []
            for row in results:
                q = dict(row)
                if q['options'] and isinstance(q['options'], str):
                    import json
                    try:
                        q['options'] = json.loads(q['options'])
                    except:
                        q['options'] = []
                questions.append(q)
        
            cursor.close()
            conn.close()
        
            return questions
        
        except Exception as e:
            print(f"Error fetching quiz questions: {e}")
            return []
    
    def submit_quiz_attempt(self, quiz_id, student_id, answers, time_taken):
        """Submit a quiz attempt"""
        try:
            conn = self.connect()
            cursor = conn.cursor()
            
            # Get quiz details
            cursor.execute("SELECT total_marks FROM quizzes WHERE id = %s", (quiz_id,))
            total_marks = cursor.fetchone()[0]
            
            # Insert attempt
            cursor.execute("""
                INSERT INTO quiz_attempts (quiz_id, student_id, answers, time_taken, total_marks)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            """, (quiz_id, student_id, json.dumps(answers), time_taken, total_marks))
            
            attempt_id = cursor.fetchone()[0]
            
            # Award points for completing quiz
            self.add_points(student_id, 20, "Quiz Completed")
            
            conn.commit()
            cursor.close()
            conn.close()
            
            return attempt_id
            
        except Exception as e:
            print(f"Error submitting quiz: {e}")
            return None
    
    def add_subject_for_class(self, class_name, subject):
        """Add a new subject for a specific class (used when student wants to add curriculum)"""
        try:
            conn = self.connect()
            cursor = conn.cursor()
        
            # Check if subject already exists
            cursor.execute("""
                SELECT COUNT(*) FROM curriculum 
                WHERE class = %s AND subject = %s
            """, (class_name, subject))
        
            exists = cursor.fetchone()[0] > 0
        
            if not exists:
                # Create empty curriculum entry
                cursor.execute("""
                    INSERT INTO curriculum (class, subject, curriculum, updated_at)
                    VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                """, (class_name, subject, "Curriculum pending - Please contact your teacher to add content."))
            
                conn.commit()
                cursor.close()
                conn.close()
                return True, "Subject added successfully!"
            else:
                cursor.close()
                conn.close()
                return False, "This subject already exists for your class."
            
        except Exception as e:
            print(f"Error adding subject: {e}")
            return False, f"Error: {str(e)}"

    def evaluate_quiz_attempt(self, attempt_id, score, feedback):
        """Evaluate and score a quiz attempt"""
        try:
            conn = self.connect()
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE quiz_attempts
                SET score = %s, feedback = %s, evaluated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (score, feedback, attempt_id))
            
            # Get student_id and award bonus points for good performance
            cursor.execute("SELECT student_id, total_marks FROM quiz_attempts WHERE id = %s", (attempt_id,))
            result = cursor.fetchone()
            
            if result:
                student_id, total_marks = result
                percentage = (score / total_marks) * 100 if total_marks > 0 else 0
                
                if percentage >= 90:
                    self.add_points(student_id, 30, "Quiz Excellence (90%+)")
                elif percentage >= 75:
                    self.add_points(student_id, 20, "Quiz Success (75%+)")
                elif percentage >= 50:
                    self.add_points(student_id, 10, "Quiz Passed (50%+)")
            
            conn.commit()
            cursor.close()
            conn.close()
            
            return True
            
        except Exception as e:
            print(f"Error evaluating quiz: {e}")
            return False
    
    def get_student_quiz_attempts(self, student_id, quiz_id=None):
        """Get quiz attempts by student"""
        try:
            conn = self.connect()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            if quiz_id:
                cursor.execute("""
                    SELECT qa.*, q.title, q.subject
                    FROM quiz_attempts qa
                    JOIN quizzes q ON qa.quiz_id = q.id
                    WHERE qa.student_id = %s AND qa.quiz_id = %s
                    ORDER BY qa.submitted_at DESC
                """, (student_id, quiz_id))
            else:
                cursor.execute("""
                    SELECT qa.*, q.title, q.subject
                    FROM quiz_attempts qa
                    JOIN quizzes q ON qa.quiz_id = q.id
                    WHERE qa.student_id = %s
                    ORDER BY qa.submitted_at DESC
                """, (student_id,))
            
            results = cursor.fetchall()
            
            cursor.close()
            conn.close()
            
            return [dict(row) for row in results]
            
        except Exception as e:
            print(f"Error fetching quiz attempts: {e}")
            return []
    
    # ==================== NOTIFICATIONS ====================
    
    def create_notification(self, user_id, title, message, notification_type):
        """Create a notification for a user"""
        try:
            conn = self.connect()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO notifications (user_id, title, message, notification_type)
                VALUES (%s, %s, %s, %s)
                RETURNING id
            """, (user_id, title, message, notification_type))
            
            notification_id = cursor.fetchone()[0]
            
            conn.commit()
            cursor.close()
            conn.close()
            
            return notification_id
            
        except Exception as e:
            print(f"Error creating notification: {e}")
            return None
    
    def get_user_notifications(self, user_id, unread_only=False):
        """Get notifications for a user"""
        try:
            conn = self.connect()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            if unread_only:
                cursor.execute("""
                    SELECT * FROM notifications
                    WHERE user_id = %s AND is_read = FALSE
                    ORDER BY created_at DESC
                """, (user_id,))
            else:
                cursor.execute("""
                    SELECT * FROM notifications
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                    LIMIT 50
                """, (user_id,))
            
            results = cursor.fetchall()
            
            cursor.close()
            conn.close()
            
            return [dict(row) for row in results]
            
        except Exception as e:
            print(f"Error fetching notifications: {e}")
            return []
    
    def mark_notification_read(self, notification_id):
        """Mark a notification as read"""
        try:
            conn = self.connect()
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE notifications
                SET is_read = TRUE
                WHERE id = %s
            """, (notification_id,))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            return True
            
        except Exception as e:
            print(f"Error marking notification: {e}")
            return False
    
    # ==================== PARENT PORTAL ====================
    
    def link_parent_student(self, parent_id, student_id, relationship='parent'):
        """Link a parent to a student"""
        try:
            conn = self.connect()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO parent_students (parent_id, student_id, relationship)
                VALUES (%s, %s, %s)
                ON CONFLICT (parent_id, student_id) DO NOTHING
            """, (parent_id, student_id, relationship))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            return True
            
        except Exception as e:
            print(f"Error linking parent-student: {e}")
            return False
    
    def get_parent_students(self, parent_id):
        """Get all students linked to a parent"""
        try:
            conn = self.connect()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute("""
                SELECT u.*, ps.relationship
                FROM user_details u
                JOIN parent_students ps ON u.id = ps.student_id
                WHERE ps.parent_id = %s
            """, (parent_id,))
            
            results = cursor.fetchall()
            
            cursor.close()
            conn.close()
            
            return [dict(row) for row in results]
            
        except Exception as e:
            print(f"Error fetching parent students: {e}")
            return []
    
    def get_student_overview_for_parent(self, student_id):
        """Get comprehensive overview of student for parent"""
        try:
            conn = self.connect()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Get basic info
            cursor.execute("SELECT * FROM user_details WHERE id = %s", (student_id,))
            student_info = dict(cursor.fetchone())
            
            # Get gamification stats
            cursor.execute("SELECT * FROM student_gamification WHERE student_id = %s", (student_id,))
            gamification = cursor.fetchone()
            student_info['gamification'] = dict(gamification) if gamification else None
            
            # Get recent activities
            cursor.execute("""
                SELECT COUNT(*) as paper_count
                FROM paper_analysis
                WHERE student_id = %s AND created_at > NOW() - INTERVAL '30 days'
            """, (student_id,))
            student_info['recent_papers'] = cursor.fetchone()['paper_count']
            
            cursor.execute("""
                SELECT COUNT(*) as quiz_count
                FROM quiz_attempts
                WHERE student_id = %s AND submitted_at > NOW() - INTERVAL '30 days'
            """, (student_id,))
            student_info['recent_quizzes'] = cursor.fetchone()['quiz_count']
            
            # Get average scores
            cursor.execute("""
                SELECT AVG(score::float / total_marks * 100) as avg_score
                FROM quiz_attempts
                WHERE student_id = %s AND score IS NOT NULL
            """, (student_id,))
            avg_result = cursor.fetchone()
            student_info['average_score'] = round(avg_result['avg_score'], 1) if avg_result['avg_score'] else 0
            
            cursor.close()
            conn.close()
            
            return student_info
            
        except Exception as e:
            print(f"Error fetching student overview: {e}")
            return None
    
    # ==================== TEACHER ANALYTICS ====================
    
    def get_class_analytics(self, class_name):
        """Get comprehensive analytics for a class"""
        try:
            conn = self.connect()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            analytics = {}
            
            # Total students
            cursor.execute("""
                SELECT COUNT(*) as total_students
                FROM user_details
                WHERE role = 'student' AND class = %s
            """, (class_name,))
            analytics['total_students'] = cursor.fetchone()['total_students']
            
            # Average points
            cursor.execute("""
                SELECT AVG(sg.total_points) as avg_points, AVG(sg.current_streak) as avg_streak
                FROM student_gamification sg
                JOIN user_details u ON sg.student_id = u.id
                WHERE u.class = %s
            """, (class_name,))
            result = cursor.fetchone()
            analytics['avg_points'] = round(result['avg_points'] or 0, 1)
            analytics['avg_streak'] = round(result['avg_streak'] or 0, 1)
            
            # Paper submissions in last 30 days
            cursor.execute("""
                SELECT COUNT(*) as paper_count
                FROM paper_analysis pa
                JOIN user_details u ON pa.student_id = u.id
                WHERE u.class = %s AND pa.created_at > NOW() - INTERVAL '30 days'
            """, (class_name,))
            analytics['recent_papers'] = cursor.fetchone()['paper_count']
            
            # Average quiz performance
            cursor.execute("""
                SELECT AVG(qa.score::float / qa.total_marks * 100) as avg_quiz_score
                FROM quiz_attempts qa
                JOIN user_details u ON qa.student_id = u.id
                WHERE u.class = %s AND qa.score IS NOT NULL
            """, (class_name,))
            avg_result = cursor.fetchone()
            analytics['avg_quiz_score'] = round(avg_result['avg_quiz_score'] or 0, 1)
            
            # Top performers
            cursor.execute("""
                SELECT u.full_name, sg.total_points, sg.level, sg.current_streak
                FROM student_gamification sg
                JOIN user_details u ON sg.student_id = u.id
                WHERE u.class = %s
                ORDER BY sg.total_points DESC
                LIMIT 5
            """, (class_name,))
            analytics['top_performers'] = [dict(row) for row in cursor.fetchall()]
            
            # Subject-wise performance
            cursor.execute("""
                SELECT 
                    sp.subject,
                    COUNT(DISTINCT sp.student_id) AS student_count,
                    SUM(sp.attempts) AS total_attempts,
                    SUM(sp.correct_attempts) AS correct_attempts,
                    ROUND(AVG((sp.correct_attempts::numeric / NULLIF(sp.attempts, 0)) * 100), 1) AS avg_accuracy
                FROM student_progress sp
                JOIN user_details u ON sp.student_id = u.id
                WHERE u.class = %s
                GROUP BY sp.subject
            """, (class_name,))
            analytics['subject_performance'] = [dict(row) for row in cursor.fetchall()]

            cursor.close()
            conn.close()
            
            return analytics
            
        except Exception as e:
            print(f"Error fetching class analytics: {e}")
            return {}
    
    def get_student_performance_trend(self, student_id, days=30):
        """Get student performance trend over time"""
        try:
            conn = self.connect()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Quiz scores over time
            cursor.execute("""
                SELECT 
                    DATE(submitted_at) as date,
                    AVG(score::float / total_marks * 100) as avg_score
                FROM quiz_attempts
                WHERE student_id = %s 
                    AND submitted_at > NOW() - INTERVAL '%s days'
                    AND score IS NOT NULL
                GROUP BY DATE(submitted_at)
                ORDER BY date
            """, (student_id, days))
            
            trend_data = [dict(row) for row in cursor.fetchall()]
            
            cursor.close()
            conn.close()
            
            return trend_data
            
        except Exception as e:
            print(f"Error fetching performance trend: {e}")
            return []
    
    # ==================== SEARCH STUDENTS ====================
    
    def search_students(self, email=None, class_name=None):
        try:
            conn = self.connect()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
        
            if email:
                cursor.execute("""
                    SELECT id, full_name, email, class 
                    FROM user_details 
                    WHERE email = %s AND role = 'student'
                """, (email,))
            elif class_name:
                cursor.execute("""
                    SELECT id, full_name, email, class 
                    FROM user_details 
                    WHERE class = %s AND role = 'student'
                """, (class_name,))
            else:
                return []
        
            results = cursor.fetchall()
            cursor.close()
            conn.close()
            return [dict(row) for row in results]
        
        except Exception as e:
            print(f"Error searching students: {e}")
            return []
