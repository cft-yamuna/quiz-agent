class TaskPlanner:
    def __init__(self):
        self.tasks = []

    def update_tasks(self, tasks: list):
        """Replace the current task list with updated tasks from the agent."""
        self.tasks = tasks

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
