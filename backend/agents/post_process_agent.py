"""
Post-Processing Agent – validate và chuẩn hóa JSON output từ Qwen.
Improvements:
  - Validates and defaults new 'severity' field (minor/major/critical)
  - Validates and defaults new 'category' field
  - Returns severity_summary breakdown in final dict
"""
import re
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
        7. Clean 'Rule X' mentions from reasons (User request)
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

            # Adaptive Coordinate Conversion:
            # - qwen3-vl-flash (và series 2.5) dùng normalized 0-1000.
            # - qwen-vl-max thường dùng pixel thực nếu ảnh lớn.
            # Heuristic: Nếu có giá trị > 1000 -> chắc chắn là pixel. 
            # Nếu tất cả <= 1000 và ảnh gốc lớn (>1000px) -> khả năng cao là normalized.
            needs_normalization = all(v <= 1000 for v in [x1, y1, x2, y2])
            
            if needs_normalization:
                x1 = int(x1 / 1000 * img_w)
                y1 = int(y1 / 1000 * img_h)
                x2 = int(x2 / 1000 * img_w)
                y2 = int(y2 / 1000 * img_h)

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

            # Deduplication
            box_key = (x1 // 10, y1 // 10, x2 // 10, y2 // 10)
            if box_key in seen_boxes:
                continue
            seen_boxes.add(box_key)

            # --- Validate severity ---
            severity = str(err.get("s") or err.get("severity") or "minor").lower().strip()
            if severity not in VALID_SEVERITIES:
                severity = "minor"

            # --- Validate category ---
            category = str(err.get("g") or err.get("category") or "general").lower().strip()
            if category not in VALID_CATEGORIES:
                category = "general"
                
            # --- Vision-based Color Analysis (WCAG) ---
            new_reason = str(reason).strip()
            
            # --- USER REQUEST: Clean 'Rule X' mentions ---
            # Remove patterns like "Rule 7", "Rule 123", "Rules 1-2", "(Rule 7)" etc.
            
            # 1. Remove "Rule X" + optional separator following it (e.g., "Rule 7 — ", "Rule 7: ")
            new_reason = re.sub(r'(?i)\bRules?\s+\d+([-&,]\d+)?\s*[:\-—]+\s*', '', new_reason)
            
            # 2. Remove "Rule X" without separator (e.g., "violating Rule 7", "(Rule 7)")
            new_reason = re.sub(r'(?i)\bRules?\s+\d+([-&,]\d+)?\b', '', new_reason)
            
            # 3. Clean up empty parentheses "( )"
            new_reason = re.sub(r'\(\s*\)', '', new_reason)
            
            # 4. Clean up multiple spaces and strip
            new_reason = re.sub(r'\s+', ' ', new_reason).strip()

            new_severity = severity
            if category in ["typography", "color_theory"]:
                wcag_result = analyze_box_contrast(image_bytes, [x1, y1, x2, y2])
                ratio = wcag_result.get("ratio")
                if ratio is not None and not wcag_result.get("pass"):
                    new_reason = f"{new_reason} [LỖI WCAG: Tỷ lệ tương phản chỉ đạt {ratio}:1, dưới mức chuẩn 4.5:1. Bạn cần tăng độ tương phản sáng tối giữa chữ và nền.]"
                    new_severity = "critical" if ratio < 3.0 else "major"

            cleaned.append({
                "c"  : [x1, y1, x2, y2],
                "r"  : new_reason,
                "s": new_severity,
                "g": category,
            })

        # --- 4. Build severity summary ---
        severity_summary = {"minor": 0, "major": 0, "critical": 0}
        for item in cleaned:
            severity_summary[item["s"]] += 1

        usage_data = raw_result.get("_usage", {}) if isinstance(raw_result, dict) else {}
        return {
            "e"  : cleaned,
            "isz": {"w": img_w, "h": img_h},
            "te" : len(cleaned),
            "ss" : severity_summary,
            "inputtoken": usage_data.get("input_tokens", 0),
            "outputtoken": usage_data.get("output_tokens", 0),
            "totaltoken": usage_data.get("total_tokens", 0)
        }
