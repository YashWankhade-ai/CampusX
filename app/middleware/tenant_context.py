from flask import request, g

def tenant_context():
    """Extract tenant information from request headers and set in global context."""
    tenant_id = request.headers.get("X-Tenant-ID")
    if tenant_id:
        g.tenant_id = tenant_id
    else:
        g.tenant_id = "default"
