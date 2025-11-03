-- Table 1: user_details (already exists, but here's the structure for reference)
CREATE TABLE IF NOT EXISTS user_details (
    id SERIAL PRIMARY KEY,
    full_name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL CHECK (role IN ('teacher', 'student', 'parent')),
    class VARCHAR(50) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table 2: curriculum
CREATE TABLE IF NOT EXISTS curriculum (
    id SERIAL PRIMARY KEY,
    class VARCHAR(50) NOT NULL,
    subject VARCHAR(100) NOT NULL,
    curriculum TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(class, subject)
);

-- Table 3: paper_analysis
CREATE TABLE IF NOT EXISTS paper_analysis (
    id SERIAL PRIMARY KEY,
    class VARCHAR(50) NOT NULL,
    student_id INTEGER NOT NULL,
    student_name VARCHAR(255) NOT NULL,
    subject VARCHAR(100) NOT NULL,
    student_paper TEXT NOT NULL,
    analysis_by_model TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES user_details(id) ON DELETE CASCADE
);
-- Table 4: student_progress
CREATE TABLE IF NOT EXISTS student_progress (
    id SERIAL PRIMARY KEY,
    student_id INTEGER NOT NULL,
    class VARCHAR(50) NOT NULL,
    subject VARCHAR(100) NOT NULL,
    topic VARCHAR(255) NOT NULL,
    attempts INTEGER DEFAULT 0,
    correct_attempts INTEGER DEFAULT 0,
    last_feedback TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES user_details(id) ON DELETE CASCADE
);

-- Table 5: learned_topics
CREATE TABLE IF NOT EXISTS learned_topics (
    id SERIAL PRIMARY KEY,
    student_id INTEGER NOT NULL REFERENCES user_details(id) ON DELETE CASCADE,
    class VARCHAR(50) NOT NULL,
    subject VARCHAR(100) NOT NULL,
    topic VARCHAR(255) NOT NULL,
    learned_content TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (student_id, subject, topic)
);

-- Table 6: gamification - student points and badges
CREATE TABLE IF NOT EXISTS student_gamification (
    id SERIAL PRIMARY KEY,
    student_id INTEGER NOT NULL REFERENCES user_details(id) ON DELETE CASCADE,
    total_points INTEGER DEFAULT 0,
    current_streak INTEGER DEFAULT 0,
    longest_streak INTEGER DEFAULT 0,
    last_activity_date DATE,
    level INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(student_id)
);

-- Table 7: badges earned by students
CREATE TABLE IF NOT EXISTS badges (
    id SERIAL PRIMARY KEY,
    student_id INTEGER NOT NULL REFERENCES user_details(id) ON DELETE CASCADE,
    badge_name VARCHAR(100) NOT NULL,
    badge_description TEXT,
    badge_icon VARCHAR(50),
    earned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table 8: quizzes
CREATE TABLE IF NOT EXISTS quizzes (
    id SERIAL PRIMARY KEY,
    teacher_id INTEGER NOT NULL REFERENCES user_details(id) ON DELETE CASCADE,
    class VARCHAR(50) NOT NULL,
    subject VARCHAR(100) NOT NULL,
    title VARCHAR(255) NOT NULL,
    duration_minutes INTEGER NOT NULL,
    total_marks INTEGER NOT NULL,
    deadline TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table 9: quiz questions
CREATE TABLE IF NOT EXISTS quiz_questions (
    id SERIAL PRIMARY KEY,
    quiz_id INTEGER NOT NULL REFERENCES quizzes(id) ON DELETE CASCADE,
    question_text TEXT NOT NULL,
    question_type VARCHAR(50) CHECK (question_type IN ('mcq', 'short_answer', 'long_answer')),
    options JSONB,  -- For MCQ options
    correct_answer TEXT,
    marks INTEGER NOT NULL,
    order_num INTEGER NOT NULL
);

-- Table 10: quiz attempts
CREATE TABLE IF NOT EXISTS quiz_attempts (
    id SERIAL PRIMARY KEY,
    quiz_id INTEGER NOT NULL REFERENCES quizzes(id) ON DELETE CASCADE,
    student_id INTEGER NOT NULL REFERENCES user_details(id) ON DELETE CASCADE,
    answers JSONB,
    score FLOAT,
    total_marks INTEGER,
    time_taken INTEGER, -- in seconds
    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    evaluated_at TIMESTAMP,
    feedback TEXT
);

-- Table 11: notifications
CREATE TABLE IF NOT EXISTS notifications (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES user_details(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    notification_type VARCHAR(50) CHECK (notification_type IN ('quiz', 'deadline', 'achievement', 'general')),
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table 12: parent-student relationships
CREATE TABLE IF NOT EXISTS parent_students (
    id SERIAL PRIMARY KEY,
    parent_id INTEGER NOT NULL REFERENCES user_details(id) ON DELETE CASCADE,
    student_id INTEGER NOT NULL REFERENCES user_details(id) ON DELETE CASCADE,
    relationship VARCHAR(50) DEFAULT 'parent',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(parent_id, student_id)
);

CREATE TABLE image_embeddings (
    id SERIAL PRIMARY KEY,
    file_name TEXT,
    image_path TEXT,
    embedding VECTOR(3584)
);
ALTER TABLE image_embeddings
ALTER COLUMN embedding TYPE halfvec(3584) USING embedding::halfvec(3584);
CREATE INDEX ON image_embeddings USING hnsw (embedding halfvec_cosine_ops);
-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_curriculum_class_subject ON curriculum(class, subject);
CREATE INDEX IF NOT EXISTS idx_paper_analysis_student ON paper_analysis(student_id);
CREATE INDEX IF NOT EXISTS idx_paper_analysis_class ON paper_analysis(class);
CREATE INDEX IF NOT EXISTS idx_student_progress_student ON student_progress(student_id);
CREATE INDEX IF NOT EXISTS idx_quiz_attempts_student ON quiz_attempts(student_id);
CREATE INDEX IF NOT EXISTS idx_quiz_attempts_quiz ON quiz_attempts(quiz_id);
CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id);
CREATE INDEX IF NOT EXISTS idx_badges_student ON badges(student_id);
CREATE INDEX IF NOT EXISTS idx_parent_students_parent ON parent_students(parent_id);
CREATE INDEX IF NOT EXISTS idx_parent_students_student ON parent_students(student_id);
