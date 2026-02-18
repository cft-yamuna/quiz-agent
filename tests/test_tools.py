"""Tests for tool handlers — read_file, list_files, create_file path resolution."""

import json
import os

import pytest

import tools.executor as executor


@pytest.fixture(autouse=True)
def setup_project(tmp_path):
    """Set up a fake project directory and configure executor globals."""
    # Override BASE_DIR to our tmp_path
    executor.BASE_DIR = str(tmp_path)
    executor._current_project = "quiz_2"

    # Create project structure
    project_dir = tmp_path / "output" / "quiz_2" / "src" / "components"
    project_dir.mkdir(parents=True)

    # Create files
    app_jsx = tmp_path / "output" / "quiz_2" / "src" / "App.jsx"
    app_jsx.write_text("export default function App() { return <div>Hello</div>; }")

    app_css = tmp_path / "output" / "quiz_2" / "src" / "App.css"
    app_css.write_text("body { margin: 0; }")

    results_jsx = tmp_path / "output" / "quiz_2" / "src" / "components" / "Results.jsx"
    results_jsx.write_text("function Results() { return <h1>Done</h1>; }")

    pkg = tmp_path / "output" / "quiz_2" / "package.json"
    pkg.write_text(json.dumps({"name": "quiz_2", "dependencies": {"react": "^18"}}))

    yield tmp_path

    # Restore
    executor.BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    executor._current_project = None


class TestReadFile:
    """Test _handle_read_file with path auto-resolution."""

    def test_read_bare_src_path(self):
        result = executor._handle_read_file({"path": "src/App.jsx"})
        assert "function App()" in result
        assert "ERROR" not in result

    def test_read_full_output_path(self):
        result = executor._handle_read_file({"path": "output/quiz_2/src/App.jsx"})
        assert "function App()" in result

    def test_read_component_in_subdir(self):
        result = executor._handle_read_file({"path": "src/components/Results.jsx"})
        assert "function Results()" in result

    def test_read_nonexistent_file(self):
        result = executor._handle_read_file({"path": "src/DoesNotExist.jsx"})
        assert "ERROR" in result


class TestListFiles:
    """Test _handle_list_files with path auto-resolution."""

    def test_list_bare_src(self):
        result = executor._handle_list_files({"directory": "src"})
        assert "App.jsx" in result
        assert "App.css" in result

    def test_list_components_subdir(self):
        result = executor._handle_list_files({"directory": "src/components"})
        assert "Results.jsx" in result

    def test_list_full_output_path(self):
        result = executor._handle_list_files({"directory": "output/quiz_2/src"})
        assert "App.jsx" in result

    def test_list_nonexistent_dir(self):
        result = executor._handle_list_files({"directory": "nonexistent"})
        assert "ERROR" in result


class TestCreateFile:
    """Test _handle_create_file path auto-resolution."""

    def test_create_bare_path(self, setup_project):
        tmp_path = setup_project
        result = executor._handle_create_file({
            "path": "src/NewComponent.jsx",
            "content": "function New() {}",
        })
        assert "Created" in result
        # Verify file actually exists at the right location
        expected = tmp_path / "output" / "quiz_2" / "src" / "NewComponent.jsx"
        assert expected.exists()
        assert expected.read_text() == "function New() {}"

    def test_create_full_path(self, setup_project):
        tmp_path = setup_project
        result = executor._handle_create_file({
            "path": "output/quiz_2/src/Another.jsx",
            "content": "function Another() {}",
        })
        assert "Created" in result
        expected = tmp_path / "output" / "quiz_2" / "src" / "Another.jsx"
        assert expected.exists()
