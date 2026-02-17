"""
Screenshot validator using Playwright.
Takes screenshots of the running app and pairs them with Figma frame screenshots
for page-by-page visual comparison.
"""

import os
import re

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCREENSHOTS_DIR = os.path.join(BASE_DIR, "validation_screenshots")
FIGMA_CACHE_DIR = os.path.join(BASE_DIR, "figma", "cache")


def extract_routes_from_app(project_name: str) -> list:
    """
    Parse App.jsx to auto-detect routes defined in the React app.
    Returns a list of route paths (e.g., ["/", "/quiz", "/results"]).
    """
    app_jsx = os.path.join(BASE_DIR, "output", project_name, "src", "App.jsx")
    if not os.path.exists(app_jsx):
        return ["/"]

    with open(app_jsx, "r", encoding="utf-8") as f:
        content = f.read()

    # Match <Route path="..." /> patterns
    routes = re.findall(r'<Route\s+[^>]*path\s*=\s*["\']([^"\']+)["\']', content)

    # Also match path="..." in any route-like component
    if not routes:
        routes = re.findall(r'path\s*[=:]\s*["\']([^"\']+)["\']', content)

    # Ensure "/" is always first
    if "/" not in routes:
        routes.insert(0, "/")
    else:
        routes.remove("/")
        routes.insert(0, "/")

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for r in routes:
        if r not in seen:
            seen.add(r)
            unique.append(r)

    return unique


def take_screenshots(
    project_name: str,
    routes: list = None,
    base_url: str = "http://localhost:5173",
    viewport_width: int = 1440,
    viewport_height: int = 900,
) -> dict:
    """
    Use Playwright to take screenshots of each route in the running app.

    Returns dict with:
        "screenshots": {route: screenshot_path, ...}
        "errors": [error_messages]
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {
            "screenshots": {},
            "errors": ["Playwright not installed. Run: pip install playwright && playwright install chromium"],
        }

    # Auto-detect routes if not provided
    if not routes:
        routes = extract_routes_from_app(project_name)

    # Create screenshots directory per project
    project_screenshots = os.path.join(SCREENSHOTS_DIR, project_name)
    os.makedirs(project_screenshots, exist_ok=True)

    screenshots = {}
    errors = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": viewport_width, "height": viewport_height})

            for route in routes:
                url = f"{base_url}{route}"
                safe_name = route.replace("/", "_").strip("_") or "home"
                screenshot_path = os.path.join(project_screenshots, f"{safe_name}.png")

                try:
                    page.goto(url, wait_until="networkidle", timeout=15000)
                    # Wait for animations/transitions to settle
                    page.wait_for_timeout(1500)
                    page.screenshot(path=screenshot_path, full_page=True)
                    screenshots[route] = screenshot_path
                    print(f"  [Playwright] Screenshot: {route} -> {safe_name}.png")
                except Exception as e:
                    error_msg = f"Could not screenshot {route}: {str(e)}"
                    errors.append(error_msg)
                    print(f"  [Playwright] Error: {error_msg}")

            browser.close()

    except Exception as e:
        errors.append(f"Playwright error: {str(e)}")

    return {"screenshots": screenshots, "errors": errors}


def get_figma_frame_metadata() -> list:
    """
    Get Figma frame metadata for the CURRENT design from the manifest
    saved by fetch_figma_design. Only returns frames from the latest Figma fetch.
    Returns list of {"id": ..., "name": ..., "page": ..., "image_path": ...}
    """
    import json

    manifest_path = os.path.join(FIGMA_CACHE_DIR, "_current_frames.json")

    # Read manifest saved by fetch_figma_design
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r") as f:
                frames = json.load(f)
            # Verify image files still exist
            valid = []
            for frame in frames:
                if os.path.exists(frame.get("image_path", "")):
                    valid.append(frame)
            if valid:
                print(f"  [Validator] Loaded {len(valid)} Figma frames from manifest")
                return valid
        except Exception as e:
            print(f"  [Validator] Could not read frame manifest: {e}")

    # Fallback: try FigmaClient directly
    try:
        from figma.client import FigmaClient
        client = FigmaClient()
        frame_list = client.get_frame_ids()

        frames = []
        for frame in frame_list:
            safe_id = frame["id"].replace(":", "-")
            img_path = os.path.join(FIGMA_CACHE_DIR, f"{safe_id}.png")
            if os.path.exists(img_path):
                frames.append({
                    "id": frame["id"],
                    "name": frame.get("name", safe_id),
                    "page": frame.get("page", ""),
                    "image_path": img_path,
                })
        if frames:
            return frames
    except Exception as e:
        print(f"  [Validator] Could not get frames from FigmaClient: {e}")

    print("  [Validator] WARNING: No Figma frame data found. Run fetch_figma_design first.")
    return []


def validate(project_name: str, routes: list = None) -> dict:
    """
    Full validation flow:
    1. Take app screenshots via Playwright (one per route)
    2. Get Figma frame metadata with screenshot paths
    3. Build page-by-page comparison pairs
    4. Return structured data for the agent to compare

    Returns dict with:
        "pairs": [{"app_route": ..., "app_image": ..., "figma_name": ..., "figma_image": ...}, ...]
        "report": str (text summary for tool result)
        "image_paths": [ordered list - alternating figma,app for paired comparison]
    """
    print(f"  [Validator] Starting screenshot validation for '{project_name}'...")

    # 1. Take app screenshots
    result = take_screenshots(project_name, routes)
    app_shots = result["screenshots"]  # {route: path}
    errors = result["errors"]

    # 2. Get Figma frame metadata
    figma_frames = get_figma_frame_metadata()  # [{id, name, page, image_path}, ...]

    # 3. Build page-by-page pairs
    # Strategy: pair by order (frame 1 = route 1, frame 2 = route 2, etc.)
    # since Figma frames and app routes are usually in the same order
    app_routes = list(app_shots.keys())
    pairs = []
    all_image_paths = []

    num_pairs = min(len(app_routes), len(figma_frames))
    for i in range(num_pairs):
        route = app_routes[i]
        frame = figma_frames[i]
        pair = {
            "index": i + 1,
            "app_route": route,
            "app_image": app_shots[route],
            "figma_name": frame["name"],
            "figma_image": frame["image_path"],
        }
        pairs.append(pair)
        # Alternate: figma first, then app — so agent sees "target" then "actual"
        all_image_paths.append(frame["image_path"])
        all_image_paths.append(app_shots[route])

    # Add unpaired app screenshots (extra routes not in Figma)
    for i in range(num_pairs, len(app_routes)):
        route = app_routes[i]
        all_image_paths.append(app_shots[route])

    # Add unpaired Figma frames (pages not built yet)
    unpaired_figma = []
    for i in range(num_pairs, len(figma_frames)):
        frame = figma_frames[i]
        unpaired_figma.append(frame)
        all_image_paths.append(frame["image_path"])

    # 4. Build report
    lines = []
    lines.append("## Screenshot Validation Report")
    lines.append(f"Project: {project_name}")
    lines.append(f"App pages captured: {len(app_shots)}")
    lines.append(f"Figma frames found: {len(figma_frames)}")
    lines.append("")

    if pairs:
        lines.append("### Page-by-Page Comparison")
        lines.append("Images are sent in pairs: FIGMA (target) then APP (actual) for each page.")
        lines.append("")
        for pair in pairs:
            lines.append(
                f"  **Page {pair['index']}**: "
                f"Figma frame \"{pair['figma_name']}\" vs App route \"{pair['app_route']}\""
            )
            lines.append(f"    - Figma: {os.path.basename(pair['figma_image'])}")
            lines.append(f"    - App:   {os.path.basename(pair['app_image'])}")
        lines.append("")

    # Report extra app routes not matched to Figma
    if len(app_routes) > num_pairs:
        lines.append("### Extra App Routes (no matching Figma frame)")
        for i in range(num_pairs, len(app_routes)):
            lines.append(f"  - {app_routes[i]} → {os.path.basename(app_shots[app_routes[i]])}")
        lines.append("")

    # Report missing Figma frames (not built)
    if unpaired_figma:
        lines.append("### MISSING: Figma frames NOT built in the app")
        for frame in unpaired_figma:
            lines.append(f"  - \"{frame['name']}\" (id: {frame['id']}) — THIS PAGE IS MISSING, BUILD IT!")
        lines.append("")

    if errors:
        lines.append("### Errors")
        for err in errors:
            lines.append(f"  - {err}")
        lines.append("")

    lines.append(
        "For EACH page pair above, compare the FIGMA screenshot (target design) "
        "against the APP screenshot (what was built). Identify ALL differences in:\n"
        "  1. FONTS: wrong family, size, weight, line-height\n"
        "  2. COLORS: wrong text color, background, borders\n"
        "  3. LAYOUT: wrong spacing, alignment, flex direction, padding, gap\n"
        "  4. RADIUS: wrong border-radius\n"
        "  5. SHADOWS: missing or wrong\n"
        "  6. CONTENT: missing text, wrong text, missing elements\n"
        "  7. MISSING PAGES: build any Figma frames that don't have a corresponding route\n\n"
        "Fix ALL issues using create_file, then call validate_screenshots again."
    )

    report = "\n".join(lines)

    return {
        "pairs": pairs,
        "unpaired_figma": unpaired_figma,
        "app_screenshots": app_shots,
        "figma_frames": figma_frames,
        "report": report,
        "image_paths": all_image_paths,
    }
