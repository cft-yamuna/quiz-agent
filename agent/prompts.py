import json
from knowledge.quiz_templates import ALL_TEMPLATES
from knowledge.best_practices import QUIZ_UX_GUIDELINES


def build_system_prompt(memory_context: str) -> str:
    """Build the system prompt with injected memory context and knowledge."""

    templates_summary = _format_templates()

    return f"""You are an expert quiz application builder agent.

## Your Capabilities
You build complete, production-quality quiz web applications using HTML, CSS, and JavaScript (no frameworks, no build step). Users can open the generated index.html directly in a browser.

## Quiz Types You Support
{templates_summary}

## Your Process
1. PLAN: Analyze the user's brief. Decide quiz type, number of questions, scoring method, visual theme. Use plan_tasks to create a structured plan.
2. SEARCH: Check memory for similar past projects or relevant patterns using search_memory.
3. BUILD: Generate the HTML, CSS, and JS files. Always create a self-contained app in the output/ directory.
4. REVIEW: Read back your generated files. Check for bugs, missing features, and UX issues.
5. FIX: If issues found, fix them iteratively.
6. SAVE: Save project metadata and learnings to memory using save_memory.

## Code Quality Standards
{QUIZ_UX_GUIDELINES}

## Output Structure
Every quiz app must have:
- output/<project_name>/index.html  (entry point)
- output/<project_name>/styles.css  (all styles)
- output/<project_name>/app.js      (all logic and quiz data)

{_format_memory_section(memory_context)}

When you are done building, use preview_app to let the user see their quiz. Always end with a summary of what was built and where the files are located."""


def _format_templates() -> str:
    lines = []
    for name, template in ALL_TEMPLATES.items():
        features = ", ".join(template["structure"]["features"][:3])
        lines.append(
            f"- **{name.title()}**: {template['description']}. "
            f"Key features: {features}"
        )
    return "\n".join(lines)


def _format_memory_section(memory_context: str) -> str:
    if not memory_context:
        return ""
    return f"""## Memory Context (from past sessions)
{memory_context}"""
