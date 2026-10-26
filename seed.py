import uuid
import datetime
from datetime import timezone
from app import create_app
from app.extensions import db
from app.utils.hashing import hash_password
from app.models.user import User, Profile, Role, UserRole
from app.models.academic import Institution, Department, Degree, Program, AcademicSession, Semester, Subject, Unit, Topic
from app.models.enrollment import AcademicYear, StudentEnrollment, CourseEnrollment, InstructorAssignment
from app.models.resource import StudyMaterial, MaterialVersion, FileMetadata, ResourceCategory, MaterialType, ResourceComment, ResourceRating
from app.models.ai_chat import ChatSession, ChatMessage, AICitation
from app.models.bookmark import BookmarkFolder, Bookmark
from app.models.notification import Notification
from app.models.audit import AuditLog

def seed_database():
    app = create_app("development")
    with app.app_context():
        print("[SEED] Seeding CampusX database with realistic enterprise data...")
        db.create_all()

        # 1. Institution (Tenant)
        inst = db.session.query(Institution).filter_by(name="CampusX Institute of Technology").first()
        if not inst:
            inst = Institution(
                name="CampusX Institute of Technology",
                short_name="CIT",
                code="CIT01",
                city="Cambridge",
                state="MA",
                country="India",
                domain_whitelist=["campusx.edu"],
                subscription_tier="enterprise",
                is_active=True
            )
            db.session.add(inst)
            db.session.flush()

        # 2. Department
        dept = db.session.query(Department).filter_by(name="Computer Science & Engineering").first()
        if not dept:
            dept = Department(name="Computer Science & Engineering", institution_id=inst.id)
            db.session.add(dept)
            db.session.flush()

        # 3. Roles
        roles_data = [
            ("SUPER_ADMIN", "Full system administrator access"),
            ("ADMIN", "System administrator access"),
            ("INSTITUTION_ADMIN", "Institution-level administrator access"),
            ("DEPARTMENT_ADMIN", "Department level administrator"),
            ("FACULTY", "Faculty member and course instructor"),
            ("STUDENT", "Enrolled student user"),
            ("GUEST", "Guest user with view-only permissions")
        ]
        roles_dict = {}
        for name, desc in roles_data:
            role = db.session.query(Role).filter_by(name=name).first()
            if not role:
                role = Role(name=name, description=desc)
                db.session.add(role)
                db.session.flush()
            roles_dict[name] = role

        # 4. Users across all roles (Password: Password123!)
        password_hash = hash_password("Password123!")
        users_seed = [
            ("superadmin@campusx.edu", "Super", "Admin", "SUPER_ADMIN"),
            ("admin@campusx.edu", "System", "Administrator", "ADMIN"),
            ("deptadmin@campusx.edu", "Department", "Coordinator", "DEPARTMENT_ADMIN"),
            ("prof.smith@campusx.edu", "Alan", "Smith", "FACULTY"),
            ("faculty@campusx.edu", "Faculty", "Instructor", "FACULTY"),
            ("student.alex@campusx.edu", "Alex", "Johnson", "STUDENT"),
            ("student@campusx.edu", "Campus", "Student", "STUDENT"),
            ("guest.user@campusx.edu", "Guest", "Visitor", "GUEST")
        ]
        users_dict = {}
        for email, first, last, role_name in users_seed:
            user = db.session.query(User).filter_by(email=email).first()
            if not user:
                user = User(
                    institution_id=inst.id,
                    department_id=dept.id,
                    email=email,
                    email_normalized=email.lower(),
                    full_name=f"{first} {last}",
                    password_hash=password_hash,
                    role=role_name,
                    status="active",
                    failed_login_attempts=0
                )
                db.session.add(user)
                db.session.flush()
                # Profile
                profile = Profile(user_id=user.id, bio=f"Hello! I am {first} {last} at CampusX.", avatar_url=f"https://api.dicebear.com/7.x/avataaars/svg?seed={first}")
                db.session.add(profile)
                # UserRole link
                ur = UserRole(user_id=user.id, role_id=roles_dict[role_name].id)
                db.session.add(ur)
            else:
                user.status = "active"
                user.password_hash = password_hash
                user.institution_id = inst.id
                user.department_id = dept.id
                db.session.flush()
            users_dict[email] = user

        # 5. Academic Hierarchy
        deg = db.session.query(Degree).filter_by(name="Bachelor of Technology").first()
        if not deg:
            deg = Degree(name="Bachelor of Technology", level="Bachelor")
            db.session.add(deg)
            db.session.flush()

        prog = db.session.query(Program).filter_by(name="Computer Science").first()
        if not prog:
            prog = Program(name="Computer Science", department_id=dept.id, degree_id=deg.id)
            db.session.add(prog)
            db.session.flush()

        sess = db.session.query(AcademicSession).filter_by(name="2025-2026").first()
        if not sess:
            sess = AcademicSession(name="2025-2026", start_year=2025, end_year=2026)
            db.session.add(sess)
            db.session.flush()

        sem = db.session.query(Semester).filter_by(name="Fall Semester 2025").first()
        if not sem:
            sem = Semester(name="Fall Semester 2025", academic_session_id=sess.id, number=5, is_active=True)
            db.session.add(sem)
            db.session.flush()

        subj = db.session.query(Subject).filter_by(code="CS301").first()
        if not subj:
            subj = Subject(code="CS301", name="Design and Analysis of Algorithms", program_id=prog.id, semester_id=sem.id, credits=4)
            db.session.add(subj)
            db.session.flush()

        unit = db.session.query(Unit).filter_by(title="Dynamic Programming & Greedy Algorithms").first()
        if not unit:
            unit = Unit(title="Dynamic Programming & Greedy Algorithms", subject_id=subj.id, number=3)
            db.session.add(unit)
            db.session.flush()

        topic = db.session.query(Topic).filter_by(title="Knapsack Problem & Optimal Substructure").first()
        if not topic:
            topic = Topic(title="Knapsack Problem & Optimal Substructure", unit_id=unit.id, description="Detailed study of 0/1 Knapsack, Fractional Knapsack, and DP state transitions.")
            db.session.add(topic)
            db.session.flush()

        # 6. Academic Year & Enrollments
        ay = db.session.query(AcademicYear).filter_by(start_year=2025, end_year=2026).first()
        if not ay:
            ay = AcademicYear(start_year=2025, end_year=2026, label="2025-2026")
            db.session.add(ay)
            db.session.flush()

        # Enroll students
        for s_email in ["student.alex@campusx.edu", "student@campusx.edu"]:
            s_user = users_dict[s_email]
            ste = db.session.query(StudentEnrollment).filter_by(user_id=s_user.id, program_id=prog.id, academic_year_id=ay.id).first()
            if not ste:
                ste = StudentEnrollment(
                    user_id=s_user.id,
                    program_id=prog.id,
                    academic_year_id=ay.id,
                    institution_id=inst.id,
                    status="active"
                )
                db.session.add(ste)

            ce = db.session.query(CourseEnrollment).filter_by(student_id=s_user.id, course_id=subj.id, semester_id=sem.id).first()
            if not ce:
                ce = CourseEnrollment(
                    student_id=s_user.id,
                    course_id=subj.id,
                    semester_id=sem.id,
                    institution_id=inst.id
                )
                db.session.add(ce)

        # Faculty Assignments
        for f_email in ["prof.smith@campusx.edu", "faculty@campusx.edu"]:
            f_user = users_dict[f_email]
            ia = db.session.query(InstructorAssignment).filter_by(instructor_id=f_user.id, course_id=subj.id, semester_id=sem.id).first()
            if not ia:
                ia = InstructorAssignment(
                    instructor_id=f_user.id,
                    course_id=subj.id,
                    semester_id=sem.id,
                    institution_id=inst.id,
                    is_primary=True
                )
                db.session.add(ia)

        # 7. Resource & Material
        cat = db.session.query(ResourceCategory).filter_by(name="Lecture Notes").first()
        if not cat:
            cat = ResourceCategory(name="Lecture Notes", description="Official and student-contributed lecture note materials")
            db.session.add(cat)
            db.session.flush()

        mat = db.session.query(StudyMaterial).filter_by(title="Algorithms Comprehensive Master Notes").first()
        if not mat:
            mat = StudyMaterial(
                title="Algorithms Comprehensive Master Notes",
                description="Complete notes on Divide and Conquer, Greedy Strategy, Dynamic Programming, and Graph Algorithms with time complexities.",
                topic_id=topic.id,
                subject_id=subj.id,
                author_id=users_dict["prof.smith@campusx.edu"].id,
                material_type=MaterialType.NOTE,
                status="APPROVED"
            )
            db.session.add(mat)
            db.session.flush()

            file_meta = FileMetadata(
                original_name="algorithms_master_notes_2025.pdf",
                mime_type="application/pdf",
                size_bytes=4194304,
                storage_path="uploads/materials/algorithms_master_notes_2025.pdf",
                checksum="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
            )
            db.session.add(file_meta)
            db.session.flush()

            ver = MaterialVersion(
                study_material_id=mat.id,
                version_number=1,
                file_metadata_id=file_meta.id,
                change_summary="Initial release of CS301 Master Notes"
            )
            db.session.add(ver)

            comment = ResourceComment(
                resource_id=mat.id,
                user_id=users_dict["student.alex@campusx.edu"].id,
                content="Extremely helpful notes for CS301 mid-term exam preparation!"
            )
            db.session.add(comment)

            rating = ResourceRating(
                resource_id=mat.id,
                user_id=users_dict["student.alex@campusx.edu"].id,
                score=5
            )
            db.session.add(rating)

        # 8. Notifications
        for email in ["student.alex@campusx.edu", "student@campusx.edu"]:
            u = users_dict[email]
            notif = db.session.query(Notification).filter_by(recipient_id=u.id, title="Welcome to CampusX").first()
            if not notif:
                notif = Notification(
                    recipient_id=u.id,
                    institution_id=inst.id,
                    title="Welcome to CampusX",
                    message="Explore your courses, AI study tools, and library materials.",
                    notification_type="resource.approved",
                    is_read=False
                )
                db.session.add(notif)

        # 9. AI Chat Session & Citation
        chat_sess = db.session.query(ChatSession).filter_by(title="Algorithm Complexity Clarifications").first()
        if not chat_sess:
            chat_sess = ChatSession(
                user_id=users_dict["student.alex@campusx.edu"].id,
                title="Algorithm Complexity Clarifications",
                context_data={"model": "claude-3-5-sonnet-20241022"}
            )
            db.session.add(chat_sess)
            db.session.flush()

            msg1 = ChatMessage(session_id=chat_sess.id, sender_type="user", content="What is the recurrence relation for Merge Sort?")
            msg2 = ChatMessage(session_id=chat_sess.id, sender_type="ai", content="The recurrence relation for Merge Sort is T(n) = 2T(n/2) + O(n). By Master Theorem, this solves to O(n log n).", metadata_json={"confidence_score": 0.95})
            db.session.add_all([msg1, msg2])
            db.session.flush()

            citation = AICitation(message_id=msg2.id, study_material_id=mat.id, excerpt="Merge sort splits the array into two halves, recursively sorts them, and merges in linear time.", relevance_score=0.92)
            db.session.add(citation)

        # 10. Bookmarks & Audit Logs
        folder = db.session.query(BookmarkFolder).filter_by(name="Exam Prep 2025").first()
        if not folder:
            folder = BookmarkFolder(user_id=users_dict["student.alex@campusx.edu"].id, name="Exam Prep 2025")
            db.session.add(folder)
            db.session.flush()

            bm = Bookmark(user_id=users_dict["student.alex@campusx.edu"].id, folder_id=folder.id, resource_id=mat.id)
            db.session.add(bm)

        audit = AuditLog(
            user_id=users_dict["superadmin@campusx.edu"].id,
            action="SYSTEM_INIT_SEED",
            entity_type="SYSTEM",
            entity_id=str(inst.id),
            changes={"status": "SUCCESS", "seeded_models": 25},
            ip_address="127.0.0.1"
        )
        db.session.add(audit)

        db.session.commit()
        print("[SEED SUCCESS] Database successfully seeded with verified users, enrollments, courses, resources, and notifications!")

if __name__ == "__main__":
    seed_database()
