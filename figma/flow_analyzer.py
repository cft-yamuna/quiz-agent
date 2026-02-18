"""
Flow analyzer for Figma designs.
Determines screen navigation flow by analyzing frame order and interactive elements.
"""

import os
import json
import re


# Button text patterns that suggest navigation targets
_FORWARD_PATTERNS = [
    (r"\bstart\b", "next"),          # "Start Quiz", "Start", "Get Started"
    (r"\bbegin\b", "next"),
    (r"\bget started\b", "next"),
    (r"\bnext\b", "next"),
    (r"\bcontinue\b", "next"),
    (r"\bplay\b", "next"),
    (r"\bgo\b", "next"),
    (r"\blet'?s go\b", "next"),
    (r"\btake quiz\b", "next"),
]

_BACKWARD_PATTERNS = [
    (r"\bback\b", "previous"),
    (r"\bprevious\b", "previous"),
    (r"\breturn\b", "previous"),
]

_SUBMIT_PATTERNS = [
    (r"\bsubmit\b", "last"),
    (r"\bfinish\b", "last"),
    (r"\bcomplete\b", "last"),
    (r"\bdone\b", "last"),
    (r"\bsee results?\b", "last"),
    (r"\bshow results?\b", "last"),
    (r"\bview results?\b", "last"),
]

_RESTART_PATTERNS = [
    (r"\btry again\b", "first"),
    (r"\brestart\b", "first"),
    (r"\bretake\b", "first"),
    (r"\bplay again\b", "first"),
    (r"\bhome\b", "first"),
    (r"\breset\b", "first"),
]

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "figma", "cache")


def analyze_flow(frames: list, interactive_elements: list) -> dict:
    """
    Analyze Figma frames and interactive elements to determine app navigation flow.

    Args:
        frames: List of frame dicts with keys: id, name, page, (optional) x, y
        interactive_elements: List of dicts with keys: name, text, frame, type

    Returns:
        dict with keys:
            screens: List of screen dicts (name, frame_id, description, buttons)
            transitions: List of transition dicts (from, to, trigger)
            flow_text: Human-readable flow description
    """
    if not frames:
        return {
            "screens": [],
            "transitions": [],
            "flow_text": "No screens found in the Figma design.",
        }

    # Build screens list from frames
    screens = []
    for i, frame in enumerate(frames):
        # Collect buttons for this frame
        frame_buttons = [
            el for el in interactive_elements
            if el.get("frame", "").lower() == frame.get("name", "").lower()
        ]

        screen = {
            "index": i,
            "name": frame.get("name", f"Screen {i + 1}"),
            "frame_id": frame.get("id", ""),
            "buttons": [{"text": b["text"], "type": b.get("type", "clickable")} for b in frame_buttons],
            "description": _describe_screen(frame, frame_buttons),
        }
        screens.append(screen)

    # Determine transitions by analyzing button text
    transitions = _determine_transitions(screens)

    # Generate flow text
    flow_text = _generate_flow_text(screens, transitions)

    return {
        "screens": [
            {
                "name": s["name"],
                "frame_id": s["frame_id"],
                "description": s["description"],
                "buttons": s["buttons"],
            }
            for s in screens
        ],
        "transitions": transitions,
        "flow_text": flow_text,
    }


def _describe_screen(frame: dict, buttons: list) -> str:
    """Generate a brief description of a screen based on its name and buttons."""
    name = frame.get("name", "").lower()
    button_texts = [b["text"] for b in buttons]

    # Heuristic descriptions based on common screen names
    if any(kw in name for kw in ("home", "start", "landing", "welcome", "intro")):
        desc = "Landing/start screen"
    elif any(kw in name for kw in ("question", "quiz", "q1", "q2", "q3")):
        desc = "Quiz question screen"
    elif any(kw in name for kw in ("result", "score", "summary", "finish", "end", "complete")):
        desc = "Results/score screen"
    elif any(kw in name for kw in ("settings", "config", "option")):
        desc = "Settings screen"
    elif any(kw in name for kw in ("profile", "user", "account")):
        desc = "Profile screen"
    elif any(kw in name for kw in ("loading", "splash")):
        desc = "Loading screen"
    else:
        desc = "App screen"

    if button_texts:
        desc += f" with buttons: {', '.join(button_texts[:5])}"

    return desc


def _determine_transitions(screens: list) -> list:
    """Determine navigation transitions based on button text patterns."""
    transitions = []
    num_screens = len(screens)

    for screen in screens:
        idx = screen["index"]

        for button in screen.get("buttons", []):
            btn_text = button["text"].lower().strip()
            target = _match_button_target(btn_text, idx, num_screens)

            if target is not None and 0 <= target < num_screens:
                transitions.append({
                    "from": screen["name"],
                    "to": screens[target]["name"],
                    "trigger": f"{button['text']} button",
                })

    # If no transitions found, create a simple linear flow
    if not transitions and num_screens > 1:
        for i in range(num_screens - 1):
            transitions.append({
                "from": screens[i]["name"],
                "to": screens[i + 1]["name"],
                "trigger": "navigation (inferred)",
            })

    return transitions


def _match_button_target(btn_text: str, current_idx: int, total: int) -> int | None:
    """Match button text to a target screen index."""
    # Check forward patterns
    for pattern, action in _FORWARD_PATTERNS:
        if re.search(pattern, btn_text, re.IGNORECASE):
            if action == "next" and current_idx + 1 < total:
                return current_idx + 1
            return None

    # Check backward patterns
    for pattern, action in _BACKWARD_PATTERNS:
        if re.search(pattern, btn_text, re.IGNORECASE):
            if action == "previous" and current_idx > 0:
                return current_idx - 1
            return None

    # Check submit/finish patterns
    for pattern, action in _SUBMIT_PATTERNS:
        if re.search(pattern, btn_text, re.IGNORECASE):
            if action == "last":
                return total - 1
            return None

    # Check restart patterns
    for pattern, action in _RESTART_PATTERNS:
        if re.search(pattern, btn_text, re.IGNORECASE):
            if action == "first":
                return 0
            return None

    return None


def _generate_flow_text(screens: list, transitions: list) -> str:
    """Generate a human-readable flow description."""
    lines = []
    lines.append("=== APP FLOW ANALYSIS ===\n")

    # List all screens
    lines.append("SCREENS:")
    for i, screen in enumerate(screens):
        btn_info = ""
        if screen["buttons"]:
            btn_names = [b["text"] for b in screen["buttons"]]
            btn_info = f"  |  Buttons: {', '.join(btn_names)}"
        lines.append(f"  {i + 1}. {screen['name']} - {screen['description']}{btn_info}")

    lines.append("")

    # List transitions
    if transitions:
        lines.append("NAVIGATION FLOW:")
        for t in transitions:
            lines.append(f"  {t['from']}  --[{t['trigger']}]-->  {t['to']}")
    else:
        lines.append("NAVIGATION FLOW:")
        lines.append("  (No navigation detected - screens may be standalone)")

    lines.append("")

    # Visual flow summary
    if len(screens) > 1:
        lines.append("FLOW SUMMARY:")
        # Build linear path
        visited = set()
        flow_parts = []
        current = screens[0]["name"]
        flow_parts.append(current)
        visited.add(current)

        for _ in range(len(transitions)):
            next_screen = None
            trigger = None
            for t in transitions:
                if t["from"] == current and t["to"] not in visited:
                    next_screen = t["to"]
                    trigger = t["trigger"]
                    break
            if next_screen:
                flow_parts.append(f"--[{trigger}]-->")
                flow_parts.append(next_screen)
                visited.add(next_screen)
                current = next_screen
            else:
                break

        lines.append(f"  {' '.join(flow_parts)}")

        # Add any loop-back transitions
        loops = [t for t in transitions if t["to"] in visited and t["from"] in visited]
        if loops:
            lines.append("")
            lines.append("  LOOPS:")
            for t in loops:
                # Only show if it goes backward
                from_idx = next((s["index"] for s in screens if s["name"] == t["from"]), -1)
                to_idx = next((s["index"] for s in screens if s["name"] == t["to"]), -1)
                if to_idx < from_idx:
                    lines.append(f"    {t['from']} --[{t['trigger']}]--> {t['to']}")

    return "\n".join(lines)


def load_cached_flow() -> dict | None:
    """Load the confirmed flow from cache (saved after user confirmation)."""
    flow_path = os.path.join(CACHE_DIR, "_confirmed_flow.json")
    if os.path.exists(flow_path):
        try:
            with open(flow_path, "r") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def save_confirmed_flow(flow: dict) -> None:
    """Save the confirmed flow to cache for use during building."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    flow_path = os.path.join(CACHE_DIR, "_confirmed_flow.json")
    with open(flow_path, "w") as f:
        json.dump(flow, f, indent=2)
