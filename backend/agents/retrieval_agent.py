"""
Retrieval Agent – tìm design rules liên quan dùng TF-IDF (scikit-learn).
Nhẹ hơn sentence-transformers ~10x, không cần PyTorch.
Category boost ×1.3 vẫn giữ nguyên.
"""
import json
import pickle
from typing import List, Dict, Set
from pathlib import Path

INDEX_DIR = Path(__file__).resolve().parent.parent / "knowledge_base" / "faiss_index"

# Map query keywords → category names (dùng để boost score)
CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "color_theory"  : ["color", "colour", "hue", "saturation", "contrast", "palette",
                        "rgb", "cmyk", "tint", "shade", "complementary", "analogous",
                        "warm", "cool", "vibration", "value",
                        "màu", "màu sắc", "tương phản", "bảng màu", "độ bão hòa"],
    "typography"    : ["typography", "typeface", "font", "serif", "sans", "type",
                        "leading", "kerning", "tracking", "legibility", "readability",
                        "headline", "body text", "letter", "glyph", "weight",
                        "chữ", "font chữ", "kiểu chữ", "cỡ chữ", "dễ đọc"],
    "layout_rules"  : ["layout", "grid", "composition", "margin", "spacing", "alignment",
                        "column", "proximity", "whitespace", "white space", "hierarchy",
                        "balance", "symmetry", "asymmetry", "direction", "wayfinding",
                        "bố cục", "lưới", "khoảng trắng", "căn chỉnh", "cân bằng"],
    "logo_design"   : ["logo", "logotype", "brand", "identity", "mark", "monogram",
                        "wordmark", "branding", "graphic identity", "exclusion zone",
                        "thương hiệu", "nhận diện"],
    "poster_design" : ["poster", "advertisement", "billboard", "campaign", "print",
                        "focal", "visual noise", "outdoor", "format", "signage",
                        "áp phích", "quảng cáo", "tờ rơi"],
    "icon_design"   : ["icon", "pictogram", "symbol", "wayfinding", "glyph",
                        "ui icon", "sign", "pictograph", "stroke weight", "icon set",
                        "icon system", "monochrome icon", "icon grid", "legibility",
                        "icon style", "navigation icon", "app icon", "ui symbol",
                        "biểu tượng", "icon"],
    "pattern_design": ["pattern", "motif", "repeat", "tile", "tiling", "textile",
                        "half-drop", "brick repeat", "mirrored repeat", "tossed",
                        "surface design", "print design", "seamless", "density",
                        "ditsy", "floral pattern", "geometric pattern", "folk pattern",
                        "họa tiết", "hoa văn", "lặp lại"],
}

CATEGORY_BOOST = 1.3


class RetrievalAgent:
    def __init__(self, top_k: int = 10):
        self.top_k = top_k
        self._load_index()

    def _load_index(self):
        """Load TF-IDF vectorizer, matrix và metadata từ disk."""
        vec_path  = INDEX_DIR / "tfidf_vectorizer.pkl"
        mat_path  = INDEX_DIR / "tfidf_matrix.npz"
        meta_path = INDEX_DIR / "metadata.json"

        if not vec_path.exists():
            raise FileNotFoundError(
                f"TF-IDF index không tìm thấy tại {INDEX_DIR}. "
                "Chạy backend/knowledge_base/build_index.py trước."
            )

        import scipy.sparse
        with open(vec_path, "rb") as f:
            self.vectorizer = pickle.load(f)

        self.matrix = scipy.sparse.load_npz(str(mat_path))

        with open(meta_path, encoding="utf-8") as f:
            self.metadata = json.load(f)

        print(f"[RetrievalAgent] Loaded TF-IDF index: {self.matrix.shape[0]} chunks, "
              f"vocab={self.matrix.shape[1]}")

    def _detect_categories(self, query: str) -> Set[str]:
        q = query.lower()
        matched = set()
        for cat, keywords in CATEGORY_KEYWORDS.items():
            if any(kw in q for kw in keywords):
                matched.add(cat)
        return matched

    def retrieve(self, query: str) -> list:
        """Return top-k relevant rules for the given query using TF-IDF cosine similarity."""
        from sklearn.metrics.pairwise import cosine_similarity

        query_vec = self.vectorizer.transform([query])          # sparse (1, vocab)
        scores    = cosine_similarity(query_vec, self.matrix).flatten()

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
