import pytest
import uuid
from datetime import datetime, timezone
from app import create_app
from app.extensions import db

# Import all models across all 15 modules
from app.models.academic import (
    Institution, Department, Degree, Program, AcademicSession, Semester, Subject, Unit, Topic
)
from app.models.user import User, Role, UserRole, Profile, OTPCode
from app.models.resource import (
    StudyMaterial, MaterialVersion, FileMetadata, ResourceCategory,
    ResourceTag, ResourceTagAssociation, ResourceComment, ResourceRating, MaterialType
)
from app.models.approval import ApprovalWorkflow, ApprovalStep, ApprovalRequest, ApprovalAction
from app.models.ai_chat import ChatSession, ChatMessage, AICitation
from app.models.analytics import EventLog, DailyMetric, ResourceView
from app.models.audit import AuditLog, LoginHistory
from app.models.notification import NotificationTemplate, Notification, UserDevice
from app.models.contribution import ContributionType, UserContribution, Leaderboard, Badge
from app.models.qr_code import QRCode, QRCodeScan
from app.models.search import SearchQueryLog, SearchFilterLog
from app.models.bookmark import BookmarkFolder, Bookmark
from app.models.embedding import EmbeddingModelConfig, ResourceChunk, ChunkEmbedding
from app.models.enrollment import AcademicYear, StudentEnrollment, CourseEnrollment, InstructorAssignment


@pytest.fixture
def app():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def test_academic_hierarchy_models(app):
    """Test all academic domain models: Institution, Department, Degree, Program, AcademicSession, Semester, Subject, Unit, Topic."""
    with app.app_context():
        # 1. Institution
        inst = Institution(
            name="Apex University of Technology",
            short_name="ApexTech",
            code="APEX-001",
            domain_whitelist=["apex.edu"],
            city="Pune",
            state="Maharashtra"
        )
        db.session.add(inst)
        db.session.flush()
        assert inst.id is not None
        assert inst.is_active is True
        assert inst.is_deleted is False

        # 2. Department
        dept = Department(name="Computer Science & Engineering", institution_id=inst.id)
        db.session.add(dept)
        db.session.flush()
        assert dept.institution_id == inst.id
        assert dept in inst.departments

        # 3. Degree
        degree = Degree(name="Bachelor of Technology", level="UNDERGRADUATE")
        db.session.add(degree)
        db.session.flush()

        # 4. Program
        prog = Program(name="B.Tech Computer Science", department_id=dept.id, degree_id=degree.id)
        db.session.add(prog)
        db.session.flush()
        assert prog.department.name == "Computer Science & Engineering"
        assert prog.degree.name == "Bachelor of Technology"

        # 5. AcademicSession & Semester
        session = AcademicSession(name="2026-2027", start_year=2026, end_year=2027)
        db.session.add(session)
        db.session.flush()

        sem = Semester(name="Semester 1", academic_session_id=session.id, number=1, is_active=True)
        db.session.add(sem)
        db.session.flush()

        # 6. Subject
        subj = Subject(
            code="CS101",
            name="Data Structures and Algorithms",
            program_id=prog.id,
            semester_id=sem.id,
            credits=4
        )
        db.session.add(subj)
        db.session.flush()
        assert subj.program_id == prog.id
        assert subj.semester_id == sem.id
        assert subj.credits == 4

        # 7. Unit & Topic
        unit = Unit(title="Unit 1: Trees and Graphs", number=1, subject_id=subj.id)
        db.session.add(unit)
        db.session.flush()

        topic = Topic(title="Binary Search Trees", unit_id=unit.id, description="BST operations and balancing")
        db.session.add(topic)
        db.session.commit()

        # Query & Verify
        fetched_subj = db.session.query(Subject).filter_by(code="CS101").first()
        assert fetched_subj is not None
        assert len(fetched_subj.units) == 1
        assert len(fetched_subj.units[0].topics) == 1
        assert fetched_subj.units[0].topics[0].title == "Binary Search Trees"


def test_user_and_auth_models(app):
    """Test User, Role, UserRole, Profile, and OTPCode models."""
    with app.app_context():
        inst = Institution(name="Tech Academy", short_name="TA", code="TA-001", domain_whitelist=[])
        db.session.add(inst)
        db.session.flush()

        # User
        user = User(
            institution_id=inst.id,
            email="researcher@tech.edu",
            full_name="Dr. Alan Turing",
            password_hash="argon2id$hashed",
            role="FACULTY",
            status="active"
        )
        db.session.add(user)
        db.session.flush()
        assert user.first_name == "Dr."
        assert user.last_name == "Turing"
        assert user.email_normalized == "researcher@tech.edu"

        # Profile
        profile = Profile(
            user_id=user.id,
            bio="Pioneer of theoretical computer science and artificial intelligence.",
            avatar_url="/static/avatars/alan.png"
        )
        db.session.add(profile)
        db.session.flush()
        assert user.profile.bio.startswith("Pioneer")

        # Role & UserRole
        role = Role(name="FACULTY_HEAD", description="Head of Academic Department")
        db.session.add(role)
        db.session.flush()

        ur = UserRole(user_id=user.id, role_id=role.id)
        db.session.add(ur)
        db.session.flush()
        assert len(user.user_roles) == 1
        assert user.user_roles[0].role.name == "FACULTY_HEAD"

        # OTPCode
        otp = OTPCode(
            user_id=user.id,
            email="researcher@tech.edu",
            code_hash="sha256:hashedcode123",
            purpose="email_verification",
            expires_at=datetime.now(timezone.utc)
        )
        db.session.add(otp)
        db.session.commit()

        fetched_otp = db.session.query(OTPCode).filter_by(user_id=user.id).first()
        assert fetched_otp.code_hash == "sha256:hashedcode123"
        assert fetched_otp.purpose == "email_verification"


def test_resource_and_file_models(app):
    """Test StudyMaterial, MaterialVersion, FileMetadata, ResourceCategory, ResourceTag, ResourceComment, ResourceRating."""
    with app.app_context():
        inst = Institution(name="Resource Inst", short_name="RI", code="RI-001", domain_whitelist=[])
        db.session.add(inst)
        db.session.flush()

        author = User(
            institution_id=inst.id,
            email="author@ri.edu",
            full_name="Prof. Donald Knuth",
            password_hash="hash",
            role="FACULTY",
            status="active"
        )
        db.session.add(author)
        db.session.flush()

        # Category
        cat = db.session.query(ResourceCategory).filter_by(name="Advanced Research Papers").first()
        if not cat:
            cat = ResourceCategory(name="Advanced Research Papers", description="Official university syllabus notes")
            db.session.add(cat)
            db.session.flush()

        # StudyMaterial
        mat = StudyMaterial(
            title="Volume 1: Fundamental Algorithms",
            description="The definitive handbook on fundamental algorithms and data representations.",
            author_id=author.id,
            material_type=MaterialType.NOTE,
            status="APPROVED",
            faculty_name="Prof. Donald Knuth",
            department_name="Computer Science"
        )
        db.session.add(mat)
        db.session.flush()

        # FileMetadata
        fmeta = FileMetadata(
            original_name="algorithms_vol1.pdf",
            mime_type="application/pdf",
            size_bytes=10485760,
            storage_path="uploads/materials/algorithms_vol1.pdf",
            checksum="sha256:abc123def456"
        )
        db.session.add(fmeta)
        db.session.flush()

        # MaterialVersion
        ver = MaterialVersion(
            study_material_id=mat.id,
            version_number=1,
            file_metadata_id=fmeta.id,
            change_summary="Initial publication"
        )
        db.session.add(ver)
        db.session.flush()

        # Tag
        tag = db.session.query(ResourceTag).filter_by(name="Distributed Consensus").first()
        if not tag:
            tag = ResourceTag(name="Distributed Consensus")
            db.session.add(tag)
            db.session.flush()

        assoc = ResourceTagAssociation(resource_id=mat.id, tag_id=tag.id)
        db.session.add(assoc)
        db.session.flush()

        # Comment & Rating
        comment = ResourceComment(
            resource_id=mat.id,
            user_id=author.id,
            content="Chapter 2 tree algorithms have been updated with AVL balances."
        )
        db.session.add(comment)

        rating = ResourceRating(
            resource_id=mat.id,
            user_id=author.id,
            score=5
        )
        db.session.add(rating)
        db.session.commit()

        # Assertions
        fetched_mat = db.session.query(StudyMaterial).filter_by(title="Volume 1: Fundamental Algorithms").first()
        assert fetched_mat is not None
        assert len(fetched_mat.versions) == 1
        assert fetched_mat.versions[0].file_metadata.mime_type == "application/pdf"
        assert len(fetched_mat.comments) == 1
        assert len(fetched_mat.ratings) == 1
        assert fetched_mat.ratings[0].score == 5


def test_approval_and_workflow_models(app):
    """Test ApprovalWorkflow, ApprovalStep, ApprovalRequest, ApprovalAction."""
    with app.app_context():
        inst = Institution(name="Govt Engg College", short_name="GEC", code="GEC-001", domain_whitelist=[])
        db.session.add(inst)
        db.session.flush()

        user = User(institution_id=inst.id, email="approver@gec.edu", full_name="Dean Academics", password_hash="h", role="ADMIN", status="active")
        role = Role(name="REVIEWER_ROLE", description="Reviewer")
        db.session.add_all([user, role])
        db.session.flush()

        # StudyMaterial for approval action
        mat = StudyMaterial(title="Operating Systems Lab Manual", author_id=user.id, material_type=MaterialType.NOTE)
        db.session.add(mat)
        db.session.flush()

        wf = ApprovalWorkflow(name="Faculty Note Review Workflow", description="Multi-stage review for academic materials")
        db.session.add(wf)
        db.session.flush()

        step = ApprovalStep(workflow_id=wf.id, role_id=role.id, step_order=1)
        db.session.add(step)
        db.session.flush()

        req = ApprovalRequest(
            workflow_id=wf.id,
            requester_id=user.id,
            status="pending",
            target_resource_id=str(mat.id)
        )
        db.session.add(req)
        db.session.flush()

        action = ApprovalAction(
            resource_id=mat.id,
            approver_id=user.id,
            action="approve",
            comments="Material meets all academic board standards."
        )
        db.session.add(action)
        db.session.commit()

        fetched_req = db.session.query(ApprovalRequest).filter_by(id=req.id).first()
        assert fetched_req is not None
        assert fetched_req.status == "pending"

        fetched_action = db.session.query(ApprovalAction).filter_by(resource_id=mat.id).first()
        assert fetched_action.action == "approve"
        assert fetched_action.approver_id == user.id


def test_ai_chat_and_analytics_models(app):
    """Test ChatSession, ChatMessage, AICitation, EventLog, DailyMetric, ResourceView."""
    with app.app_context():
        inst = Institution(name="AI Lab", short_name="AIL", code="AIL-001", domain_whitelist=[])
        db.session.add(inst)
        db.session.flush()

        user = User(institution_id=inst.id, email="student@ail.edu", full_name="Student Scholar", password_hash="h", role="STUDENT", status="active")
        db.session.add(user)
        db.session.flush()

        mat = StudyMaterial(title="Quantum Physics Notes", author_id=user.id, material_type=MaterialType.NOTE)
        db.session.add(mat)
        db.session.flush()

        # ChatSession & Message & Citation
        chat = ChatSession(user_id=user.id, title="Quantum Computing Fundamentals")
        db.session.add(chat)
        db.session.flush()

        msg = ChatMessage(session_id=chat.id, sender_type="ai", content="Shor's algorithm solves discrete logarithms in polynomial time.")
        db.session.add(msg)
        db.session.flush()

        citation = AICitation(
            message_id=msg.id,
            study_material_id=mat.id,
            chunk_index=0,
            page_number=1,
            relevance_score=0.95,
            excerpt="Shor algorithm complexity is polynomial."
        )
        db.session.add(citation)
        db.session.flush()

        # Analytics: EventLog, DailyMetric, ResourceView
        ev = EventLog(event_type="resource.viewed", user_id=user.id, institution_id=inst.id, event_data={"resource_id": str(mat.id)})
        db.session.add(ev)

        dm = DailyMetric(metric_date="2026-10-27", metric_name="ai_queries_total", metric_value=42.0)
        db.session.add(dm)

        rv = ResourceView(resource_id=mat.id, user_id=user.id, institution_id=inst.id)
        db.session.add(rv)
        db.session.commit()

        fetched_chat = db.session.query(ChatSession).filter_by(id=chat.id).first()
        assert len(fetched_chat.messages) == 1
        assert len(fetched_chat.messages[0].citations) == 1

        fetched_dm = db.session.query(DailyMetric).filter_by(metric_name="ai_queries_total").first()
        assert fetched_dm.metric_value == 42.0


def test_audit_notification_and_contributions(app):
    """Test AuditLog, LoginHistory, NotificationTemplate, Notification, UserDevice, ContributionType, UserContribution, Leaderboard, Badge."""
    with app.app_context():
        inst = Institution(name="Audit Univ", short_name="AU", code="AU-001", domain_whitelist=[])
        db.session.add(inst)
        db.session.flush()

        user = User(institution_id=inst.id, email="auditor@au.edu", full_name="Security Auditor", password_hash="h", role="ADMIN", status="active")
        db.session.add(user)
        db.session.flush()

        # AuditLog & LoginHistory
        al = AuditLog(user_id=user.id, action="USER_ROLE_UPDATED", entity_type="USER", entity_id=str(user.id), ip_address="192.168.1.100")
        db.session.add(al)

        lh = LoginHistory(user_id=user.id, ip_address="192.168.1.100", user_agent="Mozilla/5.0", status="SUCCESS")
        db.session.add(lh)

        # Notification & Template
        nt = NotificationTemplate(name="MATERIAL_APPROVED", body_template="Your material has been reviewed.")
        db.session.add(nt)
        db.session.flush()

        notif = Notification(
            recipient_id=user.id,
            institution_id=inst.id,
            notification_type="resource.approved",
            title="Material Approved",
            message="Your lecture note is live.",
            is_read=False
        )
        db.session.add(notif)

        dev = UserDevice(user_id=user.id, device_token="fcm_token_12345", platform="android")
        db.session.add(dev)

        # Contribution, Leaderboard, Badge
        ct = ContributionType(name="UPLOAD_NOTE", description="Upload an approved study note", points=50)
        db.session.add(ct)
        db.session.flush()

        uc = UserContribution(user_id=user.id, action="resource_uploaded", institution_id=inst.id)
        db.session.add(uc)

        lb = Leaderboard(user_id=user.id, total_points=50, rank=1)
        db.session.add(lb)

        badge = Badge(name="Top Scholar", description="Top contributor of verified study material")
        db.session.add(badge)
        db.session.commit()

        # Verify
        assert db.session.query(AuditLog).filter_by(user_id=user.id).count() == 1
        assert db.session.query(LoginHistory).filter_by(user_id=user.id).count() == 1
        assert db.session.query(Notification).filter_by(recipient_id=user.id).count() == 1
        assert db.session.query(Leaderboard).filter_by(user_id=user.id).first().total_points == 50
        assert db.session.query(Badge).count() >= 1


def test_qr_search_bookmark_and_embedding_models(app):
    """Test QRCode, QRCodeScan, SearchQueryLog, SearchFilterLog, BookmarkFolder, Bookmark, EmbeddingModelConfig, ResourceChunk, ChunkEmbedding."""
    with app.app_context():
        inst = Institution(name="Search Inst", short_name="SI", code="SI-001", domain_whitelist=[])
        db.session.add(inst)
        db.session.flush()

        user = User(institution_id=inst.id, email="searcher@si.edu", full_name="Searcher User", password_hash="h", role="STUDENT", status="active")
        db.session.add(user)
        db.session.flush()

        mat = StudyMaterial(title="Database Management", author_id=user.id, material_type=MaterialType.NOTE)
        db.session.add(mat)
        db.session.flush()

        # QRCode & Scan
        qr = QRCode(entity_type="resource", entity_id=str(mat.id), code_data="https://campusx-portal.onrender.com/r/123")
        db.session.add(qr)
        db.session.flush()

        scan = QRCodeScan(qr_code_id=qr.id, user_id=user.id, location_data="Library Building 3")
        db.session.add(scan)

        # Search Query & Filter Log
        sq = SearchQueryLog(user_id=user.id, query_string="machine learning lecture notes", results_count=12)
        db.session.add(sq)
        db.session.flush()

        sf = SearchFilterLog(search_query_id=sq.id, filter_name="department", filter_value="CSE")
        db.session.add(sf)

        # Bookmark & Folder
        folder = BookmarkFolder(user_id=user.id, name="Algorithms Revision")
        db.session.add(folder)
        db.session.flush()

        bm = Bookmark(user_id=user.id, resource_id=mat.id, folder_id=folder.id)
        db.session.add(bm)

        # Embedding & Chunk
        emb_cfg = EmbeddingModelConfig(model_name="text-embedding-3-large", dimension=3072, is_active=True)
        db.session.add(emb_cfg)
        db.session.flush()

        chunk = ResourceChunk(resource_id=mat.id, chunk_index=0, content="Gradient descent minimizes the objective function.")
        db.session.add(chunk)
        db.session.flush()

        ce = ChunkEmbedding(chunk_id=chunk.id, model_id=emb_cfg.id, vector_id="vec-12345")
        db.session.add(ce)
        db.session.commit()

        # Assertions
        assert db.session.query(QRCode).count() == 1
        assert db.session.query(SearchQueryLog).count() == 1
        assert len(folder.bookmarks) == 1
        assert db.session.query(EmbeddingModelConfig).count() == 1
        assert db.session.query(ChunkEmbedding).count() == 1


def test_enrollment_and_soft_delete(app):
    """Test AcademicYear, StudentEnrollment, CourseEnrollment, InstructorAssignment, and soft delete behavior across models."""
    with app.app_context():
        inst = Institution(name="Enrollment Inst", short_name="EI", code="EI-001", domain_whitelist=[])
        db.session.add(inst)
        db.session.flush()

        user = User(institution_id=inst.id, email="enrolled@ei.edu", full_name="Enrolled Student", password_hash="h", role="STUDENT", status="active")
        db.session.add(user)

        instructor = User(institution_id=inst.id, email="instructor@ei.edu", full_name="Dr. Course Instructor", password_hash="h", role="FACULTY", status="active")
        db.session.add(instructor)
        db.session.flush()

        ay = AcademicYear(start_year=2026, end_year=2027, label="2026-2027")
        db.session.add(ay)
        db.session.flush()

        dept = Department(name="Information Technology", institution_id=inst.id)
        degree = Degree(name="B.Tech", level="UG")
        db.session.add_all([dept, degree])
        db.session.flush()

        prog = Program(name="IT Program", department_id=dept.id, degree_id=degree.id)
        db.session.add(prog)
        db.session.flush()

        session = AcademicSession(name="2026-2027", start_year=2026, end_year=2027)
        db.session.add(session)
        db.session.flush()

        sem = Semester(name="Sem 5", academic_session_id=session.id, number=5)
        db.session.add(sem)
        db.session.flush()

        subj = Subject(code="IT501", name="Cloud Computing Architecture", program_id=prog.id, semester_id=sem.id)
        db.session.add(subj)
        db.session.flush()

        # Student Enrollment
        se = StudentEnrollment(
            user_id=user.id,
            program_id=prog.id,
            academic_year_id=ay.id,
            institution_id=inst.id,
            status="active"
        )
        db.session.add(se)
        db.session.flush()

        # Course Enrollment
        ce = CourseEnrollment(student_id=user.id, course_id=subj.id, semester_id=sem.id, institution_id=inst.id, grade="A")
        db.session.add(ce)

        # Instructor Assignment
        ia = InstructorAssignment(instructor_id=instructor.id, course_id=subj.id, semester_id=sem.id, institution_id=inst.id, is_primary=True)
        db.session.add(ia)
        db.session.commit()

        # Test Soft Delete on BaseModel
        assert user.is_deleted is False
        assert user.deleted_at is None
        user.soft_delete()
        db.session.commit()

        reloaded_user = db.session.query(User).filter_by(id=user.id).first()
        assert reloaded_user.is_deleted is True
        assert reloaded_user.deleted_at is not None

        # Restore
        reloaded_user.restore()
        db.session.commit()
        restored_user = db.session.query(User).filter_by(id=user.id).first()
        assert restored_user.is_deleted is False
