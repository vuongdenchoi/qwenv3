# Design Check AI – Hệ thống kiểm tra lỗi thiết kế 2D

Hệ thống AI phát hiện lỗi trong bản thiết kế 2D sử dụng **RAG + Qwen Multimodal Vision**.

## Kiến trúc

```
User Upload Image
      │
      ▼
DesignCheckAgent (Orchestrator)
      │
      ├─► RetrievalAgent  → FAISS Vector DB → Top-5 Design Rules
      ├─► PromptAgent     → Multimodal Prompt
      ├─► QwenAgent       → Qwen VL API → JSON errors  
      └─► PostProcessAgent→ Validate + Render
                                  │
                              Frontend HTML
                         (bounding box overlay)
```

## Cấu trúc thư mục

```
qwen3v/
├── design_rules/          # Knowledge base (markdown)
│   ├── typography.md
│   ├── color_theory.md
│   ├── layout_rules.md
│   ├── poster_design.md
│   └── logo_design.md
├── backend/
│   ├── main.py            # FastAPI server
│   ├── requirements.txt
│   ├── agents/
│   │   ├── design_check_agent.py   # Orchestrator
│   │   ├── retrieval_agent.py      # FAISS search
│   │   ├── prompt_agent.py         # Prompt builder
│   │   ├── qwen_agent.py           # Qwen VL API
│   │   └── post_process_agent.py   # Validate + clean
│   └── knowledge_base/
│       └── build_index.py          # Build FAISS index (run once)
├── frontend/
│   └── index.html         # Web UI
└── run.py                 # Unified runner script
```

## Cách chạy

### Bước 0: Set API Key

```bash
# Windows PowerShell
$env:DASHSCOPE_API_KEY = "sk-your-key-here"

# Linux/Mac
export DASHSCOPE_API_KEY="sk-your-key-here"
```

> Lấy API key tại: https://dashscope.aliyun.com

### Bước 1: Cài thư viện

```bash
cd d:\qwen3v
python run.py install
```

### Bước 2: Build knowledge base index (chỉ cần 1 lần)

```bash
python run.py build-index
```

### Bước 3: Chạy server

```bash
python run.py serve
```

Hoặc chạy tất cả cùng lúc:

```bash
python run.py all
```

### Bước 4: Mở browser

Truy cập: **http://localhost:8000**

## API Endpoint

```
POST /analyze
Content-Type: multipart/form-data

file  : <image file>  (JPEG/PNG/WEBP, max 10MB)
query : <string>      (optional; nếu để trống, backend sẽ lấy query gần nhất của phiên)
session_id : <string> (optional; dùng để backend nhớ câu hỏi theo phiên)
user_id : <string>    (optional; thay thế cho session_id nếu bạn không có session)

Ghi nhớ hội thoại:
- Backend sẽ lưu thêm "turns" (user query + assistant JSON tóm tắt) theo `session_id/user_id`
- Các turns gần nhất sẽ được gửi kèm vào `messages` khi gọi Qwen, giúp LLM trả lời nhất quán khi người dùng hỏi lại

Response:
{
  "errors": [
    {
      "box_2d": [x1, y1, x2, y2],
      "reason": "Explanation"
    }
  ],
  "image_size": {"width": W, "height": H},
  "total_errors": N
}
```

## Models & APIs sử dụng

| Component         | Model/Tool                |
|-------------------|---------------------------|
| Embedding         | BAAI/bge-large-en         |
| Vector DB         | FAISS (IndexFlatIP)       |
| Vision Language   | Qwen VL Max (DashScope)   |
| Backend           | FastAPI + Uvicorn         |
| Frontend          | Plain HTML/CSS/JS         |
