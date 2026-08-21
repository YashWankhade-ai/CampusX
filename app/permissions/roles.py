class Role:
    SUPER_ADMIN = "SUPER_ADMIN"
    INSTITUTION_ADMIN = "INSTITUTION_ADMIN"
    MODERATOR = "MODERATOR"
    FACULTY = "FACULTY"
    STUDENT = "STUDENT"
    GUEST = "GUEST"

ROLE_HIERARCHY = [
    Role.GUEST,
    Role.STUDENT,
    Role.FACULTY,
    Role.MODERATOR,
    Role.INSTITUTION_ADMIN,
    Role.SUPER_ADMIN
]

def get_role_level(role: str) -> int:
    """Return integer level of role, -1 if unknown."""
    try:
        return ROLE_HIERARCHY.index(role)
    except ValueError:
        return -1
