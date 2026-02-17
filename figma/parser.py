import json

# Keywords that indicate a node is a button or clickable element
BUTTON_KEYWORDS = {
    "button", "btn", "cta", "submit", "next", "start", "continue",
    "back", "login", "signup", "sign up", "sign in", "register",
    "play", "go", "send", "save", "cancel", "close", "menu",
    "nav", "link", "tab", "card",  "click", "action",
}


def extract_design_specs(figma_data: dict) -> str:
    """
    Parse Figma file data and extract design specifications
    that the agent can use to build the UI.
    Returns a formatted string with all design details.
    """
    file_name = figma_data.get("name", "Unknown")
    document = figma_data.get("document", {})
    pages = document.get("children", [])

    specs = {
        "file_name": file_name,
        "pages": [],
        "colors": set(),
        "fonts": set(),
        "font_sizes": set(),
        "components": [],
        "text_content": [],      # All text strings found
        "interactive_elements": [],  # Buttons, links, clickable items
    }

    for page in pages:
        page_info = {
            "name": page.get("name"),
            "frames": [],
        }

        for frame in page.get("children", []):
            frame_info = _extract_frame(frame, specs, frame_name=frame.get("name", ""))
            page_info["frames"].append(frame_info)

        specs["pages"].append(page_info)

    return _format_specs(specs)


def _extract_frame(node: dict, specs: dict, depth: int = 0, frame_name: str = "") -> dict:
    """Recursively extract design info from a frame/node."""
    node_name = node.get("name", "")
    node_type = node.get("type", "")

    frame_info = {
        "name": node_name,
        "type": node_type,
        "children": [],
    }

    # Extract dimensions
    bbox = node.get("absoluteBoundingBox", {})
    if bbox:
        frame_info["width"] = round(bbox.get("width", 0))
        frame_info["height"] = round(bbox.get("height", 0))

    # Extract colors from fills
    for fill in node.get("fills", []):
        if fill.get("type") == "SOLID" and fill.get("color"):
            color = fill["color"]
            r = round(color.get("r", 0) * 255)
            g = round(color.get("g", 0) * 255)
            b = round(color.get("b", 0) * 255)
            a = round(color.get("a", 1), 2)
            hex_color = f"#{r:02x}{g:02x}{b:02x}"
            specs["colors"].add(hex_color)
            frame_info["background_color"] = hex_color
        elif fill.get("type") == "GRADIENT_LINEAR":
            frame_info["has_gradient"] = True

    # Extract stroke colors
    for stroke in node.get("strokes", []):
        if stroke.get("type") == "SOLID" and stroke.get("color"):
            color = stroke["color"]
            r = round(color.get("r", 0) * 255)
            g = round(color.get("g", 0) * 255)
            b = round(color.get("b", 0) * 255)
            hex_color = f"#{r:02x}{g:02x}{b:02x}"
            specs["colors"].add(hex_color)

    # Extract typography
    style = node.get("style", {})
    if style:
        font = style.get("fontFamily")
        size = style.get("fontSize")
        weight = style.get("fontWeight")
        if font:
            specs["fonts"].add(font)
            frame_info["font"] = font
        if size:
            specs["font_sizes"].add(size)
            frame_info["font_size"] = size
        if weight:
            frame_info["font_weight"] = weight

    # Extract text content
    if node_type == "TEXT":
        chars = node.get("characters", "")
        frame_info["text"] = chars
        if chars.strip():
            specs["text_content"].append({
                "text": chars.strip(),
                "frame": frame_name,
                "font": frame_info.get("font", ""),
                "size": frame_info.get("font_size", ""),
                "weight": frame_info.get("font_weight", ""),
            })

    # Detect interactive/clickable elements (buttons, links, CTAs)
    name_lower = node_name.lower()
    is_interactive = (
        any(kw in name_lower for kw in BUTTON_KEYWORDS)
        or node.get("type") == "INSTANCE"  # Component instances are often interactive
        or (node.get("cornerRadius") and node.get("fills") and _has_text_child(node))
    )
    if is_interactive and depth > 0:
        button_text = _get_all_text(node)
        if button_text:
            specs["interactive_elements"].append({
                "name": node_name,
                "text": button_text,
                "frame": frame_name,
                "type": "button" if any(kw in name_lower for kw in {"button", "btn", "cta"}) else "clickable",
            })
            frame_info["interactive"] = True

    # Extract corner radius
    corner_radius = node.get("cornerRadius")
    if corner_radius:
        frame_info["border_radius"] = corner_radius

    # Extract layout info
    layout_mode = node.get("layoutMode")
    if layout_mode:
        frame_info["layout"] = layout_mode  # HORIZONTAL or VERTICAL
        frame_info["item_spacing"] = node.get("itemSpacing", 0)
        frame_info["padding_top"] = node.get("paddingTop", 0)
        frame_info["padding_right"] = node.get("paddingRight", 0)
        frame_info["padding_bottom"] = node.get("paddingBottom", 0)
        frame_info["padding_left"] = node.get("paddingLeft", 0)

    # Extract effects (shadows, blurs)
    for effect in node.get("effects", []):
        if effect.get("type") == "DROP_SHADOW":
            frame_info["has_shadow"] = True
        elif effect.get("type") == "LAYER_BLUR":
            frame_info["has_blur"] = True

    # Extract opacity
    opacity = node.get("opacity")
    if opacity is not None and opacity < 1:
        frame_info["opacity"] = round(opacity, 2)

    # Recurse into children (depth 8 to capture full hierarchy)
    if depth < 8:
        for child in node.get("children", []):
            child_info = _extract_frame(child, specs, depth + 1, frame_name=frame_name)
            frame_info["children"].append(child_info)

    return frame_info


def _has_text_child(node: dict) -> bool:
    """Check if a node has any TEXT child (indicating it might be a button)."""
    for child in node.get("children", []):
        if child.get("type") == "TEXT":
            return True
        if _has_text_child(child):
            return True
    return False


def _get_all_text(node: dict) -> str:
    """Get all text content from a node and its children."""
    texts = []
    if node.get("type") == "TEXT":
        chars = node.get("characters", "").strip()
        if chars:
            texts.append(chars)
    for child in node.get("children", []):
        texts.append(_get_all_text(child))
    return " ".join(t for t in texts if t)


def _format_specs(specs: dict) -> str:
    """Format extracted specs into a readable string for the agent."""
    lines = []
    lines.append(f"# Figma Design: {specs['file_name']}")
    lines.append("")

    # Colors
    colors = sorted(specs["colors"])
    if colors:
        lines.append(f"## Colors ({len(colors)} found)")
        for c in colors:
            lines.append(f"  - {c}")
        lines.append("")

    # Fonts
    fonts = sorted(specs["fonts"])
    if fonts:
        lines.append(f"## Fonts")
        for f in fonts:
            lines.append(f"  - {f}")
        lines.append("")

    # Font sizes
    sizes = sorted(specs["font_sizes"])
    if sizes:
        lines.append(f"## Font Sizes")
        lines.append(f"  {', '.join(str(int(s)) + 'px' for s in sizes)}")
        lines.append("")

    # All text content — so the agent uses the EXACT text from the design
    if specs.get("text_content"):
        lines.append("## Text Content (use these EXACT strings in the app)")
        by_frame = {}
        for t in specs["text_content"]:
            frame = t["frame"] or "Unknown"
            by_frame.setdefault(frame, []).append(t)
        for frame, texts in by_frame.items():
            lines.append(f"  ### {frame}")
            for t in texts:
                size_info = f" ({int(t['size'])}px)" if t.get("size") else ""
                lines.append(f"    - \"{t['text']}\"{size_info}")
        lines.append("")

    # Interactive elements — buttons, clickable items
    if specs.get("interactive_elements"):
        lines.append("## Interactive Elements (buttons, links, clickable items)")
        lines.append("  Each of these MUST be functional in the built app:")
        for el in specs["interactive_elements"]:
            lines.append(f"  - [{el['type'].upper()}] \"{el['text']}\" (in frame: {el['frame']}, layer: {el['name']})")
        lines.append("")
        lines.append("  IMPORTANT: If a button says 'Start Quiz', 'Next', 'Submit', etc.,")
        lines.append("  it must navigate to the correct next page/screen.")
        lines.append("  Map each button to the corresponding frame/page in the design.")
        lines.append("")

    # Page and frame structure
    lines.append("## Layout Structure")
    for page in specs["pages"]:
        lines.append(f"\n### Page: {page['name']}")
        for frame in page["frames"]:
            _format_frame(frame, lines, indent=1)

    return "\n".join(lines)


def _format_frame(frame: dict, lines: list, indent: int = 0):
    """Recursively format a frame into readable text."""
    prefix = "  " * indent
    name = frame.get("name", "")
    ftype = frame.get("type", "")

    # Build a concise description
    desc_parts = []
    if frame.get("width") and frame.get("height"):
        desc_parts.append(f"{frame['width']}x{frame['height']}")
    if frame.get("background_color"):
        desc_parts.append(f"bg:{frame['background_color']}")
    if frame.get("layout"):
        desc_parts.append(f"flex:{frame['layout'].lower()}")
    if frame.get("border_radius"):
        desc_parts.append(f"radius:{frame['border_radius']}px")
    if frame.get("font"):
        desc_parts.append(f"font:{frame['font']}")
    if frame.get("font_size"):
        desc_parts.append(f"{int(frame['font_size'])}px")
    if frame.get("has_shadow"):
        desc_parts.append("shadow")
    if frame.get("has_gradient"):
        desc_parts.append("gradient")

    desc = " | ".join(desc_parts) if desc_parts else ""

    # Text content
    text = frame.get("text", "")
    if text:
        text_preview = text[:60].replace("\n", " ")
        lines.append(f"{prefix}- [{ftype}] \"{text_preview}\" ({desc})")
    else:
        lines.append(f"{prefix}- [{ftype}] {name} ({desc})")

    # Children
    for child in frame.get("children", []):
        _format_frame(child, lines, indent + 1)
