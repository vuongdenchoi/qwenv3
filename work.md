# Walkthrough – Design Check AI System

## Tổng kết

Đã xây dựng thành công **hệ thống AI kiểm tra lỗi thiết kế 2D** theo đúng flow, ứng dụng pipeline RAG (Retrieval-Augmented Generation) kết hợp với Multimodal LLM (Qwen3-VL). Hệ thống đã được refactor tinh chuẩn, sử dụng TF-IDF tích hợp Category Boosting, giúp việc trích xuất Design Rules nhanh, nhẹ và triệt để các rủi ro tương thích môi trường.

## Cấu trúc code hiện tại

```text
d:\qwen3v\
├── design_rules/                    ← Knowledge Base (7 thư mục quy tắc thiết kế)
│   ├── typography.md
│   ├── color_theory.md
│   ├── layout_rules.md
│   ├── poster_design.md
│   ├── logo_design.md
│   ├── icon_design.md               
│   └── pattern_design.md            
├── backend/
│   ├── main.py                      ← FastAPI server (HTTP Endpoints)
│   ├── memory_store.py              ← In-memory Session persistence
│   ├── requirements.txt
│   ├── agents/
│   │   ├── design_check_agent.py    ← Orchestrator: Điều phối vòng đời Request
│   │   ├── retrieval_agent.py       ← Step 2: Tìm Rules với TF-IDF + Boosting
│   │   ├── prompt_agent.py          ← Step 3: Ghép prompt với context & schema
│   │   ├── qwen_agent.py            ← Step 4: Kết nối DashScope API (qwen3-vl)
│   │   └── post_process_agent.py    ← Step 6: Validate, format Box, lọc độ ưu tiên (Severity)
│   └── knowledge_base/
│       ├── build_index.py           ← Step 1: Phân mảnh rules và tạo Matrix Vector (TF-IDF)
│       └── faiss_index/             ← Thư mục chứa Vector Files (.pkl, .npz, metadata)
├── frontend/
│   └── index.html                   ← Step 7: UI Dashboard mạnh mẽ (Canvas vẽ Box, Dark theme)
├── run.py                           ← Unified CLI (install, serve, build-index)
└── README.md
```

## Kết quả xác minh

| Thành phần | Trạng thái |
|------------|-----------|
| Knowledge Base (7 rules files) | ✅ Bao quát từ layout, color đến icon, pattern |
| Chế độ Sinh Index (TF-IDF) | ✅ Chạy gọn nhẹ, chunking thông minh theo từng Rule |
| RetrievalAgent | ✅ Rule trả về chính xác cho prompt text |
| Qwen Agent & Validation | ✅ JSON output tuân thủ format (box, error severity) |
| Server Backend | ✅ Load tốt, quản lý Exception/Error code rõ ràng |
| Giao Diện Frontend | ✅ Rendering Canvas mượt mà, phân loại màu theo Severity |

## Cách chạy

```powershell
cd d:\qwen3v

# 1. Set biến môi trường API key
$env:DASHSCOPE_API_KEY = "sk-your-key-here"

# 2. Chạy indexer (chỉ cần chạy nếu rule có cập nhật)
python backend/knowledge_base/build_index.py

# 3. Khởi chạy Server
$env:PYTHONPATH = "d:\qwen3v\backend"
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000

# 4. Mở browser: http://localhost:8000
```

> **Lưu ý kỹ thuật**: Hệ thống ưu tiên phương án **TF-IDF + cosine similarity** (từ `scikit-learn`) — đảm bảo hiệu năng cực nhanh, zero GPU memory, né xung đột thư viện Deep Learning phức tạp mà vẫn đạt KPIs tìm rule chính xác nhờ cơ chế rule-level chunking chặt chẽ.

---

## 🚀 ĐỊNH HƯỚNG PHÁT TRIỂN NÂNG CẤP (ROADMAP)

Dự án đã có base vững chắc. Để đóng gói thành sản phẩm thương mại hoặc tool nội bộ ở scope lớn hơn, dưới đây là các bước có thể mở rộng tiếp theo:

### 1. Kiến trúc Frontend & Trải nghiệm UX (Modernization)
- **Framework Conversion**: Rewrite giao diện từ file HTML thuần sang các Framework hiện đại như **React (Next.js)** hoặc **Vue (Nuxt.js)**. Điều này giúp chia nhỏ các Component (Chips, Canvas, Error Sidebar, Chatbox) dễ maintain và tái sử dụng code.
- **Công cụ phân tích ảnh (Advanced Viewer)**: 
  - Bổ sung chức năng **Zoom, Pan dọc/ngang** trên vùng kết quả ảnh canvas để soi xét kĩ các box nhỏ bị trùng lặp.
  - Hover chuột vào lỗi bên Error List -> Highlights bounding box tương ứng và làm mờ các box khác (Focus Mode).
- **History Dashboard**: Trang lịch sử cho phép người dùng xem và kéo lại những bản design đã check trong quá khứ thông qua session / cookie.

### 2. Quản lý Dữ liệu & Database (Persistence)
- **Data Persistence**: Thay thế `memory_store.py` (in-memory, bị mất khi restart server) bằng **SQLite** (chạy cục bộ) hoặc **PostgreSQL**. Lưu trữ lịch sử chat, input image, kết quả JSON JSON schema trả về.
- **Rule Design CMS API**: 
  - Mở rộng API backend cung cấp ứng dụng CRUD (Create, Read, Update, Delete) đối với kho thư viện `design_rules`. 
  - Thay vì thao tác file `.md` bằng code, Admin có thể quản lí Rule ngay trên Webpage. Thêm luồng Webhook tự động compile lại vector array (trigger index bối cảnh).

### 3. Nâng cấp Engine AI & Luồng Pipeline
- **Multiple Model Fallback**: Mở rộng `qwen_agent.py` thành mô hình Factory pattern, cho phép tích hợp linh động nhiều API khác ngoài DashScope qua LangChain, chẳng hạn gửi request backup đến **GPT-4o** hay **Claude 3.5 Sonnet** nếu mô hình của Qwen bị timeout, giới hạn rate limit.
- **Multi-Agent Debate**: Trước khi xuất lỗi cuối cùng, thêm 1 step LLM Critic nội bộ rà soát lại kết quả xem lỗi này có thực là vi phạm không (tránh false positive - báo ảo).
- **Vision-based Color Analysis**: Kết hợp OpenCV hoặc logic tách vùng ảnh để truy xuất chính xác thông số Palette (Màu hex) trên hình ảnh, từ đó so chuẩn tỷ lệ tương phản WCAG (thay vì thuần túy để Qwen nhìn cảm tính).
- **Dynamic Few-Shot (In-Context Learning)**: Đưa các hình ảnh "Good/Bad practice" thẳng vào template trong Prompt đối với mỗi lĩnh vực, ép model học theo trực quan giúp Output có tính ổn định hơn.

### 4. Tính năng Thương mại & Ứng dụng Bổ trợ
- **Xuất Báo Cáo Chuyên Nghiệp (PDF Report / Export)**: Tính năng One-click tạo PDF Report audit toàn diện hình ảnh có đính kèm các vùng đỏ (Bounding boxes), danh sách Error / Cấp độ vi phạm + Nhận xét chung. Gửi thẳng đường link cho đối tác thiết kế khắc phục.
- **Brand Identity Guard**: Cho phép doanh nghiệp upload hẳn **Brand Guidelines** (PDF file) cá nhân. Hệ thống RAG phân tách file tài liệu, Agent sẽ rà soát nội suy xem Designer có đang tuân thủ khoảng cách Logo Safe Zone riêng của Công ty hay dùng sai màu Brand Color không.
- **Auto Design Fix Suggestion**: Gắn nhánh kết quả lỗi này truyền vào pipeline sinh ảnh mã nguồn mở (Stable Diffusion Inpainting) để sinh ra **hình mẫu Suggestion sửa lỗi mẫu** kế bên, cung cấp so sánh Before/After.
