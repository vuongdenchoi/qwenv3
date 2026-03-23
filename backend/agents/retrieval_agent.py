"""
Retrieval Agent – tìm design rules liên quan dùng Multilingual Embedding.
Model: paraphrase-multilingual-MiniLM-L12-v2
  - Hỗ trợ tiếng Việt + tiếng Anh (và 50+ ngôn ngữ khác)
  - Không cần query expansion / synonym dict
  - Category boost ×1.3 vẫn giữ nguyên
"""
import os
os.environ["USE_TF"] = "0"
os.environ["USE_TORCH"] = "1"

import json
import numpy as np
from typing import List, Dict, Set
from pathlib import Path


INDEX_DIR  = Path(__file__).resolve().parent.parent / "knowledge_base" / "faiss_index"
MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

# Map query keywords → category names (dùng để boost score)
CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "color_theory"  : ["color", "colour", "hue", "saturation", "contrast", "palette",
                        "rgb", "cmyk", "tint", "shade", "complementary", "analogous",
                        "warm", "cool", "vibration", "value",
                        # Vietnamese
                        "màu", "màu sắc", "tương phản", "bảng màu", "độ bão hòa"],
    "typography"    : ["typography", "typeface", "font", "serif", "sans", "type",
                        "leading", "kerning", "tracking", "legibility", "readability",
                        "headline", "body text", "letter", "glyph", "weight",
                        # Vietnamese
                        "chữ", "font chữ", "kiểu chữ", "cỡ chữ", "dễ đọc"],
    "layout_rules"  : ["layout", "grid", "composition", "margin", "spacing", "alignment",
                        "column", "proximity", "whitespace", "white space", "hierarchy",
                        "balance", "symmetry", "asymmetry", "direction", "wayfinding",
                        # Vietnamese
                        "bố cục", "lưới", "khoảng trắng", "căn chỉnh", "cân bằng"],
    "logo_design"   : ["logo", "logotype", "brand", "identity", "mark", "monogram",
                        "wordmark", "branding", "graphic identity", "exclusion zone",
                        # Vietnamese
                        "thương hiệu", "nhận diện"],
    "poster_design" : ["poster", "advertisement", "billboard", "campaign", "print",
                        "focal", "visual noise", "outdoor", "format", "signage",
                        # Vietnamese
                        "áp phích", "quảng cáo", "tờ rơi"],
    "icon_design"   : ["icon", "pictogram", "symbol", "wayfinding", "glyph",
                        "ui icon", "sign", "pictograph", "stroke weight", "icon set",
                        "icon system", "monochrome icon", "icon grid", "legibility",
                        "icon style", "navigation icon", "app icon", "ui symbol",
                        # Vietnamese
                        "biểu tượng", "icon"],
    "pattern_design": ["pattern", "motif", "repeat", "tile", "tiling", "textile",
                        "half-drop", "brick repeat", "mirrored repeat", "tossed",
                        "surface design", "print design", "seamless", "density",
                        "ditsy", "floral pattern", "geometric pattern", "folk pattern",
                        # Vietnamese
                        "họa tiết", "hoa văn", "lặp lại"],
}

CATEGORY_BOOST = 1.3  # score multiplier when query matches a category


class RetrievalAgent:
    def __init__(self, top_k: int = 10):
        self.top_k = top_k
        self._load_model()
        self._load_index()

    def _load_model(self):
        """Load sentence-transformer model (1 lần khi khởi tạo)."""
        from sentence_transformers import SentenceTransformer
        print(f"[RetrievalAgent] Loading embedding model: {MODEL_NAME}")
        self.model = SentenceTransformer(MODEL_NAME)
        print(f"[RetrievalAgent] Model loaded.")

    def _load_index(self):
        """Load embedding vectors và metadata từ disk."""
        emb_path  = INDEX_DIR / "embeddings.npy"
        meta_path = INDEX_DIR / "metadata.json"

        if not emb_path.exists():
            raise FileNotFoundError(
                f"Embedding index không tìm thấy tại {INDEX_DIR}. "
                "Chạy backend/knowledge_base/build_index.py trước."
            )

        self.embeddings = np.load(str(emb_path))  # shape (N, 384)
        with open(meta_path, encoding="utf-8") as f:
            self.metadata = json.load(f)
        print(f"[RetrievalAgent] Loaded embeddings: {self.embeddings.shape[0]} chunks, dim={self.embeddings.shape[1]}")

    # ------------------------------------------------------------------
    # Detect which design categories the query matches (for boost)
    # ------------------------------------------------------------------
    def _detect_categories(self, query: str) -> Set[str]:
        q = query.lower()
        matched = set()
        for cat, keywords in CATEGORY_KEYWORDS.items():
            if any(kw in q for kw in keywords):
                matched.add(cat)
        return matched

    # ------------------------------------------------------------------
    # Main retrieval
    # ------------------------------------------------------------------
    def retrieve(self, query: str) -> list:
        """Return top-k relevant rules for the given query.
        
        Hỗ trợ tiếng Việt + tiếng Anh nhờ multilingual embedding.
        Áp category boost ×1.3 khi query khớp domain.
        """
        from sklearn.metrics.pairwise import cosine_similarity

        # Encode query → vector 384D (tự hiểu Việt + Anh)
        query_vec = self.model.encode([query])  # shape (1, 384)
        scores    = cosine_similarity(query_vec, self.embeddings).flatten()

        print(f"[RetrievalAgent] Query: '{query[:60]}'")

        # Apply category boost
        boosted_categories = self._detect_categories(query)
        if boosted_categories:
            print(f"[RetrievalAgent] Boosting categories: {boosted_categories}")
            for idx, entry in enumerate(self.metadata):
                if entry.get("category") in boosted_categories:
                    scores[idx] *= CATEGORY_BOOST

        top_indices = scores.argsort()[::-1][:self.top_k]
        results = []
        for idx in top_indices:
            entry = self.metadata[idx].copy()
            entry["score"]       = float(scores[idx])
            entry["rule_number"] = entry.get("rule_number", 0)
            entry["section"]     = entry.get("section", "General")
            entry["rule_title"]  = entry.get("rule_title", "")
            results.append(entry)
        return results
