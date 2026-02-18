"""Detect design/UI intent in user input for automatic Figma activation."""

import os
import re

# Short keywords that need word-boundary matching (to avoid "ui" matching in "quiz")
_SHORT_KEYWORDS = {"ui", "ux", "css"}

# Multi-word or longer keywords safe for substring matching
DESIGN_KEYWORDS = {
    # Direct design terms
    "design", "figma", "mockup", "wireframe", "prototype",
    "visual", "pixel-perfect", "pixel perfect",
    # Frontend/styling terms
    "styling", "theme", "color scheme", "color palette",
    "typography", "layout", "responsive", "gradient", "shadow",
    "border-radius", "rounded",
    # Component/page terms that imply visual work
    "landing page", "homepage", "dashboard", "navbar", "sidebar",
    "hero section", "footer", "header", "modal", "popup",
    # Adjectives that signal design intent
    "beautiful", "modern", "sleek", "elegant", "polished", "professional",
    "minimal", "stylish", "gorgeous", "stunning", "attractive",
    "good-looking", "good looking", "nice looking", "nice-looking", "pretty",
}

# Precompiled word-boundary patterns for short keywords
_SHORT_PATTERNS = [re.compile(rf"\b{kw}\b", re.IGNORECASE) for kw in _SHORT_KEYWORDS]

# Phrase patterns that strongly indicate design work
DESIGN_PHRASES = [
    r"match(?:ing)?\s+(?:the\s+)?design",
    r"look(?:s)?\s+like\s+(?:the\s+)?(?:design|mockup|figma)",
    r"follow(?:ing)?\s+(?:the\s+)?design",
    r"based\s+on\s+(?:the\s+)?(?:design|figma)",
    r"(?:make|build|create)\s+(?:it\s+)?(?:look|beautiful|pretty|modern)",
    r"exact(?:ly)?\s+(?:like|as)\s+(?:the\s+)?(?:design|figma)",
]


def has_design_intent(user_input: str) -> bool:
    """Check if user input indicates a design/UI/frontend task."""
    input_lower = user_input.lower()

    # Check longer keywords via substring match
    for kw in DESIGN_KEYWORDS:
        if kw in input_lower:
            return True

    # Check short keywords with word boundaries (avoids "ui" matching in "quiz")
    for pattern in _SHORT_PATTERNS:
        if pattern.search(user_input):
            return True

    # Check phrase patterns
    for pattern in DESIGN_PHRASES:
        if re.search(pattern, input_lower):
            return True

    return False


def is_figma_configured() -> bool:
    """Check if Figma credentials and URL are available."""
    has_token = bool(os.environ.get("FIGMA_ACCESS_TOKEN"))
    has_url = bool(os.environ.get("FIGMA_URL") or os.environ.get("FIGMA_FILE_KEY"))
    return has_token and has_url


def add_figma_hint(user_input: str) -> str:
    """
    Append Figma/design hint to user input based on config and intent.

    Three tiers:
    1. Figma configured + design intent -> Strong directive to use Figma FIRST
    2. Figma configured + no design intent -> Gentle reminder Figma is available
    3. No Figma + design intent -> Nudge toward polished UI design
    """
    # User already mentioned figma explicitly -- no hint needed
    if "figma" in user_input.lower():
        return user_input

    figma_configured = is_figma_configured()
    design_intent = has_design_intent(user_input)
    figma_url = os.environ.get("FIGMA_URL", "")

    if figma_configured and design_intent:
        hint = (
            "\n\n[SYSTEM DIRECTIVE: This is a design/UI task and a Figma design file is connected. "
            "You MUST call fetch_figma_design BEFORE writing any code. "
            "Build the app to match the Figma design EXACTLY — this is your #1 priority. "
            "Do NOT start coding until you have fetched and studied the design specs."
        )
        if "node-id=" in figma_url:
            hint += (
                " The Figma URL targets a SPECIFIC page/section — "
                "focus only on the frames returned."
            )
        hint += "]"
        user_input += hint

    elif figma_configured and not design_intent:
        hint = (
            "\n\n[System: A Figma design file is connected. "
            "Use fetch_figma_design to get design specs if you need visual reference."
        )
        if "node-id=" in figma_url:
            hint += " The URL targets a specific page/section."
        hint += "]"
        user_input += hint

    elif not figma_configured and design_intent:
        hint = (
            "\n\n[System: This appears to be a design/UI focused task. "
            "No Figma design file is connected. Apply strong visual design principles "
            "— create a polished, professional UI with consistent colors, typography, and spacing. "
            "Tip: For pixel-perfect results, the user can connect a Figma file by setting "
            "FIGMA_URL and FIGMA_ACCESS_TOKEN in .env or pasting a Figma link in their prompt.]"
        )
        user_input += hint

    return user_input
