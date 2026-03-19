"""
Qwen Agent – gọi Qwen VL API qua dashscope SDK (MultiModalConversation).
Format theo: https://help.aliyun.com/zh/dashscope/multimodal-conversation
"""
import os
import base64
import json
import re
from typing import Optional, List, Dict, Any
import dashscope
from dashscope import MultiModalConversation

# -----------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------
QWEN_API_KEY = os.getenv("DASHSCOPE_API_KEY", "sk-39c8667844bd4d738ca1c0e387afbc23")
QWEN_MODEL   = os.getenv("QWEN_MODEL", "qwen3-vl-flash")

# Dùng endpoint quốc tế
dashscope.base_http_api_url = "https://dashscope-intl.aliyuncs.com/api/v1"


class QwenAgent:
    def __init__(self, api_key=None, model=None):
        self.api_key = api_key or QWEN_API_KEY
        self.model   = model   or QWEN_MODEL

        if not self.api_key:
            raise ValueError(
                "DASHSCOPE_API_KEY chưa được set. "
                "Export DASHSCOPE_API_KEY hoặc truyền api_key vào constructor."
            )

    # ------------------------------------------------------------------
    # Core: call Qwen VL qua dashscope SDK
    # ------------------------------------------------------------------
    def analyze(
        self,
        image_bytes: bytes,
        system_prompt: str,
        instruction: str,
        mime_type: str = "image/jpeg",
        history_messages: Optional[List[Dict[str, Any]]] = None,
    ) -> dict:
        """
        Gửi ảnh + prompt tới Qwen VL, trả về dict với 'errors' list.
        """
        # Encode ảnh thành base64 data URL
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        image_data_url = f"data:{mime_type};base64,{b64}"

        messages = [
            {
                "role": "system",
                "content": [{"text": system_prompt}],
            },
        ]
        if history_messages:
            # Expect dashscope message dicts: {"role": "...", "content": [{"text": "..."}]}
            messages.extend(history_messages)
        messages.append(
            {
                "role": "user",
                "content": [
                    {"image": image_data_url},
                    {"text": instruction},
                ],
            }
        )

        try:
            response = MultiModalConversation.call(
                api_key=self.api_key,
                model=self.model,
                messages=messages,
                stream=False,
            )
        except Exception as e:
            raise RuntimeError(f"DashScope SDK error: {e}")

        # Kiểm tra status
        if response.status_code != 200:
            raise RuntimeError(
                f"Qwen API error {response.status_code}: "
                f"{response.message} (request_id={response.request_id})"
            )

        # Lấy text content từ response
        try:
            content = response.output.choices[0].message.content
            # content là list: [{"text": "..."}] hoặc string
            if isinstance(content, list):
                raw_text = "".join(
                    item.get("text", "") for item in content
                    if isinstance(item, dict)
                )
            else:
                raw_text = str(content)
        except (KeyError, IndexError, AttributeError) as e:
            raise RuntimeError(f"Không thể parse response: {e}\nFull: {response}")

        return self._parse_json_response(raw_text)

    def chat_text(
        self,
        *,
        system_prompt: str,
        user_text: str,
        history_messages: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """
        Text-only chat with the same Qwen endpoint (no image).
        Returns assistant text.
        """
        user_text = str(user_text).strip()
        if not user_text:
            raise ValueError("Tin nhan chat rong.")

        messages = [
            {"role": "system", "content": [{"text": system_prompt}]},
        ]
        if history_messages:
            messages.extend(history_messages)
        messages.append({"role": "user", "content": [{"text": user_text}]})

        try:
            response = MultiModalConversation.call(
                api_key=self.api_key,
                model=self.model,
                messages=messages,
                stream=False,
            )
        except Exception as e:
            raise RuntimeError(f"DashScope SDK error: {e}")

        if response.status_code != 200:
            raise RuntimeError(
                f"Qwen API error {response.status_code}: "
                f"{response.message} (request_id={response.request_id})"
            )

        try:
            content = response.output.choices[0].message.content
            if isinstance(content, list):
                return "".join(
                    item.get("text", "") for item in content
                    if isinstance(item, dict)
                ).strip()
            return str(content).strip()
        except (KeyError, IndexError, AttributeError) as e:
            raise RuntimeError(f"Không thể parse response: {e}\nFull: {response}")

    def chat_json(
        self,
        *,
        system_prompt: str,
        user_text: str,
        history_messages: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Text-only chat, but forces the model to return JSON.
        Returns parsed dict.
        """
        raw = self.chat_text(
            system_prompt=system_prompt,
            user_text=user_text,
            history_messages=history_messages,
        )
        return self._parse_json_response(raw)

    def locate_box(
        self,
        *,
        image_bytes: bytes,
        mime_type: str,
        user_request: str,
        context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Use vision to locate a region in the image described by user_request.
        Returns dict: {"box_2d":[x1,y1,x2,y2], "reason": "..."} (JSON).
        """
        user_request = str(user_request).strip()
        if not user_request:
            raise ValueError("Mo ta vung can zoom rong.")

        b64 = base64.b64encode(image_bytes).decode("utf-8")
        image_data_url = f"data:{mime_type};base64,{b64}"

        system_prompt = (
            "You are a precise visual localizer. "
            "Given an image and a Vietnamese request about a region to zoom, "
            "return ONLY valid JSON with a single bounding box.\n"
            "Schema:\n"
            "{\n"
            '  "box_2d": [x1, y1, x2, y2],\n'
            '  "reason": "<short>"\n'
            "}\n"
            "Rules:\n"
            "- box_2d MUST be pixel coordinates in the original image.\n"
            "- If you cannot locate confidently, still return your best guess box.\n"
        )
        instruction = "Yeu cau nguoi dung: " + user_request
        if context:
            instruction += "\nNgu canh bo sung (neu co):\n" + str(context).strip()

        messages = [
            {"role": "system", "content": [{"text": system_prompt}]},
            {
                "role": "user",
                "content": [
                    {"image": image_data_url},
                    {"text": instruction},
                ],
            },
        ]

        try:
            response = MultiModalConversation.call(
                api_key=self.api_key,
                model=self.model,
                messages=messages,
                stream=False,
            )
        except Exception as e:
            raise RuntimeError(f"DashScope SDK error: {e}")

        if response.status_code != 200:
            raise RuntimeError(
                f"Qwen API error {response.status_code}: "
                f"{response.message} (request_id={response.request_id})"
            )

        try:
            content = response.output.choices[0].message.content
            if isinstance(content, list):
                raw_text = "".join(
                    item.get("text", "") for item in content
                    if isinstance(item, dict)
                )
            else:
                raw_text = str(content)
        except (KeyError, IndexError, AttributeError) as e:
            raise RuntimeError(f"Không thể parse response: {e}\nFull: {response}")

        return self._parse_json_response(raw_text)

    # ------------------------------------------------------------------
    # JSON parser – strip markdown fences nếu có
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_json_response(raw_text: str) -> dict:
        text = re.sub(r"```(?:json)?", "", raw_text).strip().strip("`").strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
            raise ValueError(f"Không thể parse JSON từ Qwen response:\n{raw_text}")
