"""Hugging Face Spaces & ZeroGPU Master Entrypoint for CampusX.

Provides:
1. ZeroGPU supervisor handshakes and @spaces.GPU acceleration.
2. HfFolder backwards-compatibility shim for huggingface_hub.
3. Production web serving bound to port 7860 for Hugging Face Spaces.
4. Full CampusX Web UI, REST API (/api/v1), and interactive health probes.
"""
import os
import sys
import types
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("campusx.zerogpu")

# 1. Compatibility Shim: Restore HfFolder if missing in huggingface_hub >= 1.0.0
try:
    import huggingface_hub
    if not hasattr(huggingface_hub, "HfFolder"):
        class HfFolder:
            @staticmethod
            def get_token():
                return getattr(huggingface_hub, "get_token", lambda: None)()

            @staticmethod
            def save_token(token):
                return getattr(huggingface_hub, "login", lambda token: None)(token)

        huggingface_hub.HfFolder = HfFolder
        if "huggingface_hub.hf_folder" not in sys.modules:
            hf_folder_mod = types.ModuleType("huggingface_hub.hf_folder")
            hf_folder_mod.HfFolder = HfFolder
            sys.modules["huggingface_hub.hf_folder"] = hf_folder_mod
        logger.info("[Shim] Restored huggingface_hub.HfFolder compatibility shim")
except Exception as e:
    logger.debug("[Shim] Notice: %s", e)

# 2. ZeroGPU Supervisor Handshake
HAS_ZEROGPU = False
try:
    import spaces  # type: ignore

    @spaces.GPU
    def _hf_spaces_gpu_worker():
        """Dummy worker to register @spaces.GPU during container boot."""
        return "ZeroGPU Supervisor Online"

    from spaces.zero import client as zero_client  # type: ignore
    zero_client.startup_report()
    HAS_ZEROGPU = True
    logger.info("[ZeroGPU] Supervisor handshake verified and startup_report sent.")
except Exception as e:
    logger.info("[ZeroGPU] Running in CPU / standard mode (%s)", e)

# 3. Create CampusX Application
from app import create_app

flask_env = os.environ.get("FLASK_ENV", "production")
flask_app = create_app(flask_env)

# Configure ProxyFix for Hugging Face and Vercel reverse proxy routing
try:
    from werkzeug.middleware.proxy_fix import ProxyFix
    flask_app.wsgi_app = ProxyFix(flask_app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
except Exception:
    pass

class VercelPathFix:
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        matched = environ.get('HTTP_X_MATCHED_PATH') or environ.get('HTTP_X_INVOKE_PATH')
        raw = environ.get('PATH_INFO', '')
        if matched and matched != raw:
            environ['PATH_INFO'] = matched
        elif raw in ('/api/index', '/api/index/'):
            environ['PATH_INFO'] = '/'
        return self.wsgi_app(environ, start_response)

flask_app.wsgi_app = VercelPathFix(flask_app.wsgi_app)

# ZeroGPU status probe endpoint
@flask_app.route("/api/v1/gpu-status", methods=["GET"])
def gpu_status():
    from flask import jsonify
    return jsonify({
        "status": "ok",
        "zerogpu": HAS_ZEROGPU,
        "platform": "Hugging Face Spaces" if (os.environ.get("SPACE_ID") or os.environ.get("HF_SPACE")) else "Local / Cloud",
        "service": "CampusX AI Engine"
    }), 200

# 4. Optional Gradio Dual-Interface Mounting
app = flask_app
try:
    import gradio as gr
    from a2wsgi import WSGIMiddleware
    import uvicorn

    with gr.Blocks(title="CampusX AI Platform") as demo:
        gr.Markdown(
            "# 🎓 CampusX AI Platform & Knowledge Base\n"
            "CampusX is running live on **Hugging Face Spaces** "
            f"({'⚡ ZeroGPU Accelerated' if HAS_ZEROGPU else '🖥️ CPU Mode'}).\n\n"
            "### 🔗 Direct Portal Access:\n"
            "- 📚 **[Open Student & Academic Portal](/student/dashboard)**\n"
            "- 🛡️ **[Open Administrator Console](/admin/dashboard)**\n"
            "- 🔑 **[Sign In / Access Account](/login)**\n"
            "- 🔍 **[Interactive Search](/student/search)**\n"
            "- 🤖 **[AI Study Assistant](/student/ai-chat)**\n"
            "- 🩺 **[Liveness Probe](/health)** | **[Readiness Probe](/health/ready)** | **[GPU Status](/api/v1/gpu-status)**"
        )

    # Wrap WSGI Flask app to ASGI for Gradio mounting if running under ASGI
    asgi_app = WSGIMiddleware(flask_app)
    app = gr.mount_gradio_app(asgi_app, demo, path="/gradio")
    logger.info("[Gradio] Gradio status interface mounted at /gradio")
except Exception as e:
    logger.info("[Gradio] Serving native CampusX WSGI application: %s", e)
    app = flask_app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    logger.info(f"Starting CampusX server on 0.0.0.0:{port} (Hugging Face ZeroGPU Ready)...")
    try:
        # If ASGI app was created with Gradio
        if "uvicorn" in sys.modules and app is not flask_app:
            uvicorn.run(app, host="0.0.0.0", port=port)
        else:
            flask_app.run(host="0.0.0.0", port=port)
    except Exception as exc:
        logger.warning(f"Falling back to native server: {exc}")
        flask_app.run(host="0.0.0.0", port=port)
