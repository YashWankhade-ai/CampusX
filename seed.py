import uuid
import datetime
from datetime import timezone
from app import create_app
from app.extensions import db
from app.utils.hashing import hash_password
from app.models.user import User, Profile, Role, UserRole
from app.models.academic import Institution, Department, Degree, Program, AcademicSession, Semester, Subject, Unit, Topic
from app.models.resource import StudyMaterial, MaterialVersion, FileMetadata, ResourceCategory, MaterialType, ResourceComment, ResourceRating
from app.models.ai_chat import ChatSession, ChatMessage, AICitation
from app.models.approval import ApprovalWorkflow, ApprovalStep, ApprovalRequest, ApprovalAction
from app.models.bookmark import BookmarkFolder, Bookmark
from app.models.audit import AuditLog, LoginHistory
from app.models.contribution import UserContribution, ContributionType, Leaderboard

def seed_database():
    app = create_app("development")
    with app.app_context():
        print("[SEED] Seeding CampusX database with realistic enterprise data...")
        db.create_all()

        # 1. Roles
        roles_data = [
            ("SUPER_ADMIN", "Full system administrator access"),
            ("ADMIN", "System administrator access"),
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

        # 2. Users across all 6 roles
        password_hash = hash_password("Password123!")
        users_seed = [
            ("superadmin@campusx.edu", "Super", "Admin", "SUPER_ADMIN"),
            ("admin@campusx.edu", "System", "Administrator", "ADMIN"),
            ("deptadmin@campusx.edu", "Department", "Coordinator", "DEPARTMENT_ADMIN"),
            ("prof.smith@campusx.edu", "Alan", "Smith", "FACULTY"),
            ("student.alex@campusx.edu", "Alex", "Johnson", "STUDENT"),
            ("guest.user@campusx.edu", "Guest", "Visitor", "GUEST")
        ]
        users_dict = {}
        for email, first, last, role_name in users_seed:
            user = db.session.query(User).filter_by(email=email).first()
            if not user:
                user = User(
                    email=email,
                    password_hash=password_hash,
                    first_name=first,
                    last_name=last,
                    role=role_name,
                    is_verified=True,
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
            users_dict[role_name] = user

        # 3. Academic Hierarchy
        inst = db.session.query(Institution).filter_by(name="CampusX Institute of Technology").first()
        if not inst:
            inst = Institution(name="CampusX Institute of Technology", location="Cambridge, MA")
            db.session.add(inst)
            db.session.flush()

        dept = db.session.query(Department).filter_by(name="Computer Science & Engineering").first()
        if not dept:
            dept = Department(name="Computer Science & Engineering", institution_id=inst.id)
            db.session.add(dept)
            db.session.flush()

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

        # 4. Resource & Material
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
                author_id=users_dict["FACULTY"].id,
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
                user_id=users_dict["STUDENT"].id,
                content="Extremely helpful notes for CS301 mid-term exam preparation!"
            )
            db.session.add(comment)

            rating = ResourceRating(
                resource_id=mat.id,
                user_id=users_dict["STUDENT"].id,
                score=5
            )
            db.session.add(rating)

        # 5. AI Chat Session & Citation
        chat_sess = db.session.query(ChatSession).filter_by(title="Algorithm Complexity Clarifications").first()
        if not chat_sess:
            chat_sess = ChatSession(
                user_id=users_dict["STUDENT"].id,
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

        # 6. Bookmarks & Audit Logs
        folder = db.session.query(BookmarkFolder).filter_by(name="Exam Prep 2025").first()
        if not folder:
            folder = BookmarkFolder(user_id=users_dict["STUDENT"].id, name="Exam Prep 2025")
            db.session.add(folder)
            db.session.flush()

            bm = Bookmark(user_id=users_dict["STUDENT"].id, folder_id=folder.id, resource_id=mat.id)
            db.session.add(bm)

        audit = AuditLog(
            user_id=users_dict["SUPER_ADMIN"].id,
            action="SYSTEM_INIT_SEED",
            entity_type="SYSTEM",
            entity_id=str(inst.id),
            changes={"status": "SUCCESS", "seeded_models": 15},
            ip_address="127.0.0.1"
        )
        db.session.add(audit)

        db.session.commit()
        print("[SEED SUCCESS] Database successfully seeded with 6 roles, academic hierarchy, study materials, AI chat sessions, bookmarks, and audit logs!")

if __name__ == "__main__":
    seed_database()
