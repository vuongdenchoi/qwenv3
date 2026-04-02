
"""
Build TF-IDF index từ design rules knowledge base.
Dùng scikit-learn TF-IDF – nhẹ, không cần PyTorch/sentence-transformers.
Chunking strategy: split per individual Rule block (one chunk = one rule).
"""
import sys
import re
import json
import pickle
import numpy as np
from typing import List, Tuple
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR   = SCRIPT_DIR.parent.parent
RULES_DIR  = ROOT_DIR / "design_rules"
INDEX_DIR  = SCRIPT_DIR / "faiss_index"
INDEX_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# 1. Load documents
# ---------------------------------------------------------------------------
def load_docs():
    docs = []
    for md_file in sorted(RULES_DIR.glob("*.md")):
        text = md_file.read_text(encoding="utf-8")
        docs.append({"category": md_file.stem, "text": text})
        print(f"  Loaded: {md_file.name} ({len(text)} chars)")
    return docs

# ---------------------------------------------------------------------------
# 2. Chunk documents — one chunk per Rule block
# ---------------------------------------------------------------------------
RULE_PATTERN = re.compile(
    r"(Rule\s+\d+\s*[—–-][^\n]+\n(?:(?!Rule\s+\d+\s*[—–-]).)*)",
    re.DOTALL,
)
SECTION_PATTERN = re.compile(r"^#{1,4}\s+(.+)$", re.MULTILINE)


def extract_section_map(text: str) -> List[Tuple[int, str]]:
    sections = []
    for m in SECTION_PATTERN.finditer(text):
        sections.append((m.start(), m.group(1).strip()))
    return sections


def find_section_for_pos(sections: List[Tuple[int, str]], pos: int) -> str:
    current = "General"
    for (sec_pos, sec_title) in sections:
        if sec_pos <= pos:
            current = sec_title
        else:
            break
    return current


def chunk_docs(docs: List[dict]) -> List[dict]:
    chunks = []
    for doc in docs:
        text     = doc["text"]
        category = doc["category"]
        sections = extract_section_map(text)
        rule_blocks = list(RULE_PATTERN.finditer(text))

        if rule_blocks:
            for m in rule_blocks:
                rule_text   = m.group(0).strip()
                num_match   = re.match(r"Rule\s+(\d+)", rule_text)
                rule_num    = int(num_match.group(1)) if num_match else 0
                title_match = re.match(r"Rule\s+\d+\s*[—–-]\s*(.+)", rule_text)
                rule_title  = title_match.group(1).strip() if title_match else ""
                section     = find_section_for_pos(sections, m.start())
                chunks.append({
                    "text"        : rule_text,
                    "category"    : category,
                    "section"     : section,
                    "rule_number" : rule_num,
                    "rule_title"  : rule_title,
                })
        else:
            paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
            buffer = ""
            for para in paragraphs:
                if len(buffer) + len(para) < 500:
                    buffer += "\n\n" + para
                else:
                    if buffer.strip():
                        chunks.append({"text": buffer.strip(), "category": category,
                                       "section": "General", "rule_number": 0, "rule_title": ""})
                    buffer = buffer[-50:] + "\n\n" + para
            if buffer.strip():
                chunks.append({"text": buffer.strip(), "category": category,
                               "section": "General", "rule_number": 0, "rule_title": ""})

    print(f"  Total chunks: {len(chunks)}")
    return chunks

# ---------------------------------------------------------------------------
# 3. Build TF-IDF index (thay thế sentence-transformers + faiss)
# ---------------------------------------------------------------------------
def build_tfidf_index(chunks: List[dict]):
    from sklearn.feature_extraction.text import TfidfVectorizer
    import scipy.sparse

    texts = [c["text"] for c in chunks]
    print(f"  Building TF-IDF index for {len(texts)} chunks...")
    vectorizer = TfidfVectorizer(
        max_features=10000,
        ngram_range=(1, 2),
        sublinear_tf=True,
        min_df=1,
    )
    matrix = vectorizer.fit_transform(texts)
    print(f"  TF-IDF matrix shape: {matrix.shape}")
    return vectorizer, matrix

# ---------------------------------------------------------------------------
# 4. Save index
# ---------------------------------------------------------------------------
def save_index(vectorizer, matrix, chunks: List[dict]):
    import scipy.sparse

    with open(INDEX_DIR / "tfidf_vectorizer.pkl", "wb") as f:
        pickle.dump(vectorizer, f)

    scipy.sparse.save_npz(str(INDEX_DIR / "tfidf_matrix.npz"), matrix)

    metadata = [
        {"id": i, "text": c["text"], "category": c["category"],
         "section": c["section"], "rule_number": c["rule_number"], "rule_title": c["rule_title"]}
        for i, c in enumerate(chunks)
    ]
    with open(INDEX_DIR / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    print(f"  Saved: tfidf_vectorizer.pkl | tfidf_matrix.npz | metadata.json")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=== Building Knowledge Base Index (TF-IDF) ===")
    print(f"  Rules dir : {RULES_DIR}")
    print(f"  Index dir : {INDEX_DIR}")

    print("\n[Step 1] Loading documents...")
    docs = load_docs()
    if not docs:
        print("ERROR: Không tìm thấy file markdown trong", RULES_DIR)
        sys.exit(1)

    print("\n[Step 2] Chunking documents (per-rule)...")
    chunks = chunk_docs(docs)

    print("\n[Step 3] Building TF-IDF index...")
    vectorizer, matrix = build_tfidf_index(chunks)

    print("\n[Step 4] Saving index...")
    save_index(vectorizer, matrix, chunks)

    print("\n[DONE] Index ready at:", INDEX_DIR)
    from collections import Counter
    cat_counts = Counter(c["category"] for c in chunks)
    print("\n  Chunks per category:")
    for cat, cnt in sorted(cat_counts.items()):
        print(f"    {cat}: {cnt} chunks")
