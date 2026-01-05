# app.py
import os
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import pandas as pd

from models import db, Student, Question, Attempt, Answer
import secrets

# =============================
# ADMIN CONFIG (TEMP, SIMPLE)
# =============================
ADMINS = {
    "admin1": "admin123",
    "admin2": "admin456"
}

ADMIN_TOKENS = set()

# =========================
# Exam time Shedule
# =========================
EXAM_START_TIME = None
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


def is_admin(req):
    token = req.headers.get("X-ADMIN-TOKEN")
    return token in ADMIN_TOKENS

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

    name_col = None
    email_col = None
    phone_col = None

    for col in df.columns: # pyright: ignore[reportUndefinedVariable]
        c = str(col).lower()
        if "name" in c:
            name_col = col
        if "email" in c:
            email_col = col
        if "phone" in c or "mobile" in c:
            phone_col = col

    if not email_col or not phone_col:
        raise RuntimeError("Excel must contain email & phone columns")

    for _, row in df.iterrows(): # pyright: ignore[reportUndefinedVariable]
        email = str(row[email_col]).strip().lower()
        phone = str(row[phone_col]).strip()
        name = str(row[name_col]).strip() if name_col else email.split("@")[0]

        if "@" in email and len(phone) >= 10:
            ALLOWED[email] = {
                "name": name,
                "phone": phone[-10:]
            }

    print(f"Loaded {len(ALLOWED)} students")

load_allowed_students()

# =========================
# Admin APIs
# =========================
# from models import Admin
# import secrets

# ADMIN_TOKENS = {}  # token → admin_id

# @app.route("/api/admin/login", methods=["POST"])
# def admin_login():
#     data = request.json or {}
#     username = data.get("username")
#     password = data.get("password")

#     admin = Admin.query.filter_by(username=username, password=password).first()

#     if not admin:
#         return jsonify({"status": "error", "msg": "Invalid credentials"}), 401

#     token = secrets.token_hex(16)
#     ADMIN_TOKENS[token] = admin.id

#     return jsonify({"status": "ok", "token": token})

@app.route("/api/admin/login", methods=["POST"])
def admin_login():
    data = request.json or {}
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"status": "error", "msg": "Missing credentials"}), 400

    if username not in ADMINS or ADMINS[username] != password:
        return jsonify({"status": "error", "msg": "Invalid credentials"}), 401

    token = secrets.token_hex(16)
    ADMIN_TOKENS.add(token)

    return jsonify({
        "status": "ok",
        "token": token
    })


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

@app.route("/api/admin/excel-students", methods=["GET"])
def get_excel_students():
    if not is_admin(request):
        return jsonify({"error": "forbidden"}), 403

    students = []
    i = 1
    for email, data in ALLOWED.items():
        students.append({
        "id": i,
        "name": data["name"],
        "email": email,
        "phone": data["phone"]
    })
    i += 1

    return jsonify({
        "status": "ok",
        "total": len(students),
        "students": students
    })

@app.route("/api/admin/delete-excel-student", methods=["DELETE"])
def delete_excel_student():
    if not is_admin(request):
        return jsonify({"error": "forbidden"}), 403

    data = request.json or {}
    email = (data.get("email") or "").lower().strip()

    if not email or email not in ALLOWED:
        return jsonify({"error": "student not found"}), 404

    # Remove from memory
    del ALLOWED[email]

    # Rewrite Excel file
    try:
        df = pd.DataFrame(
            [{
                "name":data["name"],
                "email":email,
                "phone":data["phone"]
            } for email, data in ALLOWED.items()]
        )
        df.to_excel(ALLOWED_XLSX, index=False)
        load_allowed_students()
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({
        "status": "ok",
        "total": len(ALLOWED)
    })


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

    student = ALLOWED.get(email)

    if not student:
        return jsonify({"error": "invalid", "msg": "Email not found"}), 401

    if student["phone"] != password:
        return jsonify({"error": "invalid", "msg": "Wrong password"}), 401

    # Create student in DB if not exists
    db_student = Student.query.filter_by(email=email).first()
    if not db_student:
        db_student = Student(
            email=email,
            phone=student["phone"],
            name=student["name"]
        )
        db.session.add(db_student)
        db.session.commit()

    return jsonify({
        "status": "ok",
        "student_id": db_student.id,
        "name": student["name"]
    })


@app.route("/api/admin/set-exam-time", methods=["POST"])
def set_exam_time():
    if not is_admin(request):
        return jsonify({"status": "error"}), 403
    
    data = request.json
    time_str = data.get("datetime")  # format: "2025-04-05T19:00"
    
    try:
        EXAM_START_TIME = datetime.fromisoformat(time_str.replace("T", " "))
        return jsonify({
            "status": "ok", 
            "msg": f"Exam scheduled for {EXAM_START_TIME.strftime('%d %B %Y, %I:%M %p')}"
        })
    except:
        return jsonify({"status": "error", "msg": "Invalid time format"})

@app.route("/api/exam-time")
def get_exam_time():
    if EXAM_START_TIME:
        return jsonify({
            "scheduled": True,
            "start_time": EXAM_START_TIME.isoformat(),
            "time_str": EXAM_START_TIME.strftime("%d %B %Y, %I:%M %p")
        })
    return jsonify({"scheduled": False})

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
