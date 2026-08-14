from app.models import Institution, Department, Subject
from app.extensions import db

class AcademicService:
    def get_academic_hierarchy(self):
        institutions = db.session.query(Institution).all()
        hierarchy = []
        for inst in institutions:
            inst_data = {"id": inst.id, "name": inst.name, "departments": []}
            departments = db.session.query(Department).filter_by(institution_id=inst.id).all()
            for dept in departments:
                dept_data = {"id": dept.id, "name": dept.name, "subjects": []}
                subjects = db.session.query(Subject).filter_by(department_id=dept.id).all()
                for sub in subjects:
                    dept_data["subjects"].append({"id": sub.id, "name": sub.name, "code": sub.code})
                inst_data["departments"].append(dept_data)
            hierarchy.append(inst_data)
        return hierarchy

    def create_institution(self, name, **kwargs):
        inst = Institution(name=name, **kwargs)
        db.session.add(inst)
        db.session.commit()
        return inst

    def create_department(self, institution_id, name, **kwargs):
        dept = Department(institution_id=institution_id, name=name, **kwargs)
        db.session.add(dept)
        db.session.commit()
        return dept

    def create_subject(self, department_id, name, code, **kwargs):
        sub = Subject(department_id=department_id, name=name, code=code, **kwargs)
        db.session.add(sub)
        db.session.commit()
        return sub
