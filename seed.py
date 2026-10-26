import uuid
import datetime
from datetime import timezone
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

def _execute_seed():
    print("[SEED] Seeding CampusX database with realistic enterprise data...", flush=True)
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
            domain_whitelist=["campusx.edu", "ghrua.edu.in"],
            subscription_tier="enterprise",
            is_active=True
        )
        db.session.add(inst)
        db.session.flush()

    # 2. Departments
    dept_names = [
        "Computer Science & Engineering",
        "Artificial Intelligence & Data Science",
        "Information Technology",
        "Electronics & Communication Engineering",
        "Mechanical Engineering",
        "Civil Engineering"
    ]
    depts = {}
    for dname in dept_names:
        d = db.session.query(Department).filter_by(name=dname, institution_id=inst.id).first()
        if not d:
            d = Department(name=dname, institution_id=inst.id)
            db.session.add(d)
            db.session.flush()
        depts[dname] = d

    cse_dept = depts["Computer Science & Engineering"]
    aids_dept = depts["Artificial Intelligence & Data Science"]
    it_dept = depts["Information Technology"]

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
        ("superadmin@campusx.edu", "Super", "Admin", "SUPER_ADMIN", cse_dept.id, "ADM-001"),
        ("admin@campusx.edu", "System", "Administrator", "ADMIN", cse_dept.id, "ADM-002"),
        ("deptadmin@campusx.edu", "Department", "Coordinator", "DEPARTMENT_ADMIN", cse_dept.id, "DPT-001"),
        ("prof.smith@campusx.edu", "Alan", "Smith", "FACULTY", cse_dept.id, "FAC-CSE-001"),
        ("faculty@campusx.edu", "Faculty", "Instructor", "FACULTY", cse_dept.id, "FAC-CSE-002"),
        ("yash.wankhde.cse@ghrua.edu.in", "Yash", "Wankhade", "STUDENT", cse_dept.id, "STU-CSE-2026-001"),
        ("student@campusx.edu", "Campus", "Student", "STUDENT", cse_dept.id, "STU-CSE-2026-002"),
        ("student.alex@campusx.edu", "Alex", "Johnson", "STUDENT", aids_dept.id, "STU-AI-2026-003"),
        ("guest.user@campusx.edu", "Guest", "Visitor", "GUEST", cse_dept.id, "GST-001")
    ]
    users_dict = {}
    for email, first, last, role_name, dept_id, inst_id in users_seed:
        user = db.session.query(User).filter_by(email=email).first()
        if not user:
            user = User(
                institution_id=inst.id,
                department_id=dept_id,
                email=email,
                email_normalized=email.lower(),
                full_name=f"{first} {last}",
                password_hash=password_hash,
                role=role_name,
                status="active",
                failed_login_attempts=0,
                metadata_json={"institutional_id": inst_id}
            )
            db.session.add(user)
            db.session.flush()
            # Profile
            profile = Profile(
                user_id=user.id,
                bio=f"Hello! I am {first} {last} at CampusX.",
                avatar_url=f"https://api.dicebear.com/7.x/avataaars/svg?seed={first}"
            )
            db.session.add(profile)
            # UserRole link
            ur = UserRole(user_id=user.id, role_id=roles_dict[role_name].id)
            db.session.add(ur)
        else:
            user.status = "active"
            user.password_hash = password_hash
            user.institution_id = inst.id
            user.department_id = dept_id
            if not user.metadata_json or not user.metadata_json.get("institutional_id"):
                user.metadata_json = {"institutional_id": inst_id}
            db.session.flush()
        users_dict[email] = user

    # 5. Academic Degrees & Programs
    deg = db.session.query(Degree).filter_by(name="Bachelor of Technology").first()
    if not deg:
        deg = Degree(name="Bachelor of Technology", level="Bachelor")
        db.session.add(deg)
        db.session.flush()

    programs_data = [
        ("Computer Science & Engineering", cse_dept.id),
        ("Artificial Intelligence & Data Science", aids_dept.id),
        ("Information Technology", it_dept.id)
    ]
    progs = {}
    for pname, did in programs_data:
        prog = db.session.query(Program).filter_by(name=pname).first()
        if not prog:
            prog = Program(name=pname, department_id=did, degree_id=deg.id)
            db.session.add(prog)
            db.session.flush()
        progs[pname] = prog

    cse_prog = progs["Computer Science & Engineering"]

    # 6. Academic Session & Semesters
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

    # 7. Multiple Core Subjects
    subjects_data = [
        ("CS301", "Design and Analysis of Algorithms", cse_prog.id, 4),
        ("CS201", "Data Structures and Algorithms", cse_prog.id, 4),
        ("CS304", "Operating Systems & Virtualization", cse_prog.id, 3),
        ("AI201", "Foundations of Machine Learning", progs["Artificial Intelligence & Data Science"].id, 4),
        ("AI302", "Deep Learning & Neural Networks", progs["Artificial Intelligence & Data Science"].id, 4),
        ("IT205", "Cloud Infrastructure & DevOps", progs["Information Technology"].id, 3),
    ]
    subjs = {}
    for code, name, pid, credits in subjects_data:
        s = db.session.query(Subject).filter_by(code=code).first()
        if not s:
            s = Subject(code=code, name=name, program_id=pid, semester_id=sem.id, credits=credits)
            db.session.add(s)
            db.session.flush()
        subjs[code] = s

    cs301 = subjs["CS301"]
    cs201 = subjs["CS201"]

    # Units & Topics for CS301
    unit = db.session.query(Unit).filter_by(title="Dynamic Programming & Greedy Algorithms").first()
    if not unit:
        unit = Unit(title="Dynamic Programming & Greedy Algorithms", subject_id=cs301.id, number=3)
        db.session.add(unit)
        db.session.flush()

    topic = db.session.query(Topic).filter_by(title="Knapsack Problem & Optimal Substructure").first()
    if not topic:
        topic = Topic(title="Knapsack Problem & Optimal Substructure", unit_id=unit.id, description="0/1 Knapsack, Fractional Knapsack, and DP state transitions.")
        db.session.add(topic)
        db.session.flush()

    # 8. Academic Year & Student Enrollments
    ay = db.session.query(AcademicYear).filter_by(start_year=2025, end_year=2026).first()
    if not ay:
        ay = AcademicYear(start_year=2025, end_year=2026, label="2025-2026")
        db.session.add(ay)
        db.session.flush()

    # Enroll students into subjects
    for s_email in ["student.alex@campusx.edu", "student@campusx.edu", "yash.wankhde.cse@ghrua.edu.in"]:
        s_user = users_dict[s_email]
        ste = db.session.query(StudentEnrollment).filter_by(user_id=s_user.id, program_id=cse_prog.id, academic_year_id=ay.id).first()
        if not ste:
            ste = StudentEnrollment(
                user_id=s_user.id,
                program_id=cse_prog.id,
                academic_year_id=ay.id,
                institution_id=inst.id,
                status="active"
            )
            db.session.add(ste)

        for s_code in ["CS301", "CS201", "CS304", "AI201"]:
            target_subj = subjs[s_code]
            ce = db.session.query(CourseEnrollment).filter_by(student_id=s_user.id, course_id=target_subj.id, semester_id=sem.id).first()
            if not ce:
                ce = CourseEnrollment(
                    student_id=s_user.id,
                    course_id=target_subj.id,
                    semester_id=sem.id,
                    institution_id=inst.id
                )
                db.session.add(ce)

    # Faculty Assignments
    for f_email in ["prof.smith@campusx.edu", "faculty@campusx.edu"]:
        f_user = users_dict[f_email]
        for s_code in ["CS301", "CS201"]:
            target_subj = subjs[s_code]
            ia = db.session.query(InstructorAssignment).filter_by(instructor_id=f_user.id, course_id=target_subj.id, semester_id=sem.id).first()
            if not ia:
                ia = InstructorAssignment(
                    instructor_id=f_user.id,
                    course_id=target_subj.id,
                    semester_id=sem.id,
                    institution_id=inst.id,
                    is_primary=True
                )
                db.session.add(ia)

    # 9. Resource Categories & Curated Study Materials
    categories_data = [
        ("Lecture Notes", "Official syllabus notes and annotated faculty slides"),
        ("Question Banks", "Mid-term and end-term verified previous year exam papers"),
        ("Lab Manuals", "Coding problem statements and implementation guides"),
        ("Syllabus", "Curriculum breakdown and credit distributions")
    ]
    for cname, cdesc in categories_data:
        cat = db.session.query(ResourceCategory).filter_by(name=cname).first()
        if not cat:
            cat = ResourceCategory(name=cname, description=cdesc)
            db.session.add(cat)
            db.session.flush()

    # Materials for library & search
    materials_data = [
        (
            "Algorithms Comprehensive Master Notes",
            "Complete notes on Divide and Conquer, Greedy Strategy, Dynamic Programming, and Graph Algorithms with time complexities.",
            cs301.id,
            "algorithms_master_notes_2025.pdf"
        ),
        (
            "Data Structures Hand-Written Revision Vault",
            "Handwritten review sheets for Trees, Heaps, AVL Trees, Hash Tables, and Disjoint Set Unions.",
            cs201.id,
            "data_structures_revision_vault.pdf"
        ),
        (
            "Operating Systems Process & Memory Management",
            "Detailed lecture notes covering CPU scheduling, semaphores, deadlock avoidance, paging, and virtual memory.",
            subjs["CS304"].id,
            "operating_systems_notes_unit2.pdf"
        ),
        (
            "Foundations of Machine Learning Formula Sheet",
            "Linear regression, logistic regression, gradient descent derivations, and bias-variance tradeoff summary.",
            subjs["AI201"].id,
            "machine_learning_formula_cheatsheet.pdf"
        )
    ]

    for title, desc, subject_id, filename in materials_data:
        mat = db.session.query(StudyMaterial).filter_by(title=title).first()
        if not mat:
            mat = StudyMaterial(
                title=title,
                description=desc,
                topic_id=topic.id if subject_id == cs301.id else None,
                subject_id=subject_id,
                author_id=users_dict["prof.smith@campusx.edu"].id,
                material_type=MaterialType.NOTE,
                status="APPROVED"
            )
            db.session.add(mat)
            db.session.flush()

            file_meta = FileMetadata(
                original_name=filename,
                mime_type="application/pdf",
                size_bytes=4194304,
                storage_path=f"uploads/materials/{filename}",
                checksum="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
            )
            db.session.add(file_meta)
            db.session.flush()

            ver = MaterialVersion(
                study_material_id=mat.id,
                version_number=1,
                file_metadata_id=file_meta.id,
                change_summary=f"Initial release of {title}"
            )
            db.session.add(ver)

            comment = ResourceComment(
                resource_id=mat.id,
                user_id=users_dict["student@campusx.edu"].id,
                content="Extremely helpful notes for exam preparation!"
            )
            db.session.add(comment)

            rating = ResourceRating(
                resource_id=mat.id,
                user_id=users_dict["student@campusx.edu"].id,
                score=5
            )
            db.session.add(rating)

    # 10. Notifications
    for email in ["student.alex@campusx.edu", "student@campusx.edu", "yash.wankhde.cse@ghrua.edu.in"]:
        u = users_dict[email]
        notif = db.session.query(Notification).filter_by(recipient_id=u.id, title="Welcome to CampusX").first()
        if not notif:
            notif = Notification(
                recipient_id=u.id,
                institution_id=inst.id,
                title="Welcome to CampusX",
                message="Explore your enrolled courses, AI study tools, and library materials.",
                notification_type="resource.approved",
                is_read=False
            )
            db.session.add(notif)

    # 11. AI Chat Session
    chat_sess = db.session.query(ChatSession).filter_by(title="Algorithm Complexity Clarifications").first()
    if not chat_sess:
        chat_sess = ChatSession(
            user_id=users_dict["yash.wankhde.cse@ghrua.edu.in"].id,
            title="Algorithm Complexity Clarifications",
            context_data={"model": "zero-gpu-engine"}
        )
        db.session.add(chat_sess)
        db.session.flush()

        msg1 = ChatMessage(session_id=chat_sess.id, sender_type="user", content="What is the recurrence relation for Merge Sort?")
        msg2 = ChatMessage(session_id=chat_sess.id, sender_type="ai", content="The recurrence relation for Merge Sort is T(n) = 2T(n/2) + O(n). By Master Theorem, this solves to O(n log n).", metadata_json={"confidence_score": 0.95})
        db.session.add_all([msg1, msg2])
        db.session.flush()

    db.session.commit()
    print("[SEED SUCCESS] Database successfully populated with complete enterprise courses, departments, notes, and user accounts!", flush=True)

def seed_database(app=None):
    from flask import has_app_context
    if has_app_context():
        _execute_seed()
    elif app is not None:
        with app.app_context():
            _execute_seed()
    else:
        from app import create_app
        app = create_app("development", run_seed=False)
        with app.app_context():
            _execute_seed()

if __name__ == "__main__":
    seed_database()
