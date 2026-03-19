"""
FastAPI backend server cho Design Check AI System.
"""
import os
import io
import sys
from typing import Optional
from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from pathlib import Path
from PIL import Image, ImageDraw
import base64
import io
import re

from agents.design_check_agent import DesignCheckAgent
from memory_store import MemoryStore
import json

# -----------------------------------------------------------------------
# Windows console encoding fix (avoid 'charmap' codec errors)
# -----------------------------------------------------------------------
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    # If reconfigure isn't supported, just ignore.
    pass

# -----------------------------------------------------------------------
# App setup
# -----------------------------------------------------------------------
app = FastAPI(
    title="Design Check AI",
    description="He thong AI kiem tra loi thiet ke 2D bang RAG + Qwen VL",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount frontend static files
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

# -----------------------------------------------------------------------
# Lazy-load agent
# -----------------------------------------------------------------------
_agent = None
memory_store = MemoryStore()

def get_agent():
    global _agent
    if _agent is None:
        api_key = os.getenv("DASHSCOPE_API_KEY", "")
        _agent = DesignCheckAgent(api_key=api_key)
    return _agent


# -----------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------
@app.get("/")
async def serve_frontend():
    index_html = FRONTEND_DIR / "index.html"
    if index_html.exists():
        return FileResponse(str(index_html))
    return {"message": "Design Check AI backend is running", "docs": "/docs"}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "Design Check AI"}


# -----------------------------------------------------------------------
# Chat schema + endpoint
# -----------------------------------------------------------------------
class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    user_id: Optional[str] = None


@app.post("/chat")
async def chat(req: ChatRequest):
    """
    Text-only chat endpoint. Uses session memory to keep context.
    """
    key = (req.session_id or req.user_id or "anonymous").strip()
    msg = (req.message or "").strip()
    if not msg:
        raise HTTPException(status_code=400, detail="message rong.")

    try:
        turns = memory_store.get_recent_turns(key, limit=10)
        history_messages = [{"role": role, "content": [{"text": text}]} for role, text in turns]

        agent = get_agent()
        payload = agent.qwen_agent.chat_json(
            system_prompt=(
                "You are a helpful assistant for Design Check AI.\n"
                "Answer in Vietnamese by default.\n"
                "Return ONLY valid JSON (no markdown, no extra text) with this schema:\n"
                "{\n"
                '  "reply": "<text>",\n'
                '  "zoom_command": null | {\n'
                '    "type": "error_index" | "box_2d",\n'
                '    "error_index": <int, 0-based> ,\n'
                '    "box_2d": [x1,y1,x2,y2],\n'
                '    "padding": <int>\n'
                "  }\n"
                "}\n"
                "Rules:\n"
                "- If the user asks to zoom/enlarge a region or a specific error, set zoom_command.\n"
                "- Prefer type=error_index when the user references 'lỗi số N'.\n"
                "- If there is no last analyzed image in this session, set zoom_command=null.\n"
            ),
            user_text=msg,
            history_messages=history_messages,
        )

        reply = str(payload.get("reply", "")).strip()
        zoom_command = payload.get("zoom_command", None)

        # If model suggests zoom by box_2d (or user asks zoom in free-form),
        # use vision on the last analyzed image to get a more accurate box.
        wants_zoom = isinstance(zoom_command, dict) and zoom_command.get("type") in {"box_2d", "error_index"}
        freeform_zoom = any(k in msg.lower() for k in ["phóng to", "phong to", "zoom", "phóng lớn", "phong lon", "phóng to lên"])
        has_error_number = bool(re.search(r"(?:lỗi|error)\s*(?:số)?\s*\d+", msg, flags=re.I))
        if (wants_zoom or freeform_zoom) and not has_error_number:
            last = memory_store.get_last_analysis(key)
            if last:
                image_bytes, last_result = last
                # Provide brief context of errors to help localization.
                errors = (last_result or {}).get("e", [])
                ctx = ""
                if isinstance(errors, list) and errors:
                    top = errors[:5]
                    ctx = json.dumps(
                        [{"i": i, "c": e.get("c"), "r": e.get("r")} for i, e in enumerate(top)],
                        ensure_ascii=False,
                    )

                loc = agent.qwen_agent.locate_box(
                    image_bytes=image_bytes,
                    mime_type="image/jpeg",
                    user_request=msg,
                    context=ctx or None,
                )
                box = loc.get("box_2d")
                if isinstance(box, list) and len(box) == 4:
                    zoom_command = {
                        "type": "box_2d",
                        "box_2d": [int(v) for v in box],
                        "padding": int((zoom_command or {}).get("padding", 60) or 60),
                    }

        memory_store.add_turn(key, "user", msg)
        memory_store.add_turn(key, "assistant", reply or json.dumps(payload, ensure_ascii=False))
        return {"reply": reply, "zoom_command": zoom_command}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")


class ZoomRequest(BaseModel):
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    error_index: Optional[int] = None  # 0-based index in errors list
    box_2d: Optional[list] = None      # [x1,y1,x2,y2]
    padding: int = 40                  # pixels around box
    max_size: int = 900                # max output width/height


@app.post("/zoom")
async def zoom(req: ZoomRequest):
    """
    Crop/zoom the last analyzed image by an error box (no re-upload needed).
    Returns base64 PNG data URL + the box used.
    """
    key = (req.session_id or req.user_id or "anonymous").strip()
    last = memory_store.get_last_analysis(key)
    if not last:
        raise HTTPException(status_code=404, detail="Chua co ket qua analyze cho session nay.")
    image_bytes, result = last

    errors = result.get("e", []) if isinstance(result, dict) else []
    box = None
    if req.error_index is not None:
        idx = int(req.error_index)
        if idx < 0 or idx >= len(errors):
            raise HTTPException(status_code=400, detail="error_index khong hop le.")
        box = errors[idx].get("box_2d")
    elif req.box_2d is not None:
        box = req.box_2d

    if not (isinstance(box, list) and len(box) == 4):
        raise HTTPException(status_code=400, detail="Khong co box_2d hop le de zoom.")

    try:
        x1, y1, x2, y2 = [int(v) for v in box]
    except Exception:
        raise HTTPException(status_code=400, detail="box_2d phai la 4 so nguyen.")

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    w, h = img.size
    pad = max(0, int(req.padding))

    cx1 = max(0, min(x1, x2) - pad)
    cy1 = max(0, min(y1, y2) - pad)
    cx2 = min(w, max(x1, x2) + pad)
    cy2 = min(h, max(y1, y2) + pad)

    crop = img.crop((cx1, cy1, cx2, cy2))

    # Draw bounding box relative to crop
    draw = ImageDraw.Draw(crop)
    rx1, ry1 = max(0, min(x1, x2) - cx1), max(0, min(y1, y2) - cy1)
    rx2, ry2 = min(crop.size[0], max(x1, x2) - cx1), min(crop.size[1], max(y1, y2) - cy1)
    draw.rectangle([rx1, ry1, rx2, ry2], outline=(255, 77, 109), width=4)

    # Resize to max_size
    max_size = max(200, int(req.max_size))
    cw, ch = crop.size
    scale = min(1.0, max_size / max(cw, ch))
    if scale < 1.0:
        crop = crop.resize((int(cw * scale), int(ch * scale)))

    buf = io.BytesIO()
    crop.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return {
        "image_data_url": f"data:image/png;base64,{b64}",
        "box_2d": [int(min(x1, x2)), int(min(y1, y2)), int(max(x1, x2)), int(max(y1, y2))],
        "crop_box": [int(cx1), int(cy1), int(cx2), int(cy2)],
    }


@app.post("/analyze")
async def analyze_design(
    file: UploadFile = File(...),
    query: Optional[str] = Form(default=None),
    user_id: Optional[str] = Form(default=None),
    session_id: Optional[str] = Form(default=None),
):
    """
    Nhan anh thiet ke va tra ve danh sach loi + bounding boxes.
    """
    allowed_types = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
    content_type = file.content_type or ""
    if content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {content_type}. Chi ho tro JPEG, PNG, WEBP."
        )

    image_bytes = await file.read()
    if len(image_bytes) == 0:
        raise HTTPException(status_code=400, detail="File rong.")
    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File qua lon (max 10MB).")

    try:
        key = (session_id or user_id or "anonymous").strip()
        provided_query = (query or "").strip()

        # If user doesn't provide query, fallback to last stored query.
        used_query = (
            provided_query
            if provided_query
            else (memory_store.get_last_query(key) or "graphic design poster advertisement")
        )

        # Mix a little recent context to keep retrieval consistent across "ask again".
        recent_queries = memory_store.get_recent_queries(key, limit=3)
        if recent_queries and recent_queries[-1] == used_query:
            recent_queries = recent_queries[:-1]
        effective_query = " / ".join(recent_queries + [used_query]).strip()

        # Build LLM chat history (text-only) for the session.
        # Keep it short to avoid prompt bloat.
        turns = memory_store.get_recent_turns(key, limit=6)
        history_messages = []
        for role, text in turns:
            history_messages.append({"role": role, "content": [{"text": text}]})

        agent = get_agent()
        result = agent.analyze(
            image_bytes=image_bytes,
            filename=file.filename or "image.jpg",
            query=effective_query,
            history_messages=history_messages,
        )

        # Store the query actually used for this request.
        memory_store.add_query(key, used_query)
        # Store latest image+result for zoom/follow-up (no re-upload).
        memory_store.set_last_analysis(key, image_bytes, result)
        # Store conversation turn for LLM to reuse next time.
        memory_store.add_turn(key, "user", used_query)
        # Store a compact assistant summary (useful for consistency).
        assistant_text = json.dumps(
            {
                "q": effective_query,
                "te": result.get("te"),
                "ss": result.get("ss"),
                "e": result.get("e", []),
            },
            ensure_ascii=False,
        )
        memory_store.add_turn(key, "assistant", assistant_text)
        return result
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
