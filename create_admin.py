from app import app
from models import db, Admin

with app.app_context():
    db.create_all()

    if not Admin.query.filter_by(username="admin1").first():
        db.session.add(Admin(username="admin1", password="admin123"))

    if not Admin.query.filter_by(username="admin2").first():
        db.session.add(Admin(username="admin2", password="admin456"))

    db.session.commit()
    print("Admins created")
