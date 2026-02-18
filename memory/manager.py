import os
import json
import threading
from datetime import datetime

MEMORY_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "memory",
    "store",
)

MEMORY_FILES = {
    "projects": os.path.join(MEMORY_DIR, "projects.json"),
    "preferences": os.path.join(MEMORY_DIR, "preferences.json"),
    "knowledge": os.path.join(MEMORY_DIR, "knowledge.json"),
    "sessions": os.path.join(MEMORY_DIR, "sessions.json"),
}

MAX_SESSIONS = 50


class MemoryManager:
    def __init__(self):
        """Initialize memory directory and files if they don't exist."""
        os.makedirs(MEMORY_DIR, exist_ok=True)
        for filepath in MEMORY_FILES.values():
            if not os.path.exists(filepath):
                with open(filepath, "w") as f:
                    json.dump({}, f)
        # Per-category locks to prevent concurrent read/write corruption
        self._locks = {cat: threading.Lock() for cat in MEMORY_FILES}

    def _load(self, category: str) -> dict:
        """Load a memory category from disk. Returns empty dict on corruption."""
        try:
            with open(MEMORY_FILES[category], "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, ValueError) as e:
            print(f"  Warning: Corrupted memory file for '{category}': {e}. Resetting.")
            return {}
        except Exception as e:
            print(f"  Warning: Could not load memory '{category}': {e}")
            return {}

    def _save_file(self, category: str, data: dict):
        with open(MEMORY_FILES[category], "w") as f:
            json.dump(data, f, indent=2, default=str)

    def save(self, category: str, key: str, data: dict):
        """Save a key-value pair to the specified memory category."""
        with self._locks[category]:
            store = self._load(category)
            store[key] = {
                "data": data,
                "saved_at": datetime.now().isoformat(),
            }
            self._save_file(category, store)

    def search(self, query: str, category: str = "all") -> list:
        """
        Word-boundary search across memory stores.
        Splits query into words and matches each independently against keys and data.
        Results are ranked by number of matched words.
        """
        results = []
        query_words = [w.lower() for w in query.split() if len(w) > 1]
        if not query_words:
            return results

        categories = (
            [category]
            if category != "all"
            else ["projects", "preferences", "knowledge"]
        )

        for cat in categories:
            with self._locks[cat]:
                store = self._load(cat)
            for key, entry in store.items():
                searchable = f"{key} {json.dumps(entry.get('data', {}))}".lower()
                matched = sum(1 for w in query_words if w in searchable)
                if matched > 0:
                    results.append(
                        {
                            "category": cat,
                            "key": key,
                            "data": entry["data"],
                            "saved_at": entry.get("saved_at", "unknown"),
                            "_score": matched,
                        }
                    )

        # Sort by match score descending
        results.sort(key=lambda r: r["_score"], reverse=True)
        # Remove internal score field
        for r in results:
            del r["_score"]

        return results

    def get_relevant_context(self, user_input: str) -> str:
        """
        Search memory for anything relevant to the current user input.
        Returns a formatted string for injection into the system prompt.
        """
        results = self.search(user_input)
        if not results:
            return ""

        lines = []
        for r in results[:5]:
            lines.append(
                f"- [{r['category']}] {r['key']}: "
                f"{json.dumps(r['data'], indent=None)[:200]}"
            )
        return "\n".join(lines)

    def get_project_memory(self, project_name: str) -> dict:
        """Directly load project memory by key — no search needed."""
        with self._locks["projects"]:
            store = self._load("projects")
        entry = store.get(project_name)
        if entry:
            return entry.get("data", {})
        return {}

    def save_session(self, user_input: str, agent_response: str):
        """Log a completed session. Caps at MAX_SESSIONS entries."""
        with self._locks["sessions"]:
            sessions = self._load("sessions")

            # Use timestamp-based session ID
            session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            sessions[session_id] = {
                "data": {
                    "user_input": user_input[:500],
                    "agent_response": agent_response[:500],
                },
                "saved_at": datetime.now().isoformat(),
            }

            # Prune oldest sessions if over cap
            if len(sessions) > MAX_SESSIONS:
                sorted_keys = sorted(
                    sessions.keys(),
                    key=lambda k: sessions[k].get("saved_at", ""),
                )
                excess = len(sessions) - MAX_SESSIONS
                for old_key in sorted_keys[:excess]:
                    del sessions[old_key]

            self._save_file("sessions", sessions)
