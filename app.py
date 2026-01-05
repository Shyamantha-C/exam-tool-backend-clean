# app.py
import os
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import pandas as pd

from models_original import db, Student, Question, Attempt, Answer

# =========================
# App Setup
# =========================
app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

# =========================
# Static Frontend
# =========================
@app.route('/')
def index():
    return send_from_directory('.', 'admin-login.html')

@app.route('/<path:path>')
def serve_static(path):
    if os.path.isfile(path):
        return send_from_directory('.', path)
    return send_from_directory('.', 'admin-login.html')

# =========================
# Database (SQLite)
# =========================
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "exam.db")

app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DB_PATH}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)
with app.app_context():
    db.create_all()

# =========================
# Admin Auth (UserID + Password)
# =========================
ADMIN_USERS_RAW = os.environ.get("ADMIN_USERS")
if not ADMIN_USERS_RAW:
    raise RuntimeError("ADMIN_USERS env variable not set")

# Parse: user:pass,user:pass
ADMIN_USERS = {}
for pair in ADMIN_USERS_RAW.split(","):
    if ":" in pair:
        user, pwd = pair.split(":", 1)
        ADMIN_USERS[user.strip()] = pwd.strip()

# Generate tokens (simple but stable)
ADMIN_TOKENS = {
    user: f"TOKEN_{user}_{pwd}"
    for user, pwd in ADMIN_USERS.items()
}

def is_admin(req):
    token = req.headers.get("X-ADMIN-TOKEN")
    return token in ADMIN_TOKENS.values()

# =========================
# Allowed Students (Excel)
# =========================
ALLOWED_XLSX = os.path.join(BASE_DIR, "allowed_students.xlsx")
ALLOWED = {}

def load_allowed_students():
    global ALLOWED
    ALLOWED = {}

    if not os.path.exists(ALLOWED_XLSX):
        print("allowed_students.xlsx not found")
        return

    df = pd.read_excel(ALLOWED_XLSX)

    email_col = None
    phone_col = None

    for col in df.columns:
        c = str(col).lower()
        if "email" in c:
            email_col = col
        if "phone" in c or "mobile" in c:
            phone_col = col

    if not email_col or not phone_col:
        raise RuntimeError("Excel must contain email & phone columns")

    for _, row in df.iterrows():
        email = str(row[email_col]).strip().lower()
        phone = str(row[phone_col]).strip()
        if "@" in email and len(phone) >= 10:
            ALLOWED[email] = phone[-10:]

    print(f"Loaded {len(ALLOWED)} students")

load_allowed_students()

# =========================
# Admin APIs
# =========================
@app.route("/api/admin/login", methods=["POST"])
def admin_login():
    data = request.json or {}
    user_id = data.get("userId")
    password = data.get("password")

    if user_id in ADMIN_USERS and ADMIN_USERS[user_id] == password:
        return jsonify({
            "status": "ok",
            "token": ADMIN_TOKENS[user_id]
        })

    return jsonify({"status": "error", "msg": "Invalid credentials"}), 401

@app.route("/api/admin/upload-students", methods=["POST"])
def upload_students():
    if not is_admin(request):
        return jsonify({"error": "forbidden"}), 403

    file = request.files.get("file")
    if not file or not file.filename.endswith(".xlsx"):
        return jsonify({"error": "invalid file"}), 400

    file.save(ALLOWED_XLSX)
    load_allowed_students()
    return jsonify({"status": "ok", "count": len(ALLOWED)})

@app.route("/api/admin/add-question", methods=["POST"])
def add_question():
    if not is_admin(request):
        return jsonify({"error": "forbidden"}), 403

    data = request.json or {}
    index = Question.query.count() + 1

    q = Question(
        text=data.get("text", ""),
        opt_a=data.get("opta", ""),
        opt_b=data.get("optb", ""),
        opt_c=data.get("optc", ""),
        opt_d=data.get("optd", ""),
        correct=(data.get("correct") or "").upper(),
        order_index=index,
        per_question_time=int(data.get("per_question_time", 60))
    )

    db.session.add(q)
    db.session.commit()
    return jsonify({"status": "ok"})

@app.route("/api/admin/questions")
def get_questions():
    if not is_admin(request):
        return jsonify({"error": "forbidden"}), 403

    qs = Question.query.order_by(Question.order_index.asc()).all()
    return jsonify([{
        "id": q.id,
        "text": q.text,
        "opt_a": q.opt_a,
        "opt_b": q.opt_b,
        "opt_c": q.opt_c,
        "opt_d": q.opt_d,
        "correct": q.correct,
        "order_index": q.order_index,
        "per_question_time": q.per_question_time
    } for q in qs])

# =========================
# Student APIs
# =========================
@app.route("/api/student/login", methods=["POST"])
def student_login():
    data = request.json or {}
    email = data.get("email", "").lower().strip()
    password = data.get("password", "").strip()

    if ALLOWED.get(email) != password:
        return jsonify({"error": "invalid"}), 401

    student = Student.query.filter_by(email=email).first()
    if not student:
        student = Student(
            email=email,
            phone=password,
            name=email.split("@")[0]
        )
        db.session.add(student)
        db.session.commit()

    return jsonify({"status": "ok", "student_id": student.id})

@app.route("/api/start", methods=["POST"])
def start_exam():
    sid = request.json.get("student_id")
    if Attempt.query.filter_by(student_id=sid).first():
        return jsonify({"error": "already attempted"}), 400

    att = Attempt(student_id=sid, started_at=datetime.utcnow())
    db.session.add(att)
    db.session.commit()
    return jsonify({"attempt_id": att.id})

@app.route("/api/questions_for/<int:attempt_id>")
def questions_for(attempt_id):
    qs = Question.query.order_by(Question.order_index.asc()).all()
    payload = []
    total_time = 0

    for q in qs:
        payload.append({
            "id": q.id,
            "text": q.text,
            "options": {
                "A": q.opt_a,
                "B": q.opt_b,
                "C": q.opt_c,
                "D": q.opt_d
            },
            "per_question_time": q.per_question_time
        })
        total_time += q.per_question_time

    return jsonify({"questions": payload, "total_time": total_time})

@app.route("/api/submit", methods=["POST"])
def submit_exam():
    data = request.json or {}
    attempt_id = data.get("attempt_id")
    answers = data.get("answers", {})

    att = Attempt.query.get(attempt_id)
    if not att:
        return jsonify({"error": "invalid attempt"}), 400

    for qid, sel in answers.items():
        ans = Answer(
            attempt_id=attempt_id,
            question_id=int(qid),
            selected=sel
        )
        db.session.add(ans)

    db.session.flush()

    score = 0
    for a in Answer.query.filter_by(attempt_id=attempt_id).all():
        q = Question.query.get(a.question_id)
        if q and a.selected and a.selected.upper() == q.correct:
            score += 1

    att.score = score
    att.finished_at = datetime.utcnow()
    db.session.commit()

    return jsonify({"status": "ok", "score": score})

# =========================
# Health Check
# =========================
@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})

# =========================
# Local Run
# =========================
if __name__ == "__main__":
    app.run(debug=True)
