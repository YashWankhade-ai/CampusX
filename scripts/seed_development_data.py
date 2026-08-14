from app import create_app
from app.extensions import db
from app.models import User, Role, University, College, Department
import uuid

def seed():
    app = create_app()
    with app.app_context():
        print("Seeding database...")
        db.create_all()

        if not Role.query.first():
            student = Role(name="student", description="Student Role")
            faculty = Role(name="faculty", description="Faculty Role")
            admin = Role(name="admin", description="Admin Role")
            db.session.add_all([student, faculty, admin])
            db.session.commit()
        
        if not University.query.first():
            uni = University(name="Global Tech University", location="Metropolis")
            db.session.add(uni)
            db.session.commit()
            
            col = College(name="College of Engineering", university_id=uni.id)
            db.session.add(col)
            db.session.commit()
            
            dept = Department(name="Computer Science", college_id=col.id)
            db.session.add(dept)
            db.session.commit()

            admin_user = User(
                email="admin@campusx.edu",
                password_hash="hashed_password",
                first_name="Admin",
                last_name="User",
                role="admin",
                department_id=dept.id
            )
            db.session.add(admin_user)
            db.session.commit()

        print("Seeding complete.")

if __name__ == "__main__":
    seed()
