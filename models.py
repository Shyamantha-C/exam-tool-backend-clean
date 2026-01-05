# models.py
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    roll_no = db.Column(db.String, nullable=True)
    name = db.Column(db.String(150))
    username = db.Column(db.String(80), unique=True, nullable=True)  # generated login username
    email = db.Column(db.String(200))
    phone = db.Column(db.String(20))
    password = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)
    opt_a = db.Column(db.String(300))
    opt_b = db.Column(db.String(300))
    opt_c = db.Column(db.String(300))
    opt_d = db.Column(db.String(300))
    correct = db.Column(db.String(5))
    per_question_time = db.Column(db.Integer, default=30)
    order_index = db.Column(db.Integer, default=0)

class Attempt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"))
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    finished_at = db.Column(db.DateTime, nullable=True)
    score = db.Column(db.Integer, nullable=True)

class Answer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    attempt_id = db.Column(db.Integer, db.ForeignKey("attempt.id"))
    question_id = db.Column(db.Integer, db.ForeignKey("question.id"))
    selected = db.Column(db.String(5))
    answered_at = db.Column(db.DateTime, default=datetime.utcnow)




