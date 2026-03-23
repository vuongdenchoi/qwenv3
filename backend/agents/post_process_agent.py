"""
Post-Processing Agent – validate và chuẩn hóa JSON output từ Qwen.
Improvements:
  - Validates and defaults new 'severity' field (minor/major/critical)
  - Validates and defaults new 'category' field
  - Returns severity_summary breakdown in final dict
"""
from PIL import Image
import io
from .color_analyzer import analyze_box_contrast

VALID_SEVERITIES = {"minor", "major", "critical"}
VALID_CATEGORIES = {
    "color_theory", "typography", "layout_rules",
    "logo_design", "poster_design",
    "icon_design", "pattern_design",
    "general",
}


class PostProcessAgent:
    def process(
        self,
        raw_result: dict,
        image_bytes: bytes,
    ) -> dict:
        """
        Validate và clean Qwen output:
        1. Kiểm tra JSON structure hợp lệ
        2. Clamp bounding boxes trong giới hạn ảnh
        3. Loại bỏ duplicate bounding boxes
        4. Lọc bỏ errors có boxes quá nhỏ
        5. Validate severity + category fields (new)
        6. Build severity_summary (new)
        """
        # --- 1. Validate structure (hỗ trợ cả schema cũ và mới) ---
        errors = raw_result.get("e")
        if errors is None:
            errors = raw_result.get("errors")
        if errors is None or not isinstance(errors, list):
            raise ValueError("Response JSON thiếu trường 'e' hoặc 'errors'")

        # --- 2. Lấy kích thước ảnh ---
        img = Image.open(io.BytesIO(image_bytes))
        img_w, img_h = img.size

        # --- 3. Process từng error ---
        cleaned   = []
        seen_boxes = set()

        for err in errors:
            if not isinstance(err, dict):
                continue
            box = err.get("c") or err.get("box_2d")
            reason = err.get("r") or err.get("reason")
            if box is None or reason is None:
                continue
            if not (isinstance(box, list) and len(box) == 4):
                continue

            # Convert to int
            try:
                x1, y1, x2, y2 = [int(v) for v in box]
            except (ValueError, TypeError):
                continue

            # Clamp vào image bounds
            x1 = max(0, min(x1, img_w))
            y1 = max(0, min(y1, img_h))
            x2 = max(0, min(x2, img_w))
            y2 = max(0, min(y2, img_h))

            # Đảm bảo x1<x2, y1<y2
            x1, x2 = min(x1, x2), max(x1, x2)
            y1, y2 = min(y1, y2), max(y1, y2)

            # Bỏ qua boxes quá nhỏ (< 5×5 px)
            if (x2 - x1) < 5 or (y2 - y1) < 5:
                continue

            # Deduplication (bỏ qua nếu overlap >80% với box đã có)
            box_key = (x1 // 10, y1 // 10, x2 // 10, y2 // 10)
            if box_key in seen_boxes:
                continue
            seen_boxes.add(box_key)

            # --- Validate severity (hỗ trợ s/severity) ---
            severity = str(err.get("s") or err.get("severity") or "minor").lower().strip()
            if severity not in VALID_SEVERITIES:
                severity = "minor"

            # --- Validate category (hỗ trợ g/category) ---
            category = str(err.get("g") or err.get("category") or "general").lower().strip()
            if category not in VALID_CATEGORIES:
                category = "general"
                
            # --- Vision-based Color Analysis (WCAG) ---
            new_reason = str(reason).strip()
            new_severity = severity
            if category in ["typography", "color_theory"]:
                wcag_result = analyze_box_contrast(image_bytes, [x1, y1, x2, y2])
                ratio = wcag_result.get("ratio")
                if ratio is not None and not wcag_result.get("pass"):
                    # Override reason and severity based on hard math
                    new_reason = f"{new_reason} [LỖI WCAG: Tỷ lệ tương phản chỉ đạt {ratio}:1, dưới mức chuẩn 4.5:1. Bạn cần tăng độ tương phản sáng tối giữa chữ và nền.]"
                    new_severity = "critical" if ratio < 3.0 else "major"

            cleaned.append({
                "c"  : [x1, y1, x2, y2],
                "r"  : new_reason,
                "s": new_severity,
                "g": category,
            })

        # --- 4. Build severity summary (new) ---
        severity_summary = {"minor": 0, "major": 0, "critical": 0}
        for item in cleaned:
            severity_summary[item["s"]] += 1

        return {
            "e"  : cleaned,
            "isz": {"w": img_w, "h": img_h},
            "te" : len(cleaned),
            "ss" : severity_summary,
        }
