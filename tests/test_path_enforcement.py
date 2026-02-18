"""Tests for tools.executor._enforce_output_dir path resolution."""

import pytest

# We need to set _current_project before importing, so we patch it
import tools.executor as executor


@pytest.fixture(autouse=True)
def reset_project():
    """Reset _current_project before and after each test."""
    old = executor._current_project
    yield
    executor._current_project = old


class TestWithProjectContext:
    """Tests when _current_project is set (normal operating mode)."""

    def setup_method(self):
        executor._current_project = "quiz_2"

    def test_correct_path_passes_through(self):
        result = executor._enforce_output_dir("output/quiz_2/src/App.jsx")
        assert result == "output/quiz_2/src/App.jsx"

    def test_bare_src_path_resolved(self):
        result = executor._enforce_output_dir("src/App.jsx")
        assert result == "output/quiz_2/src/App.jsx"

    def test_bare_package_json_resolved(self):
        result = executor._enforce_output_dir("package.json")
        assert result == "output/quiz_2/package.json"

    def test_project_name_prefix_resolved(self):
        result = executor._enforce_output_dir("quiz_2/src/App.jsx")
        assert result == "output/quiz_2/src/App.jsx"

    def test_backslashes_normalized(self):
        result = executor._enforce_output_dir("src\\components\\Quiz.jsx")
        assert "\\" not in result
        assert result == "output/quiz_2/src/components/Quiz.jsx"

    def test_leading_dot_slash_stripped(self):
        result = executor._enforce_output_dir("./src/App.jsx")
        assert result == "output/quiz_2/src/App.jsx"

    def test_output_without_project_name_fixed(self):
        result = executor._enforce_output_dir("output/package.json")
        assert result == "output/quiz_2/package.json"


class TestWithoutProjectContext:
    """Tests when _current_project is None (fallback mode)."""

    def setup_method(self):
        executor._current_project = None

    def test_bare_path_gets_output_prefix(self):
        result = executor._enforce_output_dir("src/App.jsx")
        assert result == "output/src/App.jsx"

    def test_correct_path_passes_through(self):
        result = executor._enforce_output_dir("output/some_project/src/App.jsx")
        assert result == "output/some_project/src/App.jsx"
