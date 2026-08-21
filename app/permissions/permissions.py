from .roles import Role

# Architecture-approved roles:
# SUPER_ADMIN — platform-level, cross-institution
# INSTITUTION_ADMIN — institution-level admin
# FACULTY — content contributor
# STUDENT — content consumer
# MODERATOR — content reviewer/approver
# GUEST — unauthenticated or unverified

ROLE_PERMISSIONS = {
    Role.SUPER_ADMIN: [
        'resources:read', 'resources:write', 'resources:delete', 'resources:approve',
        'users:read', 'users:write', 'users:delete', 'users:manage',
        'ai:use', 'ai:configure',
        'search:use',
        'analytics:read', 'analytics:export',
        'institutions:read', 'institutions:manage',
        'settings:read', 'settings:manage'
    ],
    Role.INSTITUTION_ADMIN: [
        'resources:read', 'resources:write', 'resources:delete', 'resources:approve',
        'users:read', 'users:write', 'users:delete', 'users:manage',
        'ai:use', 'ai:configure',
        'search:use',
        'analytics:read', 'analytics:export',
        'institutions:read',
        'settings:read', 'settings:manage'
    ],
    Role.MODERATOR: [
        'resources:read', 'resources:write', 'resources:approve',
        'users:read',
        'ai:use',
        'search:use',
        'analytics:read',
        'settings:read'
    ],
    Role.FACULTY: [
        'resources:read', 'resources:write',
        'users:read',
        'ai:use',
        'search:use',
        'analytics:read',
        'settings:read'
    ],
    Role.STUDENT: [
        'resources:read',
        'users:read',
        'ai:use',
        'search:use',
        'settings:read'
    ],
    Role.GUEST: [
        'search:use'
    ]
}
