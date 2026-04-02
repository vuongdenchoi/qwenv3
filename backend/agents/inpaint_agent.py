"""
InpaintAgent – Gọi Wan 2.6 Image (wan2.6-image) để gen lại vùng lỗi thiết kế.

Chiến lược:
  - Wan 2.6 dùng instruction-based editing: không cần mask image riêng.
  - Ta chỉ cần: ảnh gốc (URL public) + prompt mô tả lỗi cần fix.
  - Môi trường: Option C (Docker + public domain).
    PUBLIC_BASE_URL env var chứa base URL, ví dụ: https://my-domain.com
"""

import os
import time
import requests
import io
from pathlib import Path
from typing import Optional, Tuple, List
from PIL import Image

try:
    import dashscope
    from dashscope import ImageSynthesis
    DASHSCOPE_AVAILABLE = True
except ImportError:
    DASHSCOPE_AVAILABLE = False


TEMP_DIR = Path(__file__).parent.parent / "static_temp"
TEMP_DIR.mkdir(exist_ok=True)

# Model ID chính thức Wan 2.6
WAN_MODEL = "wan2.6-image"


class InpaintAgent:
    """
    Agent gọi Wan 2.6 Image API để sửa các vùng lỗi thiết kế trong ảnh.
    """

    def __init__(self, api_key: str, public_base_url: str = ""):
        """
        Args:
            api_key: DashScope API key.
            public_base_url: URL gốc public của server (e.g. https://my-domain.com).
                             Dùng để tạo URL cho ảnh host trên /temp-assets/.
        """
        self.api_key = api_key
        self.public_base_url = public_base_url.rstrip("/")
        if DASHSCOPE_AVAILABLE and api_key:
            dashscope.api_key = api_key

    # ------------------------------------------------------------------
    # 1. Chuẩn bị ảnh gốc – lưu ra static_temp và trả về public URL
    # ------------------------------------------------------------------
    def prepare_original_image(
        self,
        image_bytes: bytes,
        session_id: str,
    ) -> Tuple[str, str]:
        """
        Lưu ảnh gốc vào static_temp, trả về (local_path, public_url).
        """
        filename = f"original_{session_id}.jpg"
        local_path = TEMP_DIR / filename
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        img.save(str(local_path), format="JPEG", quality=90)
        public_url = f"{self.public_base_url}/temp-assets/{filename}"
        return str(local_path), public_url

    # ------------------------------------------------------------------
    # 2. Build prompt từ danh sách lỗi
    # ------------------------------------------------------------------
    def build_prompt(self, errors: List[dict], error_indices: List[int]) -> str:
        """
        Tổng hợp prompt từ các lỗi được chọn.
        Output là 1 câu tiếng Anh mô tả tất cả những gì cần sửa.
        """
        selected = [errors[i] for i in error_indices if 0 <= i < len(errors)]
        if not selected:
            return "Improve the overall visual quality and design consistency."

        parts = []
        for err in selected:
            reason = err.get("r", "").strip()
            if reason:
                # Giữ nội dung mô tả nhưng cắt bớt nếu quá dài
                parts.append(reason[:200])

        joined = " | ".join(parts)
        prompt = (
            f"Fix the following design issues in this image: {joined}. "
            "Ensure the result is visually consistent, has proper contrast, "
            "clear typography, and follows professional design standards. "
            "Keep all other elements unchanged."
        )
        return prompt[:800]  # Giới hạn độ dài prompt

    # ------------------------------------------------------------------
    # 3. Build preview mask (chỉ dùng cho hiển thị UI, không gửi API)
    # ------------------------------------------------------------------
    def build_mask_preview(
        self,
        image_bytes: bytes,
        errors: List[dict],
        error_indices: List[int],
    ) -> bytes:
        """
        Tạo ảnh preview: overlay màu đỏ bán trong suốt lên vùng lỗi được chọn.
        Trả về bytes PNG để hiển thị trong UI (không gửi Wan API).
        """
        img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))

        try:
            from PIL import ImageDraw
            draw = ImageDraw.Draw(overlay)
            for i in error_indices:
                if 0 <= i < len(errors):
                    box = errors[i].get("c") or errors[i].get("box_2d")
                    if isinstance(box, list) and len(box) == 4:
                        x1, y1, x2, y2 = [int(v) for v in box]
                        draw.rectangle([x1, y1, x2, y2], fill=(255, 60, 60, 130))
                        draw.rectangle([x1, y1, x2, y2], outline=(255, 60, 60, 255), width=3)
        except Exception as e:
            print(f"[InpaintAgent] Lỗi vẽ preview mask: {e}")

        merged = Image.alpha_composite(img, overlay).convert("RGB")
        buf = io.BytesIO()
        merged.save(buf, format="PNG")
        return buf.getvalue()

    # ------------------------------------------------------------------
    # 4. Gọi Wan 2.6 API – async task poll
    # ------------------------------------------------------------------
    def run_inpainting(
        self,
        base_image_url: str,
        prompt: str,
        timeout: int = 180,
        poll_interval: int = 4,
    ) -> dict:
        """
        Gọi Wan 2.6 Image API và poll kết quả.

        Returns:
            {
                "success": bool,
                "result_url": str | None,
                "result_bytes": bytes | None,  # đã download nếu thành công
                "error": str | None
            }
        """
        if not DASHSCOPE_AVAILABLE:
            return {"success": False, "error": "dashscope package not installed."}

        print(f"[InpaintAgent] Gọi Wan 2.6: model={WAN_MODEL}")
        print(f"[InpaintAgent] base_image_url={base_image_url}")
        print(f"[InpaintAgent] prompt={prompt[:100]}...")

        try:
            # Wan 2.6 dùng instruction-based editing: gửi ảnh gốc + prompt
            response = ImageSynthesis.async_call(
                model=WAN_MODEL,
                prompt=prompt,
                image_urls=[base_image_url],
                n=1,
            )

            if response.status_code != 200:
                return {
                    "success": False,
                    "error": f"Wan API error {response.status_code}: {response.message}"
                }

            task_id = response.output.get("task_id") if hasattr(response, "output") else None
            print(f"[InpaintAgent] task_id={task_id}")

            # Poll kết quả
            deadline = time.time() + timeout
            while time.time() < deadline:
                time.sleep(poll_interval)
                fetch = ImageSynthesis.fetch(response)

                if fetch.status_code != 200:
                    return {"success": False, "error": f"Poll error: {fetch.message}"}

                task_status = fetch.output.get("task_status", "") if hasattr(fetch, "output") else ""
                print(f"[InpaintAgent] task_status={task_status}")

                if task_status == "SUCCEEDED":
                    results = fetch.output.get("results", []) if hasattr(fetch, "output") else []
                    if results and results[0].get("url"):
                        result_url = results[0]["url"]
                        # Download ảnh kết quả
                        img_resp = requests.get(result_url, timeout=30)
                        if img_resp.status_code == 200:
                            return {
                                "success": True,
                                "result_url": result_url,
                                "result_bytes": img_resp.content,
                                "error": None
                            }
                    return {"success": False, "error": "Task succeeded but no result URL."}

                if task_status in ("FAILED", "CANCELED"):
                    err_msg = fetch.output.get("message", "Unknown error") if hasattr(fetch, "output") else "Unknown"
                    return {"success": False, "error": f"Task {task_status}: {err_msg}"}

            return {"success": False, "error": f"Timeout ({timeout}s) – task chưa xong."}

        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------
    # 5. Entry point chính
    # ------------------------------------------------------------------
    def fix_errors(
        self,
        image_bytes: bytes,
        analysis_result: dict,
        error_indices: List[int],
        session_id: str,
        custom_prompt: Optional[str] = None,
    ) -> dict:
        """
        Pipeline đầy đủ: chuẩn bị ảnh → build prompt → gọi Wan API.

        Returns:
            {
                "success": bool,
                "result_bytes": bytes | None,
                "prompt_used": str,
                "error": str | None
            }
        """
        errors = analysis_result.get("e", [])

        # B1: Build prompt
        prompt = custom_prompt.strip() if custom_prompt else self.build_prompt(errors, error_indices)

        # B2: Lưu ảnh gốc ra static_temp → lấy public URL
        local_path, public_url = self.prepare_original_image(image_bytes, session_id)
        print(f"[InpaintAgent] Ảnh gốc host tại: {public_url}")

        # B3: Gọi Wan API
        result = self.run_inpainting(
            base_image_url=public_url,
            prompt=prompt,
        )

        return {
            "success": result.get("success", False),
            "result_bytes": result.get("result_bytes"),
            "prompt_used": prompt,
            "error": result.get("error"),
        }
