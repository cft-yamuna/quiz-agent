"""Tests for agent.context — the shared context builder."""

import json
import os
import tempfile

import pytest

from agent.context import build_prompt_context


@pytest.fixture
def tmp_base(tmp_path):
    """Create a temporary base dir with an output/ directory."""
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    return tmp_path


def _make_project(base_dir, name, *, files=None, memory=None, chat=None):
    """Helper: scaffold a fake project under output/<name>/."""
    project_dir = os.path.join(str(base_dir), "output", name)
    src_dir = os.path.join(project_dir, "src")
    os.makedirs(src_dir, exist_ok=True)

    # Always create package.json (marks it as an existing project)
    pkg = {"name": name, "dependencies": {"react": "^18.0.0", "react-dom": "^18.0.0"}}
    with open(os.path.join(project_dir, "package.json"), "w") as f:
        json.dump(pkg, f)

    # Create any requested files
    if files:
        for rel_path, content in files.items():
            full_path = os.path.join(project_dir, rel_path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w") as f:
                f.write(content)

    # Project memory
    if memory:
        with open(os.path.join(project_dir, ".project_memory.json"), "w") as f:
            json.dump(memory, f)

    # Chat history
    if chat:
        with open(os.path.join(project_dir, ".chat_history.json"), "w") as f:
            json.dump(chat, f)

    return project_dir


class TestNewProject:
    """Tests for projects that don't exist yet (create mode)."""

    def test_new_project_gets_create_mode(self, tmp_base):
        result = build_prompt_context("brand_new", "Build a quiz", str(tmp_base))
        assert "[Mode: create]" in result
        assert "[Project name: brand_new]" in result

    def test_new_project_has_no_context_blocks(self, tmp_base):
        result = build_prompt_context("brand_new", "Build a quiz", str(tmp_base))
        assert "[Project info]" not in result
        assert "[Key file contents]" not in result
        assert "[Project memory]" not in result
        assert "[Recent conversation]" not in result

    def test_new_project_preserves_user_prompt(self, tmp_base):
        result = build_prompt_context("brand_new", "Build a space trivia quiz", str(tmp_base))
        assert "Build a space trivia quiz" in result


class TestExistingProject:
    """Tests for projects that already exist (modify mode)."""

    def test_existing_project_gets_modify_mode(self, tmp_base):
        _make_project(tmp_base, "quiz_2", files={"src/App.jsx": "export default function App() {}"})
        result = build_prompt_context("quiz_2", "make it blue", str(tmp_base))
        assert "[Mode: modify]" in result
        assert "[Project name: quiz_2]" in result

    def test_existing_project_has_project_info(self, tmp_base):
        _make_project(tmp_base, "quiz_2", files={"src/App.jsx": "export default function App() {}"})
        result = build_prompt_context("quiz_2", "make it blue", str(tmp_base))
        assert "[Project info]" in result
        assert "src/App.jsx" in result
        assert "react" in result.lower()

    def test_existing_project_has_key_file_contents(self, tmp_base):
        app_code = "export default function App() { return <div>Hello</div>; }"
        _make_project(tmp_base, "quiz_2", files={"src/App.jsx": app_code})
        result = build_prompt_context("quiz_2", "make it blue", str(tmp_base))
        assert "[Key file contents]" in result
        assert app_code in result

    def test_key_files_include_app_css(self, tmp_base):
        _make_project(tmp_base, "quiz_2", files={
            "src/App.jsx": "function App() {}",
            "src/App.css": "body { color: red; }",
        })
        result = build_prompt_context("quiz_2", "change the color", str(tmp_base))
        assert "body { color: red; }" in result

    def test_mentioned_component_injected(self, tmp_base):
        _make_project(tmp_base, "quiz_2", files={
            "src/App.jsx": "function App() {}",
            "src/components/Results.jsx": "function Results() { return <h1>Score</h1>; }",
        })
        result = build_prompt_context("quiz_2", "fix the Results component", str(tmp_base))
        assert "function Results()" in result
        assert "Results.jsx" in result

    def test_project_memory_loaded(self, tmp_base):
        _make_project(
            tmp_base, "quiz_2",
            files={"src/App.jsx": "function App() {}"},
            memory={"description": "Space trivia quiz", "quiz_type": "trivia"},
        )
        result = build_prompt_context("quiz_2", "add a timer", str(tmp_base))
        assert "[Project memory]" in result
        assert "Space trivia quiz" in result

    def test_recent_chat_loaded(self, tmp_base):
        _make_project(
            tmp_base, "quiz_2",
            files={"src/App.jsx": "function App() {}"},
            chat=[
                {"role": "user", "content": "build a quiz"},
                {"role": "assistant", "content": "Done! Built a quiz app."},
            ],
        )
        result = build_prompt_context("quiz_2", "now add dark mode", str(tmp_base))
        assert "[Recent conversation]" in result
        assert "build a quiz" in result

    def test_no_memory_block_when_empty(self, tmp_base):
        _make_project(tmp_base, "quiz_2", files={"src/App.jsx": "function App() {}"})
        result = build_prompt_context("quiz_2", "do something", str(tmp_base))
        assert "[Project memory]" not in result

    def test_no_chat_block_when_empty(self, tmp_base):
        _make_project(tmp_base, "quiz_2", files={"src/App.jsx": "function App() {}"})
        result = build_prompt_context("quiz_2", "do something", str(tmp_base))
        assert "[Recent conversation]" not in result
