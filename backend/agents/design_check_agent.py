"""
DesignCheckAgent – orchestrator điều phối toàn bộ pipeline.
"""
import mimetypes
from .retrieval_agent import RetrievalAgent
from .prompt_agent import PromptAgent
from .qwen_agent import QwenAgent
from .post_process_agent import PostProcessAgent


class DesignCheckAgent:
    """
    Pipeline:
        image_bytes
            -> RetrievalAgent  (TF-IDF search, top-k rules with category boost)
            -> PromptAgent     (build domain-aware multimodal prompt)
            -> QwenAgent       (Qwen VL API call)
            -> PostProcessAgent (validate + clean, add severity/category)
            -> final result JSON
    """

    def __init__(self, api_key=None, top_k=10):
        self.retriever    = RetrievalAgent(top_k=top_k)
        self.prompt_agent = PromptAgent()
        self.qwen_agent   = QwenAgent(api_key=api_key)
        self.post_proc    = PostProcessAgent()

    def analyze(
        self,
        image_bytes,
        filename="image.jpg",
        query="graphic design poster advertisement",
        history_messages=None,
    ):
        """Main entry point. Returns validated result dict."""
        # Step 1: Retrieval (with category boost)
        print(f"[DesignCheckAgent] Retrieving rules for query: '{query}'")
        rules = self.retriever.retrieve(query.lower())
        print(f"[DesignCheckAgent] Retrieved {len(rules)} rules")

        # Log which rules were retrieved
        for r in rules:
            cat = r.get("category", "?")
            num = r.get("rule_number", 0)
            title = r.get("rule_title", "")[:50]
            score = r.get("score", 0.0)
            print(f"  [{cat}] Rule {num} — {title}  (score={score:.3f})")

        # Step 2: Build prompt
        system_prompt, instruction = self.prompt_agent.build_prompt(rules)

        # Step 3: Qwen API
        mime_type, _ = mimetypes.guess_type(filename)
        mime_type = mime_type or "image/jpeg"
        print(f"[DesignCheckAgent] Calling Qwen VL API ({mime_type})...")
        raw_result = self.qwen_agent.analyze(
            image_bytes=image_bytes,
            system_prompt=system_prompt,
            instruction=instruction,
            mime_type=mime_type,
            history_messages=history_messages,
        )
        print(f"[DesignCheckAgent] Raw result: {raw_result}")

        # Step 4: Post-process
        result = self.post_proc.process(raw_result, image_bytes)
        print(
            f"[DesignCheckAgent] Final errors: {result['te']} "
            f"(minor={result['ss']['minor']}, "
            f"major={result['ss']['major']}, "
            f"critical={result['ss']['critical']})"
        )
        return result
