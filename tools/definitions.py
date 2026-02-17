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
        "name": "create_files",
        "description": (
            "Create MULTIPLE files in one call. Much faster than calling create_file repeatedly. "
            "Use this to scaffold an entire React project at once (package.json, vite.config.js, "
            "index.html, src/main.jsx, src/App.jsx, components, etc.). "
            "PREFER this over create_file when creating 2+ files."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "files": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "File path relative to project root",
                            },
                            "content": {
                                "type": "string",
                                "description": "Full file content",
                            },
                        },
                        "required": ["path", "content"],
                    },
                    "description": "Array of files to create",
                }
            },
            "required": ["files"],
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
            "Run a shell command. Limited to safe commands only. "
            "npm install, npm run build are allowed. "
            "Dev servers (npm run dev, npm start) run in background automatically. "
            "Do NOT call 'npm run dev' until all files are created and npm install is done."
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
    {
        "name": "ask_user",
        "description": (
            "Ask the user a question and wait for their response. "
            "Use this when you need the user's input to decide what to do next — "
            "for example, whether to modify an existing project or create a new one. "
            "The tool returns the user's answer as a string."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The question to ask the user",
                }
            },
            "required": ["question"],
        },
    },
    {
        "name": "check_existing_projects",
        "description": (
            "Check the output/ directory for existing quiz projects. "
            "Returns a list of project names with their tech stack and file structure. "
            "ALWAYS call this FIRST before building anything. "
            "After getting results, use ask_user to ask whether to modify or create new."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "validate_screenshots",
        "description": (
            "Take screenshots of the running app using Playwright and compare them "
            "against the Figma design screenshots. The dev server MUST be running "
            "(call 'npm run dev' first). This tool captures every page/route of the "
            "built app, then sends both the app screenshots and Figma screenshots "
            "for visual comparison. Use this AFTER building and starting the dev server "
            "to verify design fidelity."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "project_name": {
                    "type": "string",
                    "description": "Name of the project in output/ directory (e.g., 'ai_chai_quiz')",
                },
                "routes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Optional: list of routes to screenshot (e.g., ['/', '/quiz', '/results']). "
                        "If not provided, routes are auto-detected from App.jsx."
                    ),
                },
            },
            "required": ["project_name"],
        },
    },
    {
        "name": "fetch_figma_design",
        "description": (
            "Fetch the design specifications from the connected Figma file. "
            "Returns colors, fonts, layout structure, component hierarchy, and frame screenshots. "
            "The Figma URL in .env may point to a specific page (via node-id) — "
            "in that case only that page's frames are returned. "
            "Use this FIRST when the user mentions Figma or wants to match a design. "
            "Call with no arguments to get the full design from the linked URL."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "page_name": {
                    "type": "string",
                    "description": "Optional: filter by page name (e.g., 'Home Page'). Usually not needed since the URL already targets a specific page.",
                }
            },
            "required": [],
        },
    },
]
