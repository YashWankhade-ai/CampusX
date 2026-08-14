class Permissions:
    # Users
    CREATE_USER = "create_user"
    READ_USER = "read_user"
    UPDATE_USER = "update_user"
    DELETE_USER = "delete_user"
    
    # Academic
    MANAGE_COURSES = "manage_courses"
    VIEW_COURSES = "view_courses"
    MANAGE_GRADES = "manage_grades"
    VIEW_GRADES = "view_grades"
    
    # Library
    MANAGE_BOOKS = "manage_books"
    BORROW_BOOKS = "borrow_books"
    
    # System
    MANAGE_SYSTEM = "manage_system"

ROLE_PERMISSIONS = {
    "SUPER_ADMIN": [
        Permissions.CREATE_USER, Permissions.READ_USER, Permissions.UPDATE_USER, Permissions.DELETE_USER,
        Permissions.MANAGE_COURSES, Permissions.VIEW_COURSES, Permissions.MANAGE_GRADES, Permissions.VIEW_GRADES,
        Permissions.MANAGE_BOOKS, Permissions.BORROW_BOOKS, Permissions.MANAGE_SYSTEM
    ],
    "ADMIN": [
        Permissions.CREATE_USER, Permissions.READ_USER, Permissions.UPDATE_USER, Permissions.DELETE_USER,
        Permissions.MANAGE_COURSES, Permissions.VIEW_COURSES, Permissions.MANAGE_BOOKS
    ],
    "FACULTY": [
        Permissions.READ_USER,
        Permissions.VIEW_COURSES, Permissions.MANAGE_GRADES, Permissions.VIEW_GRADES,
        Permissions.BORROW_BOOKS
    ],
    "DEPARTMENT_COORDINATOR": [
        Permissions.READ_USER,
        Permissions.MANAGE_COURSES, Permissions.VIEW_COURSES,
        Permissions.BORROW_BOOKS
    ],
    "LIBRARIAN": [
        Permissions.READ_USER,
        Permissions.MANAGE_BOOKS, Permissions.BORROW_BOOKS
    ],
    "STUDENT": [
        Permissions.READ_USER,
        Permissions.VIEW_COURSES, Permissions.VIEW_GRADES,
        Permissions.BORROW_BOOKS
    ]
}
