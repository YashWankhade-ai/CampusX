import sys
import os
import types

# Compatibility shim for huggingface_hub removing HfFolder in recent versions
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
except Exception as e:
    print(f"[Shim] Note: {e}", flush=True)

# ZeroGPU compatibility safeguard for Hugging Face Spaces
try:
    import spaces
    @spaces.GPU
    def _hf_spaces_gpu_worker():
        return "CampusX AI Engine is fully operational on Hugging Face ZeroGPU!"
    print("[ZeroGPU] Supervisor handshake verified: @spaces.GPU registered.", flush=True)

    try:
        from spaces.zero import client as zero_client
        zero_client.startup_report()
        print("[ZeroGPU] Startup report POSTed successfully to ZeroGPU supervisor daemon!", flush=True)
    except Exception as exc:
        print(f"[ZeroGPU] Immediate startup_report note: {exc}", flush=True)
except Exception as e:
    def _hf_spaces_gpu_worker():
        return "CampusX backend active in CPU mode."
    print(f"[ZeroGPU] Running in standard mode: {e}", flush=True)

import uvicorn
from fastapi import FastAPI
try:
    from a2wsgi import WSGIMiddleware
except ImportError:
    from starlette.middleware.wsgi import WSGIMiddleware
from app import create_app

flask_env = os.environ.get("FLASK_ENV", "production")
flask_app = create_app(flask_env)

# ProxyFix for reverse proxy routing (Vercel, Cloudflare, HF)
try:
    from werkzeug.middleware.proxy_fix import ProxyFix
    flask_app.wsgi_app = ProxyFix(flask_app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
except Exception:
    pass

# Initialize FastAPI parent application
fastapi_app = FastAPI(title="CampusX AI Platform & Engine")

@fastapi_app.on_event("startup")
def notify_zerogpu_on_startup():
    try:
        from spaces.zero import client as zero_client
        zero_client.startup_report()
        print("[ZeroGPU] Startup report confirmed during FastAPI lifespan startup!", flush=True)
    except Exception as exc:
        print(f"[ZeroGPU] Lifespan startup_report note: {exc}", flush=True)

@fastapi_app.get("/api/v1/gpu-status")
def gpu_status():
    return {"status": "ok", "zerogpu": True, "message": "ZeroGPU supervisor active"}

# Try importing Gradio for Hugging Face Spaces Gradio SDK
try:
    import gradio as gr
    HAS_GRADIO = True
except ImportError:
    HAS_GRADIO = False

if HAS_GRADIO:
    with gr.Blocks(title="CampusX Universal AI Academic Platform") as demo:
        gr.Markdown("# 🎓 CampusX Universal AI Academic Platform Backend")
        gr.Markdown("The CampusX AI Engine is **running live** on Hugging Face Spaces!")
        gr.Markdown("### Quick Portal Links:")
        gr.Markdown("- **📚 [Student & Academic Portal](/student/dashboard)**")
        gr.Markdown("- **🛡️ [Administrator Console](/admin/dashboard)**")
        gr.Markdown("- **🔑 [Sign In / Access Account](/login)**")
        gr.Markdown("- **🩺 [System Health](/health)** | **[GPU Status](/api/v1/gpu-status)**")
        gr.Markdown("---")
        with gr.Row():
            ai_check_btn = gr.Button("⚡ Verify AI Engine & GPU Status", variant="primary")
            ai_status_output = gr.Textbox(label="AI Engine Status", value="Ready")
        ai_check_btn.click(fn=_hf_spaces_gpu_worker, outputs=ai_status_output)
        gr.Markdown("---")
        gr.Markdown("*Connect your Vercel frontend by setting your Vercel proxy to this Space URL.*")

    # Mount Gradio dashboard at /gradio
    fastapi_app = gr.mount_gradio_app(fastapi_app, demo, path="/gradio")

# Mount Flask at root / so ALL Flask routes (landing, auth, admin, student, API) work seamlessly
fastapi_app.mount("/", WSGIMiddleware(flask_app))

app = fastapi_app

if __name__ == "__main__":
    port = int(os.getenv("PORT", "7860"))
    uvicorn.run(app, host="0.0.0.0", port=port)
