import os
import json
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


class MemoryManager:
    def __init__(self):
        """Initialize memory directory and files if they don't exist."""
        os.makedirs(MEMORY_DIR, exist_ok=True)
        for filepath in MEMORY_FILES.values():
            if not os.path.exists(filepath):
                with open(filepath, "w") as f:
                    json.dump({}, f)

    def _load(self, category: str) -> dict:
        with open(MEMORY_FILES[category], "r") as f:
            return json.load(f)

    def _save_file(self, category: str, data: dict):
        with open(MEMORY_FILES[category], "w") as f:
            json.dump(data, f, indent=2, default=str)

    def save(self, category: str, key: str, data: dict):
        """Save a key-value pair to the specified memory category."""
        store = self._load(category)
        store[key] = {
            "data": data,
            "saved_at": datetime.now().isoformat(),
        }
        self._save_file(category, store)

    def search(self, query: str, category: str = "all") -> list:
        """
        Simple keyword search across memory stores.
        Returns list of matching entries.
        """
        results = []
        query_lower = query.lower()

        categories = (
            [category]
            if category != "all"
            else ["projects", "preferences", "knowledge"]
        )

        for cat in categories:
            store = self._load(cat)
            for key, entry in store.items():
                searchable = f"{key} {json.dumps(entry.get('data', {}))}"
                if query_lower in searchable.lower():
                    results.append(
                        {
                            "category": cat,
                            "key": key,
                            "data": entry["data"],
                            "saved_at": entry.get("saved_at", "unknown"),
                        }
                    )

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

    def save_session(self, user_input: str, agent_response: str):
        """Log a completed session."""
        sessions = self._load("sessions")
        session_id = f"session_{len(sessions) + 1}"
        sessions[session_id] = {
            "data": {
                "user_input": user_input[:500],
                "agent_response": agent_response[:500],
            },
            "saved_at": datetime.now().isoformat(),
        }
        self._save_file("sessions", sessions)
