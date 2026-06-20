import json
import subprocess
import pytest
from unittest.mock import patch, MagicMock

from app.tools.bandit_scanner import run as bandit_run
from app.tools.ruff_linter import run as ruff_run
from app.tools.ast_parser import run as ast_run
from app.agents.diff_utils import extract_code_from_diff
from app.agents.security_agent import security_node
from app.agents.performance_agent import performance_node
from app.agents.architecture_agent import architecture_node


# ── diff_utils ─────────────────────────────────────────────────────────────

class TestExtractCodeFromDiff:
    def test_extracts_only_added_lines(self):
        diff = "--- a/f.py\n+++ b/f.py\n@@ -1,2 +1,2 @@\n unchanged\n+added\n-removed"
        code = extract_code_from_diff(diff)
        assert "added" in code
        assert "removed" not in code
        assert "unchanged" not in code

    def test_skips_file_header_line(self):
        diff = "+++ b/f.py\n+real_code = 1"
        code = extract_code_from_diff(diff)
        assert "b/f.py" not in code
        assert "real_code = 1" in code

    def test_empty_diff_returns_empty_string(self):
        assert extract_code_from_diff("") == ""


# ── bandit_scanner ─────────────────────────────────────────────────────────

class TestBanditRun:
    def _mock_proc(self, returncode=0, stdout="", stderr=""):
        proc = MagicMock()
        proc.returncode = returncode
        proc.stdout = stdout
        proc.stderr = stderr
        return proc

    def test_no_issues_found(self):
        empty_result = json.dumps({"results": []})
        with patch("subprocess.run", return_value=self._mock_proc(0, empty_result)):
            result = bandit_run("x = 1")
        assert result["issue_count"] == 0
        assert result["has_tool_error"] is False

    def test_parses_issues_correctly(self):
        raw = json.dumps({
            "results": [
                {
                    "test_id": "B105",
                    "issue_text": "Hardcoded password",
                    "line_number": 4,
                    "issue_severity": "HIGH",
                    "issue_confidence": "MEDIUM",
                }
            ]
        })
        with patch("subprocess.run", return_value=self._mock_proc(1, raw)):
            result = bandit_run("PASSWORD = '123'")
        assert result["issue_count"] == 1
        assert result["high_severity_count"] == 1
        assert result["issues"][0]["rule_code"] == "B105"

    def test_internal_tool_error_returncode_above_1(self):
        with patch("subprocess.run", return_value=self._mock_proc(2, "", "crash")):
            result = bandit_run("x = 1")
        assert result["has_tool_error"] is True
        assert "Bandit internal error" in result["tool_error_msg"]

    def test_malformed_json_sets_tool_error(self):
        with patch("subprocess.run", return_value=self._mock_proc(0, "not json")):
            result = bandit_run("x = 1")
        assert result["has_tool_error"] is True

    def test_timeout_sets_tool_error(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="bandit", timeout=30)):
            result = bandit_run("x = 1")
        assert result["has_tool_error"] is True
        assert "timed out" in result["tool_error_msg"]

    def test_bandit_not_installed_sets_tool_error(self):
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            result = bandit_run("x = 1")
        assert result["has_tool_error"] is True
        assert "not found" in result["tool_error_msg"]

    def test_temp_file_cleaned_up_after_run(self):
        empty_result = json.dumps({"results": []})
        with patch("subprocess.run", return_value=self._mock_proc(0, empty_result)) as mock_run:
            bandit_run("x = 1")
            # The path passed to bandit is the last positional arg
            called_path = mock_run.call_args[0][0][-1]
        import os
        assert not os.path.exists(called_path)


# ── ruff_linter ────────────────────────────────────────────────────────────

class TestRuffRun:
    def _mock_proc(self, returncode=0, stdout="", stderr=""):
        proc = MagicMock()
        proc.returncode = returncode
        proc.stdout = stdout
        proc.stderr = stderr
        return proc

    def test_no_issues_found(self):
        with patch("subprocess.run", return_value=self._mock_proc(0, "[]")):
            result = ruff_run("x = 1")
        assert result["issue_count"] == 0

    def test_parses_issues_correctly(self):
        raw = json.dumps([
            {
                "code": "S608",
                "message": "Possible SQL injection",
                "location": {"row": 10, "column": 5},
            }
        ])
        with patch("subprocess.run", return_value=self._mock_proc(0, raw)):
            result = ruff_run("query = 'SELECT...'")
        assert result["issue_count"] == 1
        assert result["issues"][0]["rule_code"] == "S608"
        assert result["issues"][0]["line"] == 10

    def test_internal_error_returncode_2(self):
        with patch("subprocess.run", return_value=self._mock_proc(2, "", "boom")):
            result = ruff_run("x = 1")
        assert result["has_tool_error"] is True

    def test_ruff_not_installed(self):
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            result = ruff_run("x = 1")
        assert result["has_tool_error"] is True
        assert "not found" in result["tool_error_msg"]

    def test_timeout(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="ruff", timeout=30)):
            result = ruff_run("x = 1")
        assert result["has_tool_error"] is True


# ── ast_parser ─────────────────────────────────────────────────────────────

class TestAstRun:
    def test_simple_function_detected(self):
        code = "def foo(a, b):\n    return a + b"
        result = ast_run(code)
        assert len(result["functions"]) == 1
        assert result["functions"][0]["name"] == "foo"
        assert result["functions"][0]["num_args"] == 2

    def test_class_with_methods_detected(self):
        code = "class Foo:\n    def bar(self): pass\n    def baz(self): pass"
        result = ast_run(code)
        assert len(result["classes"]) == 1
        assert result["classes"][0]["num_methods"] == 2

    def test_imports_detected(self):
        code = "import os\nfrom typing import List"
        result = ast_run(code)
        assert "os" in result["imports"]
        assert "typing.List" in result["imports"]

    def test_high_complexity_function_flagged(self):
        code = (
            "def complex_fn(x):\n"
            "    if x:\n"
            "        if x:\n"
            "            if x:\n"
            "                if x:\n"
            "                    if x:\n"
            "                        if x:\n"
            "                            if x:\n"
            "                                if x:\n"
            "                                    if x:\n"
            "                                        if x:\n"
            "                                            return 1\n"
            "    return 0\n"
        )
        result = ast_run(code)
        assert result["functions"][0]["is_too_complex"] is True
        assert len(result["complexity_warnings"]) == 1

    def test_syntax_error_sets_parse_error(self):
        result = ast_run("def broken(:\n")
        assert result["has_parse_error"] is True
        assert "SyntaxError" in result["parse_error_msg"]

    def test_async_function_detected(self):
        code = "async def fetch():\n    pass"
        result = ast_run(code)
        assert result["functions"][0]["is_async"] is True

    def test_empty_code_returns_empty_results(self):
        result = ast_run("")
        assert result["functions"] == []
        assert result["classes"] == []
        assert result["imports"] == []
        assert result["has_parse_error"] is False


# ── security_node ────────────────────────────────────────────────────────

class TestSecurityNode:
    def test_empty_diff_skips(self):
        result = security_node({"diff": ""})
        assert result["security_findings"]["skipped"] is True

    def test_dedupes_overlapping_ruff_and_bandit_findings(self):
        diff = "+++ b/f.py\n+x = 1"
        with patch("app.agents.security_agent.ruff_run") as mock_ruff, \
             patch("app.agents.security_agent.bandit_run") as mock_bandit:
            mock_ruff.return_value = {"issues": [{"code": "S608", "line": 5, "message": "sql"}]}
            mock_bandit.return_value = {"issues": [{"test_id": "B608", "line": 5, "message": "sql"}]}
            result = security_node({"diff": diff})

        findings = result["security_findings"]["issues"]
        # Same line + same suffix (608) → should collapse to 1
        assert len(findings) == 1

    def test_high_count_counts_high_severity_or_confidence(self):
        diff = "+++ b/f.py\n+x = 1"
        with patch("app.agents.security_agent.ruff_run") as mock_ruff, \
             patch("app.agents.security_agent.bandit_run") as mock_bandit:
            mock_ruff.return_value = {"issues": []}
            mock_bandit.return_value = {
                "issues": [{"test_id": "B105", "line": 1, "severity": "HIGH", "confidence": "LOW"}]
            }
            result = security_node({"diff": diff})

        assert result["security_findings"]["high_count"] == 1

    def test_filters_non_security_ruff_issues(self):
        diff = "+++ b/f.py\n+x = 1"
        with patch("app.agents.security_agent.ruff_run") as mock_ruff, \
             patch("app.agents.security_agent.bandit_run") as mock_bandit:
            mock_ruff.return_value = {"issues": [{"code": "E501", "line": 1, "message": "line too long"}]}
            mock_bandit.return_value = {"issues": []}
            result = security_node({"diff": diff})

        # E501 is not an S-prefixed security rule — should be filtered out
        assert result["security_findings"]["issues"] == []


# ── performance_node ─────────────────────────────────────────────────────

class TestPerformanceNode:
    def test_empty_diff_skips(self):
        result = performance_node({"diff": ""})
        assert result["performance_findings"]["skipped"] is True

    def test_flags_high_complexity_function(self):
        diff = "+++ b/f.py\n+def foo(): pass"
        with patch("app.agents.performance_agent.ast_run") as mock_ast:
            mock_ast.return_value = {
                "functions": [
                    {"name": "foo", "line_start": 1, "complexity": 15, "loc": 5}
                ]
            }
            result = performance_node({"diff": diff})

        hotspots = result["performance_findings"]["hotspots"]
        assert len(hotspots) == 1
        assert "complexity" in hotspots[0]["issues"][0].lower()

    def test_no_hotspots_when_under_threshold(self):
        diff = "+++ b/f.py\n+def foo(): pass"
        with patch("app.agents.performance_agent.ast_run") as mock_ast:
            mock_ast.return_value = {
                "functions": [{"name": "foo", "line_start": 1, "complexity": 2, "loc": 3}]
            }
            result = performance_node({"diff": diff})

        assert result["performance_findings"]["hotspots"] == []


# ── architecture_node ────────────────────────────────────────────────────

class TestArchitectureNode:
    def test_empty_diff_skips(self):
        result = architecture_node({"diff": "", "rag_context": ""})
        assert result["architecture_findings"]["skipped"] is True

    def test_flags_large_class(self):
        diff = "+++ b/f.py\n+class Foo: pass"
        with patch("app.agents.architecture_agent.ast_run") as mock_ast:
            mock_ast.return_value = {
                "imports": ["os"],
                "classes": [{"name": "Foo", "methods": list(range(20))}],
                "functions": [],
            }
            result = architecture_node({"diff": diff, "rag_context": ""})

        notes = result["architecture_findings"]["notes"]
        assert any(n["type"] == "large_class" for n in notes)

    def test_attaches_rag_context_when_present(self):
        diff = "+++ b/f.py\n+x = 1"
        with patch("app.agents.architecture_agent.ast_run") as mock_ast:
            mock_ast.return_value = {"imports": [], "classes": [], "functions": []}
            result = architecture_node({"diff": diff, "rag_context": "similar code here"})

        assert result["architecture_findings"]["has_rag"] is True

    def test_no_rag_note_when_context_empty(self):
        diff = "+++ b/f.py\n+x = 1"
        with patch("app.agents.architecture_agent.ast_run") as mock_ast:
            mock_ast.return_value = {"imports": [], "classes": [], "functions": []}
            result = architecture_node({"diff": diff, "rag_context": ""})

        assert result["architecture_findings"]["has_rag"] is False

    def test_flags_missing_imports_with_functions_present(self):
        diff = "+++ b/f.py\n+def foo(): pass"
        with patch("app.agents.architecture_agent.ast_run") as mock_ast:
            mock_ast.return_value = {
                "imports": [],
                "classes": [],
                "functions": [{"name": "foo"}],
            }
            result = architecture_node({"diff": diff, "rag_context": ""})

        notes = result["architecture_findings"]["notes"]
        assert any(n["type"] == "missing_imports" for n in notes)