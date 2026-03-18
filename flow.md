# Flow & Kiến trúc Dự án — Design Check AI

## Tổng quan

**Design Check AI** là hệ thống kiểm tra lỗi thiết kế 2D (poster, logo, layout…) bằng cách kết hợp:
- **RAG** (Retrieval-Augmented Generation) dùng TF-IDF để tìm design rules liên quan
- **Qwen3-VL** (Vision-Language Model) để phân tích ảnh và phát hiện vi phạm
- **FastAPI** backend + **HTML/JS** frontend

---

## Cấu trúc thư mục

```
qwen3v/
├── run.py                          # CLI tiện ích khởi động hệ thống
├── backend/
│   ├── main.py                     # FastAPI server (entry point backend)
│   ├── requirements.txt            # Thư viện Python cần thiết
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── design_check_agent.py   # Orchestrator điều phối pipeline
│   │   ├── retrieval_agent.py      # Tìm kiếm design rules (TF-IDF)
│   │   ├── prompt_agent.py         # Xây dựng multimodal prompt
│   │   ├── qwen_agent.py           # Gọi Qwen VL API
│   │   └── post_process_agent.py   # Validate & làm sạch output
│   └── knowledge_base/
│       ├── build_index.py          # Script xây TF-IDF index
│       └── faiss_index/            # Index đã build (pkl, npz, json)
├── design_rules/                   # Knowledge base (file Markdown)
│   ├── color_theory.md
│   ├── typography.md
│   ├── layout_rules.md
│   ├── logo_design.md
│   ├── poster_design.md
│   ├── icon_design.md
│   └── pattern_design.md
└── frontend/
    └── index.html                  # Giao diện web người dùng
```

---

## Luồng chạy chính

### Bước 0 — Chuẩn bị (chạy 1 lần)

```
python run.py all
    ├── pip install -r requirements.txt   (install thư viện)
    └── python build_index.py             (build TF-IDF index)
```

`build_index.py` đọc 7 file `.md` trong `design_rules/`, chunking từng Rule block
riêng lẻ (regex `Rule N — Title`), tạo TF-IDF vectorizer với `max_features=10000`
và lưu 3 file xuống `faiss_index/`:
- `tfidf_vectorizer.pkl`
- `tfidf_matrix.npz`
- `metadata.json`

### Bước 1 — Khởi động server

```
python run.py serve
    └── uvicorn main:app --reload
```

`main.py` (FastAPI) mount frontend tại `/static`, expose 3 endpoints:
| Endpoint     | Method | Mô tả                               |
|--------------|--------|--------------------------------------|
| `/`          | GET    | Serve `frontend/index.html`          |
| `/health`    | GET    | Kiểm tra server còn sống             |
| `/analyze`   | POST   | Nhận ảnh → trả JSON kết quả phân tích|

### Bước 2 — Người dùng upload ảnh

Người dùng truy cập giao diện web (`index.html`), upload ảnh thiết kế.
Frontend POST form-data (`file` + `query`) lên endpoint `/analyze`.

### Bước 3 — Pipeline phân tích (trong `/analyze`)

```
POST /analyze
    │
    ├─► DesignCheckAgent.analyze()
    │       │
    │       ├─[1]─► RetrievalAgent.retrieve(query)
    │       │           • Transform query → TF-IDF vector
    │       │           • Cosine similarity với toàn bộ index
    │       │           • Áp category boost (×1.3) nếu query khớp domain
    │       │           • Trả top-10 rules có score cao nhất
    │       │
    │       ├─[2]─► PromptAgent.build_prompt(rules)
    │       │           • Build system prompt (vai trò reviewer 5 domain)
    │       │           • Ghép rules thành context "[Category > Section] Rule N — Title"
    │       │           • Trả (system_prompt, instruction_text)
    │       │
    │       ├─[3]─► QwenAgent.analyze(image_bytes, system_prompt, instruction)
    │       │           • Encode ảnh thành base64 data URL
    │       │           • Gửi multimodal message tới Qwen3-VL API (DashScope)
    │       │           • Parse JSON từ text response (strip markdown fences)
    │       │           • Trả dict {"errors": [...]}
    │       │
    │       └─[4]─► PostProcessAgent.process(raw_result, image_bytes)
    │                   • Validate cấu trúc JSON (bắt buộc có "errors" list)
    │                   • Clamp bounding boxes trong giới hạn ảnh
    │                   • Loại bỏ boxes trùng lặp (overlap >80%)
    │                   • Lọc boxes quá nhỏ (<5×5 px)
    │                   • Validate severity (minor/major/critical)
    │                   • Validate category (color_theory/typography/layout_rules/
    │                     logo_design/poster_design/icon_design/pattern_design/general)
    │                   • Build severity_summary
    │                   • Trả dict hoàn chỉnh
    │
    └─► JSON response trả về frontend
```

### Bước 4 — Hiển thị kết quả

Frontend (`index.html`) nhận JSON, vẽ bounding boxes lên ảnh canvas và hiển thị
danh sách lỗi kèm severity, category, và mô tả vi phạm.

---

## Tóm tắt từng file code

### `run.py`
Script CLI tiện ích với 4 lệnh: `install`, `build-index`, `serve`, `all`.
Dùng `subprocess` để gọi pip install, build_index.py, và uvicorn.
Không chứa logic nghiệp vụ, chỉ là wrapper điều phối.

---

### `backend/main.py`
FastAPI application. Lazy-load `DesignCheckAgent` (khởi tạo lần đầu khi có request).
Xử lý validation đầu vào (file type, size tối đa 10MB) và ánh xạ exceptions ra
HTTP status codes tương ứng (400, 422, 502, 500).

---

### `backend/knowledge_base/build_index.py`
Script xây TF-IDF knowledge base. 4 bước:
1. **Load** — đọc tất cả `.md` trong `design_rules/`
2. **Chunk** — cắt theo từng Rule block (regex), fallback sang paragraph 500 chars
3. **Build** — `TfidfVectorizer(ngram_range=(1,2), max_features=10000, sublinear_tf=True)`
4. **Save** — lưu vectorizer (pickle), matrix (sparse npz), metadata (json)

Mỗi chunk giữ metadata: `category`, `section`, `rule_number`, `rule_title`.

---

### `backend/agents/design_check_agent.py`
**Orchestrator** — khởi tạo 4 sub-agents và điều phối pipeline tuần tự:
`RetrievalAgent → PromptAgent → QwenAgent → PostProcessAgent`.
Log tiến trình và kết quả cuối (số lỗi, phân loại severity) ra stdout.

---

### `backend/agents/retrieval_agent.py`
Load TF-IDF index từ disk khi khởi tạo. Method `retrieve(query)`:
- Vectorize query, tính cosine similarity với toàn bộ matrix
- `_detect_categories()` — kiểm tra từ khoá query khớp domain nào (7 domain)
- Áp `CATEGORY_BOOST = 1.3` cho các chunk thuộc domain khớp
- Trả top-`k` (mặc định 10) kết quả kèm enriched metadata

---

### `backend/agents/prompt_agent.py`
Không có state, chỉ build text thuần tuý:
- `SYSTEM_PROMPT` — định nghĩa vai trò reviewer 5 domain thiết kế
- `INSTRUCTION_TEMPLATE` — hướng dẫn phân tích kèm output schema JSON
  (mỗi error có: `box_2d`, `reason`, `severity`, `category`)
- `build_prompt(rules)` — ghép rules thành context với header `[Category > Section] Rule N — Title`

---

### `backend/agents/qwen_agent.py`
Wrapper quanh `dashscope.MultiModalConversation`:
- Encode ảnh → base64 data URL
- Gửi structured messages (system + user với image + text)
- `_parse_json_response()` — strip markdown code fences, parse JSON,
  fallback dùng regex `{...}` nếu JSONDecodeError
- Model mặc định: `qwen3-vl-flash` qua endpoint quốc tế DashScope

---

### `backend/agents/post_process_agent.py`
Validate và chuẩn hóa output thô từ Qwen:
- Kiểm tra schema (bắt buộc `errors` là list, mỗi item có `box_2d` + `reason`)
- Clamp + sắp xếp lại tọa độ bounding box
- Deduplication bằng grid quantization (chia 10px)
- Lọc boxes `< 5×5 px`
- Validate `severity` ∈ {minor, major, critical}, default "minor"
- Validate `category` ∈ {color_theory, typography, layout_rules, logo_design,
  poster_design, icon_design, pattern_design, general}, default "general"
- Build và trả `severity_summary` dict

---

### `design_rules/*.md`
Knowledge base thủ công gồm 7 file Markdown:
| File                | Nội dung                                                          |
|---------------------|-------------------------------------------------------------------|
| `color_theory.md`   | Lý thuyết màu sắc: hue, contrast, palette, optical effect         |
| `typography.md`     | Quy tắc typography: font, legibility, spacing, hierarchy          |
| `layout_rules.md`   | Quy tắc layout: composition, grid, whitespace, balance            |
| `logo_design.md`    | Thiết kế logo: scalability, brand identity, sign theory           |
| `poster_design.md`  | Thiết kế poster: focal point, hierarchy, campaign design          |
| `icon_design.md`    | Thiết kế icon: sign type, legibility, style consistency, wayfinding, UI icon |
| `pattern_design.md` | Thiết kế pattern: repeat structure, motif, scale, color, digital production |

Mỗi rule được định dạng `Rule N — <Tên>` để script chunking nhận diện.

---

### `frontend/index.html`
Single-page application thuần HTML/CSS/JS:
- Upload ảnh, gửi POST `/analyze`
- Vẽ bounding boxes lên `<canvas>`
- Hiển thị bảng lỗi với severity tag màu sắc và category badge

---

## Sơ đồ phụ thuộc module

```
run.py
  └─► backend/knowledge_base/build_index.py
  └─► backend/main.py (uvicorn)
        └─► agents/design_check_agent.py
              ├─► agents/retrieval_agent.py
              │     └─► knowledge_base/faiss_index/ (pkl, npz, json)
              ├─► agents/prompt_agent.py
              ├─► agents/qwen_agent.py
              │     └─► dashscope API (Qwen3-VL)
              └─► agents/post_process_agent.py
                    └─► Pillow (PIL)
```
