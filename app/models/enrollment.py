import uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, ForeignKey, Boolean
from app.models.base import BaseModel

class AcademicYear(BaseModel):
    __tablename__ = "academic_years"
    start_year: Mapped[int] = mapped_column()
    end_year: Mapped[int] = mapped_column()

class StudentEnrollment(BaseModel):
    __tablename__ = "student_enrollments"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    program_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("programs.id"))
    academic_year_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("academic_years.id"))
    status: Mapped[str] = mapped_column(String(50)) # active, graduated, suspended

class CourseEnrollment(BaseModel):
    __tablename__ = "course_enrollments"
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("subjects.id"))
    semester_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("semesters.id"))
    grade: Mapped[str | None] = mapped_column(String(5), nullable=True)

class InstructorAssignment(BaseModel):
    __tablename__ = "instructor_assignments"
    instructor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("subjects.id"))
    semester_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("semesters.id"))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True)
