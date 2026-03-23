"""
Prompt Agent – xây multimodal prompt từ retrieved design rules.
Improvements:
  - Domain-aware system prompt listing all 7 design rule categories
  - Richer rule format: [Category > Section] Rule N — Title
  - Output JSON schema extended with 'severity' and 'category' fields
"""
from typing import List, Tuple

SYSTEM_PROMPT = """\
You are a strict, professional graphic design critic and quality reviewer. You have deep expertise across seven design domains:
1. Color Theory      – hue, value, saturation, contrast ratio, palette harmony, optical effects
2. Typography        – legibility, hierarchy, typeface selection, font mixing, spacing, readability
3. Layout Design     – composition, scale, proportion, balance, visual hierarchy, white space
4. Logo Design       – sign theory, scalability, brand identity, color/type consistency
5. Poster Design     – focal hierarchy, contrast, visual noise, campaign continuity, readability at distance
6. Icon Design       – icon legibility, sign type, stroke consistency, grid alignment, cultural icon systems
7. Pattern Design    – repeat structure, motif orientation, scale/density, color cohesion, seamless production

You MUST critically evaluate every image as a design professional would. Even casual or informal designs must meet basic design principles. Your job is to find and report ALL violations — do not skip issues just because a design appears intentional or "decorative." Report every concrete, visible problem you detect.\
"""


INSTRUCTION_TEMPLATE = """\
You are reviewing the provided image for design quality issues. Apply the design standards below strictly.

=== DESIGN STANDARDS ===
{context}
=== END OF DESIGN STANDARDS ===

Instructions:
1. Examine the ENTIRE image carefully against EACH rule listed above.
2. This image may be a poster, social media graphic, greeting card, flyer, or any visual design — treat it as a design artifact that must follow professional standards.
3. For EVERY violation you find:
   a. Identify the exact problematic region with a tight bounding box.
   b. Explain the violation clearly, referencing the specific rule name.
   c. Assign severity: "minor" | "major" | "critical"
   d. Assign category: "color_theory" | "typography" | "layout_rules" | "logo_design" | "poster_design" | "icon_design" | "pattern_design" | "general"
4. Common issues to actively look for:
   - Mixed fonts / too many typefaces (typography)
   - Poor contrast between text and background (color_theory)
   - Cluttered composition / no clear focal point (layout_rules / poster_design)
   - Hard-to-read decorative/script fonts at small sizes (typography)
   - Lack of visual hierarchy (layout_rules)
   - Conflicting color schemes (color_theory)
   - Overcrowded layout with insufficient whitespace (layout_rules)
5. Bounding box format: [x1, y1, x2, y2] in pixel coordinates (top-left origin).

Return ONLY valid JSON — no markdown, no extra text:
{{
  "e": [
    {{
      "c": [x1, y1, x2, y2],
      "r": "Specific explanation referencing the rule",
      "s": "minor|major|critical",
      "g": "color_theory|typography|layout_rules|logo_design|poster_design|icon_design|pattern_design|general"
    }}
  ]
}}

If after thorough inspection the design truly has NO violations at all, return {{"e": []}}.
"""



class PromptAgent:
    def build_prompt(self, retrieved_rules: List[dict]) -> Tuple[str, str]:
        """
        Build system prompt and user instruction from retrieved rules.

        Returns:
            (system_prompt, instruction_text)
        """
        context_lines = []
        for rule in retrieved_rules:
            category    = rule.get("category", "general").replace("_", " ").title()
            section     = rule.get("section", "General")
            rule_num    = rule.get("rule_number", 0)
            rule_title  = rule.get("rule_title", "")
            text        = rule["text"].strip()

            # Header: [Category > Section] Rule N — Title
            if rule_num and rule_title:
                header = f"[{category} > {section}] Rule {rule_num} — {rule_title}"
            elif rule_num:
                header = f"[{category} > {section}] Rule {rule_num}"
            else:
                header = f"[{category} > {section}]"

            context_lines.append(f"{header}\n{text}")

        context     = "\n\n---\n\n".join(context_lines)
        instruction = INSTRUCTION_TEMPLATE.format(context=context)

        return SYSTEM_PROMPT, instruction
