from .base import BaseSchema, Schema, fields, validate, ValidationError

class CourseSchema(BaseSchema):
    code = fields.String(required=True)
    title = fields.String(required=True)
    credits = fields.Integer(required=True)
    department_id = fields.String(required=True)

class CourseCreateSchema(CourseSchema):
    pass

class CourseUpdateSchema(BaseSchema):
    title = fields.String()
    credits = fields.Integer()
    department_id = fields.String()

class GradeSchema(BaseSchema):
    student_id = fields.String(required=True)
    course_id = fields.String(required=True)
    grade = fields.String(required=True, validate=validate.OneOf(["A", "B", "C", "D", "F"]))
    semester = fields.String(required=True)
    
class GradeCreateSchema(GradeSchema):
    pass

SubjectSchema = CourseSchema
SubjectCreateSchema = CourseCreateSchema
SubjectUpdateSchema = CourseUpdateSchema
