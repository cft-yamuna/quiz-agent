class TaskPlanner:
    def __init__(self):
        self.tasks = []

    def update_tasks(self, tasks: list):
        """Replace the current task list with updated tasks from the agent."""
        self.tasks = tasks

    def current_phase(self) -> str:
        """
        Determine what phase the agent is in based on task statuses.
        Used by model selection to choose the right Claude model.
        """
        if not self.tasks:
            return "planning"

        in_progress = [t for t in self.tasks if t.get("status") == "in_progress"]

        if not in_progress:
            all_done = all(
                t.get("status") in ("completed", "failed") for t in self.tasks
            )
            if all_done:
                return "file_ops"
            return "planning"

        current = in_progress[0]
        desc_lower = current["description"].lower()

        if any(w in desc_lower for w in ["plan", "architect", "decide"]):
            return "planning"
        elif any(w in desc_lower for w in ["figma", "design spec", "fetch design", "visual reference"]):
            return "designing"
        elif any(w in desc_lower for w in ["screenshot", "compare", "visual check"]):
            return "validating"
        elif any(w in desc_lower for w in ["review", "check", "validate", "test"]):
            return "reviewing"
        elif any(w in desc_lower for w in ["fix", "debug", "repair", "correct", "css fix", "style fix"]):
            return "fixing"
        elif any(w in desc_lower for w in ["create", "generate", "write", "build"]):
            return "generating"
        else:
            return "generating"

    def get_status_report(self) -> str:
        """Return a human-readable status of all tasks."""
        if not self.tasks:
            return "No tasks planned yet."

        lines = ["Task Plan:"]
        status_icons = {
            "pending": "[ ]",
            "in_progress": "[~]",
            "completed": "[x]",
            "failed": "[!]",
        }

        for t in self.tasks:
            icon = status_icons.get(t["status"], "[?]")
            deps = ""
            if t.get("depends_on"):
                deps = f" (depends on: {', '.join(t['depends_on'])})"
            lines.append(f"  {icon} {t['id']}: {t['description']}{deps}")

        completed = sum(1 for t in self.tasks if t["status"] == "completed")
        total = len(self.tasks)
        lines.append(f"\nProgress: {completed}/{total} tasks completed")

        return "\n".join(lines)
