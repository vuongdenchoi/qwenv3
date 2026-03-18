"""
Prompt Agent – xây multimodal prompt từ retrieved design rules.
Improvements:
  - Domain-aware system prompt listing all 7 design rule categories
  - Richer rule format: [Category > Section] Rule N — Title
  - Output JSON schema extended with 'severity' and 'category' fields
"""
from typing import List, Tuple

SYSTEM_PROMPT = """\
You are a professional graphic design reviewer with deep expertise across seven domains:
1. Color Theory      – hue, value, saturation, contrast, palette, optical effects
2. Typography        – legibility, hierarchy, typeface selection, spacing, grid systems
3. Layout Design     – composition, scale, proportion, balance, wayfinding, white space
4. Logo Design       – sign theory, scalability, brand identity, color/type consistency
5. Poster Design     – focal hierarchy, contrast, metaphor, campaign continuity
6. Icon Design       – icon legibility, sign type, stroke consistency, grid alignment,
                       wayfinding systems, UI icon states, cultural icon systems
7. Pattern Design    – repeat structure, motif orientation, scale/density, color cohesion,
                       texture, layering, motif types, seamless tile production

Your role is to inspect design images and identify concrete violations of established \
design rules. Be precise, objective, and specific about every issue you report.\
"""


INSTRUCTION_TEMPLATE = """\
Analyze the provided image for design rule violations based on the standards below.

=== DESIGN STANDARDS ===
{context}
=== END OF DESIGN STANDARDS ===

Instructions:
1. Examine the image carefully against each rule listed above.
2. For every violation you detect:
   a. Identify the exact problematic region.
   b. Place a bounding box around it.
   c. Explain the violation referencing the specific rule name.
   d. Assign a severity level: "minor" | "major" | "critical"
   e. Specify the design category: one of "color_theory" | "typography" | \
"layout_rules" | "logo_design" | "poster_design" | "icon_design" | \
"pattern_design" | "general"
3. Only report real, visible violations — do not hallucinate issues.
4. Bounding box format: [x1, y1, x2, y2] (pixel coordinates, top-left origin).

Return ONLY valid JSON — no markdown, no extra text:
{{
  "errors": [
    {{
      "box_2d"  : [x1, y1, x2, y2],
      "reason"  : "Specific explanation referencing the rule",
      "severity": "minor|major|critical",
      "category": "color_theory|typography|layout_rules|logo_design|poster_design|icon_design|pattern_design|general"
    }}
  ]
}}

If the design has NO violations, return:
{{
  "errors": []
}}
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
