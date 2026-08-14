from sqlalchemy import select
from typing import List, Dict, Any
from app.repositories.base_repository import BaseRepository
from app.models.academic import Institution, Department, Program, Subject, Semester
import uuid

class AcademicRepository(BaseRepository[Institution]):
    def __init__(self, db_session=None):
        super().__init__(model_class=Institution, db_session=db_session)


    async def get_hierarchy(self, institution_id: uuid.UUID) -> Dict[str, Any]:
        inst_stmt = select(Institution).where(Institution.id == institution_id, Institution.is_deleted == False)
        inst_res = await self.db.execute(inst_stmt)
        inst = inst_res.scalar_one_or_none()
        if not inst:
            return {}
        
        dept_stmt = select(Department).where(Department.institution_id == institution_id, Department.is_deleted == False)
        dept_res = await self.db.execute(dept_stmt)
        depts = dept_res.scalars().all()
        
        return {
            "institution": inst,
            "departments": depts
        }

    async def find_subjects_by_semester(self, semester_id: uuid.UUID) -> List[Subject]:
        stmt = select(Subject).where(Subject.semester_id == semester_id, Subject.is_deleted == False)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
