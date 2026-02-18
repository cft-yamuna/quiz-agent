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
        "typography_styles": [],   # Unique text style combinations (font, size, weight, line-height, etc.)
        "components": [],
        "text_content": [],        # All text strings found
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

    # Extract typography (full details)
    style = node.get("style", {})
    if style:
        font = style.get("fontFamily")
        size = style.get("fontSize")
        weight = style.get("fontWeight")
        line_height_px = style.get("lineHeightPx")
        letter_spacing = style.get("letterSpacing")
        text_align = style.get("textAlignHorizontal")  # LEFT, CENTER, RIGHT, JUSTIFIED
        text_decoration = style.get("textDecoration")   # UNDERLINE, STRIKETHROUGH
        text_case = style.get("textCase")               # UPPER, LOWER, TITLE, ORIGINAL
        italic = style.get("italic", False)

        if font:
            specs["fonts"].add(font)
            frame_info["font"] = font
        if size:
            specs["font_sizes"].add(size)
            frame_info["font_size"] = size
        if weight:
            frame_info["font_weight"] = weight
        if line_height_px:
            frame_info["line_height"] = round(line_height_px, 1)
        if letter_spacing and letter_spacing != 0:
            frame_info["letter_spacing"] = round(letter_spacing, 2)
        if text_align and text_align != "LEFT":
            frame_info["text_align"] = text_align.lower()
        if text_decoration:
            frame_info["text_decoration"] = text_decoration.lower()
        if text_case and text_case != "ORIGINAL":
            _case_map = {"UPPER": "uppercase", "LOWER": "lowercase", "TITLE": "capitalize"}
            frame_info["text_transform"] = _case_map.get(text_case, text_case.lower())
        if italic:
            frame_info["font_style"] = "italic"

    # Extract text content with full typography details
    if node_type == "TEXT":
        chars = node.get("characters", "")
        frame_info["text"] = chars
        if chars.strip():
            text_entry = {
                "text": chars.strip(),
                "frame": frame_name,
                "font": frame_info.get("font", ""),
                "size": frame_info.get("font_size", ""),
                "weight": frame_info.get("font_weight", ""),
                "line_height": frame_info.get("line_height", ""),
                "letter_spacing": frame_info.get("letter_spacing", ""),
                "text_align": frame_info.get("text_align", ""),
                "text_decoration": frame_info.get("text_decoration", ""),
                "text_transform": frame_info.get("text_transform", ""),
                "font_style": frame_info.get("font_style", ""),
                "color": frame_info.get("background_color", ""),
            }
            specs["text_content"].append(text_entry)

            # Collect unique typography style combinations
            style_key = (
                frame_info.get("font", ""),
                frame_info.get("font_size", ""),
                frame_info.get("font_weight", ""),
                frame_info.get("line_height", ""),
                frame_info.get("letter_spacing", ""),
                frame_info.get("font_style", ""),
            )
            if style_key not in [tuple(s.get("_key", ())) for s in specs["typography_styles"]]:
                style_entry = {k: v for k, v in {
                    "font_family": frame_info.get("font", ""),
                    "font_size": frame_info.get("font_size", ""),
                    "font_weight": frame_info.get("font_weight", ""),
                    "line_height": frame_info.get("line_height", ""),
                    "letter_spacing": frame_info.get("letter_spacing", ""),
                    "font_style": frame_info.get("font_style", ""),
                }.items() if v}
                style_entry["_key"] = style_key
                specs["typography_styles"].append(style_entry)

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

    # Extract corner radius (individual corners if different)
    corner_radius = node.get("cornerRadius")
    if corner_radius:
        frame_info["border_radius"] = corner_radius
    # Check for individual corner radii
    tl = node.get("rectangleCornerRadii")
    if tl and isinstance(tl, list) and len(tl) == 4:
        if len(set(tl)) > 1:  # Only if corners differ
            frame_info["border_radius_individual"] = {
                "top_left": tl[0], "top_right": tl[1],
                "bottom_right": tl[2], "bottom_left": tl[3]
            }

    # Extract layout info (auto-layout / flexbox)
    layout_mode = node.get("layoutMode")
    if layout_mode:
        frame_info["layout"] = layout_mode  # HORIZONTAL or VERTICAL
        frame_info["item_spacing"] = node.get("itemSpacing", 0)
        frame_info["padding_top"] = node.get("paddingTop", 0)
        frame_info["padding_right"] = node.get("paddingRight", 0)
        frame_info["padding_bottom"] = node.get("paddingBottom", 0)
        frame_info["padding_left"] = node.get("paddingLeft", 0)

        # Alignment → CSS justify-content / align-items
        primary_align = node.get("primaryAxisAlignItems", "")
        counter_align = node.get("counterAxisAlignItems", "")
        _justify_map = {"MIN": "flex-start", "CENTER": "center", "MAX": "flex-end", "SPACE_BETWEEN": "space-between"}
        _align_map = {"MIN": "flex-start", "CENTER": "center", "MAX": "flex-end", "BASELINE": "baseline"}
        if primary_align and primary_align in _justify_map:
            frame_info["justify_content"] = _justify_map[primary_align]
        if counter_align and counter_align in _align_map:
            frame_info["align_items"] = _align_map[counter_align]

        # Sizing modes
        primary_sizing = node.get("primaryAxisSizingMode", "")
        counter_sizing = node.get("counterAxisSizingMode", "")
        if primary_sizing == "FIXED":
            frame_info["main_axis_sizing"] = "fixed"
        elif primary_sizing == "AUTO":
            frame_info["main_axis_sizing"] = "hug-contents"
        if counter_sizing == "FIXED":
            frame_info["cross_axis_sizing"] = "fixed"
        elif counter_sizing == "AUTO":
            frame_info["cross_axis_sizing"] = "hug-contents"

        # Wrap mode
        layout_wrap = node.get("layoutWrap")
        if layout_wrap == "WRAP":
            frame_info["flex_wrap"] = "wrap"

    # Child layout properties (flex-grow, align-self)
    layout_grow = node.get("layoutGrow")
    if layout_grow and layout_grow > 0:
        frame_info["flex_grow"] = layout_grow
    layout_align = node.get("layoutAlign")
    if layout_align == "STRETCH":
        frame_info["align_self"] = "stretch"

    # Min/max constraints
    for prop in ("minWidth", "maxWidth", "minHeight", "maxHeight"):
        val = node.get(prop)
        if val is not None and val > 0:
            frame_info[prop] = round(val)

    # Extract effects (shadows with full details, blurs)
    for effect in node.get("effects", []):
        if effect.get("type") == "DROP_SHADOW" and effect.get("visible", True):
            shadow = {"type": "drop-shadow"}
            offset = effect.get("offset", {})
            shadow["x"] = round(offset.get("x", 0))
            shadow["y"] = round(offset.get("y", 0))
            shadow["blur"] = round(effect.get("radius", 0))
            shadow["spread"] = round(effect.get("spread", 0))
            color = effect.get("color", {})
            if color:
                r = round(color.get("r", 0) * 255)
                g = round(color.get("g", 0) * 255)
                b = round(color.get("b", 0) * 255)
                a = round(color.get("a", 1), 2)
                shadow["color"] = f"rgba({r}, {g}, {b}, {a})"
            frame_info["shadow"] = shadow
            frame_info["has_shadow"] = True
        elif effect.get("type") == "LAYER_BLUR":
            frame_info["has_blur"] = True
            frame_info["blur_radius"] = round(effect.get("radius", 0))

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

    # Typography Styles — CSS-ready unique text style combos
    if specs.get("typography_styles"):
        lines.append("## Typography Styles (use these EXACT CSS values)")
        lines.append("  Apply these styles precisely — do NOT approximate or round values:")
        for i, ts in enumerate(specs["typography_styles"], 1):
            css_parts = []
            if ts.get("font_family"):
                css_parts.append(f"font-family: '{ts['font_family']}'")
            if ts.get("font_size"):
                css_parts.append(f"font-size: {int(ts['font_size'])}px")
            if ts.get("font_weight"):
                css_parts.append(f"font-weight: {int(ts['font_weight'])}")
            if ts.get("line_height"):
                css_parts.append(f"line-height: {ts['line_height']}px")
            if ts.get("letter_spacing"):
                css_parts.append(f"letter-spacing: {ts['letter_spacing']}px")
            if ts.get("font_style"):
                css_parts.append(f"font-style: {ts['font_style']}")
            if css_parts:
                lines.append(f"  Style {i}: {'; '.join(css_parts)}")
        lines.append("")

    # All text content — with full typography for each string
    if specs.get("text_content"):
        lines.append("## Text Content (use EXACT strings AND EXACT styles)")
        by_frame = {}
        for t in specs["text_content"]:
            frame = t["frame"] or "Unknown"
            by_frame.setdefault(frame, []).append(t)
        for frame, texts in by_frame.items():
            lines.append(f"  ### {frame}")
            for t in texts:
                # Build CSS hint for this text element
                css_hints = []
                if t.get("font"):
                    css_hints.append(f"font-family: '{t['font']}'")
                if t.get("size"):
                    css_hints.append(f"font-size: {int(t['size'])}px")
                if t.get("weight"):
                    css_hints.append(f"font-weight: {int(t['weight'])}")
                if t.get("line_height"):
                    css_hints.append(f"line-height: {t['line_height']}px")
                if t.get("letter_spacing"):
                    css_hints.append(f"letter-spacing: {t['letter_spacing']}px")
                if t.get("text_align"):
                    css_hints.append(f"text-align: {t['text_align']}")
                if t.get("text_decoration"):
                    css_hints.append(f"text-decoration: {t['text_decoration']}")
                if t.get("text_transform"):
                    css_hints.append(f"text-transform: {t['text_transform']}")
                if t.get("font_style"):
                    css_hints.append(f"font-style: {t['font_style']}")
                if t.get("color"):
                    css_hints.append(f"color: {t['color']}")
                css_str = f" → CSS: {'; '.join(css_hints)}" if css_hints else ""
                lines.append(f"    - \"{t['text']}\"{css_str}")
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


def extract_frames_summary(figma_data: dict) -> tuple:
    """
    Extract frame metadata and interactive elements in a structured format
    suitable for flow analysis.

    Returns:
        (frames, interactive_elements) where:
        - frames: list of {"id", "name", "page", "x", "y", "width", "height"}
        - interactive_elements: list of {"name", "text", "frame", "type"}
    """
    document = figma_data.get("document", {})
    pages = document.get("children", [])

    frames = []
    interactive_elements = []

    for page in pages:
        page_name = page.get("name", "")
        for frame_node in page.get("children", []):
            if frame_node.get("type") != "FRAME":
                continue

            bbox = frame_node.get("absoluteBoundingBox", {})
            frames.append({
                "id": frame_node.get("id", ""),
                "name": frame_node.get("name", ""),
                "page": page_name,
                "x": bbox.get("x", 0),
                "y": bbox.get("y", 0),
                "width": round(bbox.get("width", 0)),
                "height": round(bbox.get("height", 0)),
            })

            # Collect interactive elements from this frame
            _collect_interactive(frame_node, frame_node.get("name", ""), interactive_elements)

    # Sort frames by position: top-to-bottom, then left-to-right
    frames.sort(key=lambda f: (round(f["y"] / 100), f["x"]))

    return frames, interactive_elements


def _collect_interactive(node: dict, frame_name: str, elements: list, depth: int = 0):
    """Recursively collect interactive elements from a node tree."""
    if depth > 8:
        return

    name_lower = node.get("name", "").lower()
    is_interactive = (
        any(kw in name_lower for kw in BUTTON_KEYWORDS)
        or node.get("type") == "INSTANCE"
        or (node.get("cornerRadius") and node.get("fills") and _has_text_child(node))
    )

    if is_interactive and depth > 0:
        text = _get_all_text(node)
        if text:
            elements.append({
                "name": node.get("name", ""),
                "text": text,
                "frame": frame_name,
                "type": "button" if any(kw in name_lower for kw in {"button", "btn", "cta"}) else "clickable",
            })

    for child in node.get("children", []):
        _collect_interactive(child, frame_name, elements, depth + 1)


def _format_frame(frame: dict, lines: list, indent: int = 0):
    """Recursively format a frame into readable text with CSS-ready values."""
    prefix = "  " * indent
    name = frame.get("name", "")
    ftype = frame.get("type", "")

    # Build CSS-ready description
    desc_parts = []
    if frame.get("width") and frame.get("height"):
        desc_parts.append(f"width: {frame['width']}px; height: {frame['height']}px")
    if frame.get("background_color"):
        desc_parts.append(f"background: {frame['background_color']}")
    if frame.get("has_gradient"):
        desc_parts.append("background: linear-gradient(...)")

    # Layout as CSS flexbox
    if frame.get("layout"):
        direction = "row" if frame["layout"] == "HORIZONTAL" else "column"
        flex_css = f"display: flex; flex-direction: {direction}"
        if frame.get("item_spacing"):
            flex_css += f"; gap: {frame['item_spacing']}px"
        if frame.get("justify_content"):
            flex_css += f"; justify-content: {frame['justify_content']}"
        if frame.get("align_items"):
            flex_css += f"; align-items: {frame['align_items']}"
        if frame.get("flex_wrap"):
            flex_css += f"; flex-wrap: {frame['flex_wrap']}"
        desc_parts.append(flex_css)

        # Padding as CSS shorthand
        pt = frame.get("padding_top", 0)
        pr = frame.get("padding_right", 0)
        pb = frame.get("padding_bottom", 0)
        pl = frame.get("padding_left", 0)
        if any([pt, pr, pb, pl]):
            if pt == pb and pl == pr:
                if pt == pl:
                    desc_parts.append(f"padding: {pt}px")
                else:
                    desc_parts.append(f"padding: {pt}px {pr}px")
            else:
                desc_parts.append(f"padding: {pt}px {pr}px {pb}px {pl}px")

    # Flex child properties
    if frame.get("flex_grow"):
        desc_parts.append(f"flex-grow: {frame['flex_grow']}")
    if frame.get("align_self"):
        desc_parts.append(f"align-self: {frame['align_self']}")

    # Border radius
    if frame.get("border_radius_individual"):
        r = frame["border_radius_individual"]
        desc_parts.append(
            f"border-radius: {r['top_left']}px {r['top_right']}px "
            f"{r['bottom_right']}px {r['bottom_left']}px"
        )
    elif frame.get("border_radius"):
        desc_parts.append(f"border-radius: {frame['border_radius']}px")

    # Shadow as CSS
    if frame.get("shadow"):
        s = frame["shadow"]
        desc_parts.append(
            f"box-shadow: {s.get('x', 0)}px {s.get('y', 0)}px "
            f"{s.get('blur', 0)}px {s.get('spread', 0)}px {s.get('color', 'rgba(0,0,0,0.25)')}"
        )
    elif frame.get("has_shadow"):
        desc_parts.append("box-shadow: (present)")

    # Typography as CSS
    font_css_parts = []
    if frame.get("font"):
        font_css_parts.append(f"font-family: '{frame['font']}'")
    if frame.get("font_size"):
        font_css_parts.append(f"font-size: {int(frame['font_size'])}px")
    if frame.get("font_weight"):
        font_css_parts.append(f"font-weight: {int(frame['font_weight'])}")
    if frame.get("line_height"):
        font_css_parts.append(f"line-height: {frame['line_height']}px")
    if frame.get("letter_spacing"):
        font_css_parts.append(f"letter-spacing: {frame['letter_spacing']}px")
    if frame.get("text_align"):
        font_css_parts.append(f"text-align: {frame['text_align']}")
    if frame.get("font_style"):
        font_css_parts.append(f"font-style: {frame['font_style']}")
    if font_css_parts:
        desc_parts.append("; ".join(font_css_parts))

    # Opacity
    if frame.get("opacity"):
        desc_parts.append(f"opacity: {frame['opacity']}")

    # Size constraints
    for prop, css_prop in [("minWidth", "min-width"), ("maxWidth", "max-width"),
                           ("minHeight", "min-height"), ("maxHeight", "max-height")]:
        if frame.get(prop):
            desc_parts.append(f"{css_prop}: {frame[prop]}px")

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
