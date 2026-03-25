import os
os.environ["USE_TF"] = "0"
os.environ["USE_TORCH"] = "1"

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
import re
import json

from agents.design_check_agent import DesignCheckAgent
from memory_store import MemoryStore

# Windows console encoding fix
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

app = FastAPI(title="Design Check AI", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

_agent = None
memory_store = MemoryStore()

def get_agent():
    global _agent
    if _agent is None:
        api_key = os.getenv("DASHSCOPE_API_KEY", "")
        _agent = DesignCheckAgent(api_key=api_key)
    return _agent

@app.get("/")
async def serve_frontend():
    index_html = FRONTEND_DIR / "index.html"
    if index_html.exists():
        return FileResponse(str(index_html))
    return {"message": "Design Check AI backend is running"}

@app.get("/health")
async def health():
    return {"status": "ok", "service": "Design Check AI"}

@app.post("/chat")
async def unified_chat(
    file: Optional[UploadFile] = File(None),
    message: Optional[str] = Form(""),
    session_id: Optional[str] = Form(""),
    action_type: Optional[str] = Form(""), # e.g. "zoom"
    error_index: Optional[int] = Form(None)
):
    """
    Cổng API hợp nhất (Unified endpoint) thay thế cho /analyze, /chat và /zoom.
    Tự động route dựa trên payload gửi lên.
    """
    key = session_id.strip() if session_id else "anonymous"
    msg = message.strip() if message else ""
    action = action_type.strip().lower() if action_type else ""

    try:
        # -------------------------------------------------------------------
        # LUỒNG 1: ZOOM CỨNG TỪ NÚT BẤM GIAO DIỆN (UI BUTTON CLICK)
        # -------------------------------------------------------------------
        if action == "zoom" or error_index is not None:
            last = memory_store.get_last_analysis(key)
            if not last:
                raise HTTPException(status_code=404, detail="cần phân tích ảnh trước khi zoom.")
            image_bytes, last_result = last
            
            box = None
            if error_index is not None:
                errors = (last_result or {}).get("e", [])
                if 0 <= error_index < len(errors):
                    err = errors[error_index]
                    box = err.get("box_2d") or err.get("c")

            if not (isinstance(box, list) and len(box) == 4):
                raise HTTPException(status_code=400, detail="Lỗi tọa độ zoom.")
                
            x1, y1, x2, y2 = [int(v) for v in box]
            img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            pad = 40
            cx1, cy1 = max(0, min(x1, x2) - pad), max(0, min(y1, y2) - pad)
            cx2, cy2 = min(img.width, max(x1, x2) + pad), min(img.height, max(y1, y2) + pad)
            crop = img.crop((cx1, cy1, cx2, cy2))
            
            draw = ImageDraw.Draw(crop)
            rx1, ry1 = max(0, min(x1, x2) - cx1), max(0, min(y1, y2) - cy1)
            rx2, ry2 = min(crop.width, max(x1, x2) - cx1), min(crop.height, max(y1, y2) - cy1)
            draw.rectangle([rx1, ry1, rx2, ry2], outline=(255, 77, 109), width=4)
            
            buf = io.BytesIO()
            crop.save(buf, format="PNG")
            b64 = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("utf-8")
            
            return {
                "type": "zoom",
                "reply": "Đây là vùng ảnh bị lỗi chi tiết:",
                "image_data_url": b64
            }

        # -------------------------------------------------------------------
        # LUỒNG 2: NGƯỜI DÙNG CÓ UP ẢNH (PHÂN TÍCH NHƯ /ANALYZE CŨ)
        # -------------------------------------------------------------------
        if file is not None and file.filename:
            image_bytes = await file.read()
            if len(image_bytes) == 0:
                raise HTTPException(status_code=400, detail="File ảnh rỗng.")
            agent = get_agent()
            
            # Sử dụng mạch query cũ nếu có để bối cảnh không bị đứt đoạn
            provided_query = msg.strip()
            used_query = provided_query if provided_query else (memory_store.get_last_query(key) or "graphic design poster advertisement typography color layout")
            
            recent_queries = memory_store.get_recent_queries(key, limit=3)
            if recent_queries and recent_queries[-1] == used_query:
                recent_queries = recent_queries[:-1]
            effective_query = " / ".join(recent_queries + [used_query]).strip()
            
            # Gộp ngữ cảnh chat cũ
            turns = memory_store.get_recent_turns(key, limit=6)
            history_messages = [{"role": r, "content": [{"text": t}]} for r, t in turns]
            
            result = agent.analyze(
                image_bytes=image_bytes,
                filename=file.filename,
                query=effective_query,
                history_messages=history_messages
            )
            
            # Lưu lịch sử Query và Kết quả
            memory_store.add_query(key, used_query)
            memory_store.set_last_analysis(key, image_bytes, result)
            memory_store.add_turn(key, "user", f"[Upload Ảnh] {used_query}")
            
            # Lưu file JSON Report ra máy tính
            try:
                out_path = Path(__file__).parent / "latest_result.json"
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(result, f, ensure_ascii=False, indent=4)
                print(f"[Backend] Đã xuất file báo cáo JSON ra: {out_path}")
            except Exception as e:
                print(f"[Backend] Lỗi khi lưu file JSON: {e}")
            
            # Nhét toàn bộ danh sách lỗi 'e' vào RAM để Chatbot 'nhớ' được vị trí và nội dung lỗi
            assistant_text = json.dumps(
                {
                    "q": effective_query,
                    "te": result.get("te"),
                    "ss": result.get("ss"),
                    "e": result.get("e", []),
                },
                ensure_ascii=False,
            )
            memory_store.add_turn(key, "assistant", f"Phân tích hoàn tất: {assistant_text}")
            
            return {
                "type": "analysis",
                "reply": "Tôi đã quét xong bản thiết kế này. Dưới đây là thẻ kết quả chi tiết:",
                "has_analysis": True,
                "analysis_data": result,
                "usage": {
                    "input_tokens": result.get("inputtoken", 0),
                    "output_tokens": result.get("outputtoken", 0),
                    "total_tokens": result.get("totaltoken", 0)
                }
            }

        # -------------------------------------------------------------------
        # LUỒNG 3: NGƯỜI DÙNG CHỈ GÕ CHỮ (CHAT THUẦN TÚY) & AUTO ZOOM
        # -------------------------------------------------------------------
        if not msg:
            raise HTTPException(status_code=400, detail="Mời nhập tin nhắn hoặc tải ảnh lên.")
            
        turns = memory_store.get_recent_turns(key, limit=10)
        history_messages = [{"role": r, "content": [{"text": t}]} for r, t in turns]
        agent = get_agent()
        
        payload = agent.qwen_agent.chat_json(
            system_prompt=(
                "You are an expert graphic design assistant.\n"
                "Answer in Vietnamese politely.\n"
                "RETURN STRICT JSON ONLY:\n"
                "{\n"
                '  "reply": "text answer here",\n'
                '  "zoom_command": null | {"type": "box_2d", "box_2d": [x1,y1,x2,y2]}\n'
                "}\n"
                "If user asks to zoom/phóng to an error, set zoom_command.\n"
            ),
            user_text=msg,
            history_messages=history_messages
        )
        reply = str(payload.get("reply", "")).strip()
        zcmd = payload.get("zoom_command")
        
        # Xử lý Smart Auto-Zoom
        freeform_zoom = any(k in msg.lower() for k in ["phóng to", "zoom", "cắt", "lỗi số"])
        if freeform_zoom or zcmd:
            last = memory_store.get_last_analysis(key)
            if last:
                ctx_str = None
                if last[1] and isinstance(last[1], dict):
                    errs = last[1].get("e", [])
                    if errs:
                        ctx_str = json.dumps([{"i": i, "c": e.get("c"), "r": e.get("r")} for i, e in enumerate(errs[:5])], ensure_ascii=False)
                        
                loc = agent.qwen_agent.locate_box(image_bytes=last[0], mime_type="image/jpeg", user_request=msg, context=ctx_str)
                box = loc.get("box_2d")
                if isinstance(box, list) and len(box) == 4:
                    img = Image.open(io.BytesIO(last[0])).convert("RGB")
                    pad = 40
                    cx1, cy1 = max(0, box[0]-pad), max(0, box[1]-pad)
                    cx2, cy2 = min(img.width, box[2]+pad), min(img.height, box[3]+pad)
                    crop = img.crop((cx1, cy1, cx2, cy2))
                    draw = ImageDraw.Draw(crop)
                    draw.rectangle([box[0]-cx1, box[1]-cy1, box[2]-cx1, box[3]-cy1], outline=(255, 77, 109), width=4)
                    
                    buf = io.BytesIO()
                    crop.save(buf, format="PNG")
                    b64 = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("utf-8")
                    
                    memory_store.add_turn(key, "user", msg)
                    memory_store.add_turn(key, "assistant", reply)
                    loc_usage = loc.get("_usage", {})
                    pay_usage = payload.get("_usage", {})
                    return {
                        "type": "zoom",
                        "reply": reply,
                        "image_data_url": b64,
                        "usage": {
                            "input_tokens": loc_usage.get("input_tokens", pay_usage.get("input_tokens", 0)),
                            "output_tokens": loc_usage.get("output_tokens", pay_usage.get("output_tokens", 0)),
                            "total_tokens": loc_usage.get("total_tokens", pay_usage.get("total_tokens", 0))
                        }
                    }
                    
        memory_store.add_turn(key, "user", msg)
        memory_store.add_turn(key, "assistant", reply)
        pay_usage = payload.get("_usage", {})
        return {
            "type": "chat",
            "reply": reply,
            "usage": {
                "input_tokens": pay_usage.get("input_tokens", 0),
                "output_tokens": pay_usage.get("output_tokens", 0),
                "total_tokens": pay_usage.get("total_tokens", 0)
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
