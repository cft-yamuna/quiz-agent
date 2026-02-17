"""
Tool definitions in Gemini function calling format.
Each tool is a dict with name, description, and parameters.
"""

TOOL_DEFINITIONS = [
    {
        "name": "create_file",
        "description": (
            "Create or overwrite a file at the specified path with the given content. "
            "Parent directories are created automatically. "
            "Use this to generate quiz app files (HTML, CSS, JS)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path relative to the project root (e.g., 'output/my-quiz/index.html')",
                },
                "content": {
                    "type": "string",
                    "description": "The full content to write to the file",
                },
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "read_file",
        "description": (
            "Read the contents of a file. "
            "Use this to review generated code or check existing files."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path to read",
                }
            },
            "required": ["path"],
        },
    },
    {
        "name": "list_files",
        "description": "List all files and subdirectories in a directory.",
        "parameters": {
            "type": "object",
            "properties": {
                "directory": {
                    "type": "string",
                    "description": "Directory path to list (defaults to project root)",
                }
            },
            "required": ["directory"],
        },
    },
    {
        "name": "run_command",
        "description": (
            "Run a shell command. Limited to safe commands only "
            "(ls, cat, python -m http.server, etc.). Dangerous commands are blocked."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Shell command to execute",
                }
            },
            "required": ["command"],
        },
    },
    {
        "name": "search_memory",
        "description": (
            "Search past projects, learned patterns, and user preferences. "
            "Returns relevant matches from the agent's long-term memory."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (e.g., 'trivia quiz', 'dark theme', 'timer feature')",
                },
                "category": {
                    "type": "string",
                    "enum": ["projects", "preferences", "knowledge", "all"],
                    "description": "Which memory store to search. Defaults to 'all'.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "save_memory",
        "description": (
            "Save information to long-term memory for future sessions. "
            "Use this after completing a project to remember what was built, "
            "or to save learned patterns and user preferences."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["projects", "preferences", "knowledge"],
                    "description": "Which memory store to save to",
                },
                "key": {
                    "type": "string",
                    "description": "Unique identifier (e.g., project name, preference name)",
                },
                "data": {
                    "type": "object",
                    "description": "The data to store (any JSON-serializable object)",
                },
            },
            "required": ["category", "key", "data"],
        },
    },
    {
        "name": "plan_tasks",
        "description": (
            "Create or update a task plan for the current project. "
            "Break down the user's requirements into discrete, ordered tasks."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "tasks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {
                                "type": "string",
                                "description": "Unique task identifier (e.g., 'task_1')",
                            },
                            "description": {
                                "type": "string",
                                "description": "What needs to be done",
                            },
                            "depends_on": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "IDs of tasks that must complete first",
                            },
                            "status": {
                                "type": "string",
                                "enum": [
                                    "pending",
                                    "in_progress",
                                    "completed",
                                    "failed",
                                ],
                                "description": "Current status",
                            },
                        },
                        "required": ["id", "description", "status"],
                    },
                    "description": "List of tasks",
                }
            },
            "required": ["tasks"],
        },
    },
    {
        "name": "preview_app",
        "description": "Open the generated quiz app in the user's default web browser.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the index.html file to open",
                }
            },
            "required": ["path"],
        },
    },
]
