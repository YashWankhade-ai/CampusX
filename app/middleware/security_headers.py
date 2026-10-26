import os

def security_headers(response):
    """Add standard security headers to the response with Hugging Face & Vercel compatibility."""
    response.headers["X-Content-Type-Options"] = "nosniff"
    
    # Allow Hugging Face iframe embedding when running in HF Spaces
    if os.environ.get("SPACE_ID") or os.environ.get("HF_SPACE"):
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self' https: data: 'unsafe-inline' 'unsafe-eval'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https:; "
            "style-src 'self' 'unsafe-inline' https:; "
            "img-src 'self' data: https:; "
            "font-src 'self' https: data:; "
            "connect-src 'self' https: wss:; "
            "frame-ancestors 'self' https://huggingface.co https://*.hf.space https://*.vercel.app https://*.onrender.com https://render.com;"
        )
    else:
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self' https: data: 'unsafe-inline' 'unsafe-eval'; "
            "script-src 'self' 'unsafe-inline' https:; "
            "style-src 'self' 'unsafe-inline' https:; "
            "img-src 'self' data: https:; "
            "font-src 'self' https: data:; "
            "connect-src 'self' https:; "
            "frame-ancestors 'self' https://*.vercel.app https://*.onrender.com https://huggingface.co https://*.hf.space;"
        )

    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response
