# Thêm Knowledge Base: Icon Design & Pattern Design

Dự án đã có 5 file design rules. Người dùng cung cấp thêm 2 tài liệu mới ([icon.docx](file:///d:/qwen3v/icon.docx) và [pattern.docx](file:///d:/qwen3v/pattern.docx)). Cần:
1. Tạo 2 file markdown knowledge base mới với cấu trúc tương tự các file cũ.
2. Cập nhật code backend để nhận diện 2 category mới.

---

## Proposed Changes

### Design Rules Knowledge Base

#### [NEW] [icon_design.md](file:///d:/qwen3v/design_rules/icon_design.md)
Tạo file với ~16 rules tổ chức theo các phần chính từ [icon.docx](file:///d:/qwen3v/icon.docx):
- **I. Icon as Sign** – loại icon (icon/index/symbol), abstraction
- **II. Clarity and Legibility** – legibility at scale, monochrome, simplicity
- **III. Consistency and Style** – stroke weight, grid, style unity
- **IV. Wayfinding Systems** – spatial navigation, modularity, accessibility
- **V. Interactive and Digital Icons** – UI icons, clickability, animation
- **VI. Icon Sets and Systems** – collection cohesion, naming, versioning

#### [NEW] [pattern_design.md](file:///d:/qwen3v/design_rules/pattern_design.md)
Tạo file với ~18 rules trực tiếp từ nội dung [pattern.docx](file:///d:/qwen3v/pattern.docx):
- **I. Repeat Structure** – straight/half-drop/brick/mirrored repeat
- **II. Motif Orientation** – directional và tossed motifs
- **III. Scale & Density** – small/large-scale, dense/open print
- **IV. Color in Patterns** – cohesion, multicolor, tonal, high-contrast palettes
- **V. Pattern Construction** – texture, layering, depth
- **VI. Motif Design** – geometric, floral, folk, ethnic, children's, conversational
- **VII. Digital Production** – hand repeat, Illustrator, Photoshop

---

### Backend Code Updates

#### [MODIFY] [retrieval_agent.py](file:///d:/qwen3v/backend/agents/retrieval_agent.py)
- Thêm 2 keys mới vào `CATEGORY_KEYWORDS`:
  - `"icon_design"`: keywords liên quan đến icons, pictograms, wayfinding, signage, UI icons
  - `"pattern_design"`: keywords liên quan đến patterns, motifs, repeat, texture, surface design

#### [MODIFY] [prompt_agent.py](file:///d:/qwen3v/backend/agents/prompt_agent.py)
- Cập nhật `SYSTEM_PROMPT` để liệt kê 7 domain (thêm Icon Design và Pattern Design)
- Cập nhật `INSTRUCTION_TEMPLATE` để thêm `"icon_design"` và `"pattern_design"` vào danh sách valid categories

#### [MODIFY] [post_process_agent.py](file:///d:/qwen3v/backend/agents/post_process_agent.py)
- Thêm `"icon_design"` và `"pattern_design"` vào `VALID_CATEGORIES`

#### [MODIFY] [flow.md](file:///d:/qwen3v/flow.md)
- Cập nhật cấu trúc thư mục để liệt kê 7 file design rules
- Cập nhật bảng mô tả design_rules để thêm 2 file mới
- Cập nhật mô tả [post_process_agent.py](file:///d:/qwen3v/backend/agents/post_process_agent.py) và [retrieval_agent.py](file:///d:/qwen3v/backend/agents/retrieval_agent.py) để phản ánh 7 categories

---

## Verification Plan

### Rebuild Index
Sau khi tạo xong 2 file [.md](file:///d:/qwen3v/work.md) mới và cập nhật code, rebuild TF-IDF index:
```
cd d:\qwen3v\backend\knowledge_base
python build_index.py
```
Kiểm tra output: số chunks phải tăng so với trước (trước là 5 files, nay là 7 files).

### Manual Check
Sau khi rebuild index và khởi động server (`python run.py serve`), gọi endpoint `/analyze` với một ảnh có icon hoặc pattern. Kiểm tra response JSON có `category` là `"icon_design"` hoặc `"pattern_design"`.
