import pytest
from unittest.mock import patch, MagicMock
from app.agents.orchestrator import orchestrator_node
from app.agents.supervisor_agent import supervisor_node, _build_prompt


# ── Orchestrator ──────────────────────────────────────────────────────────────

def test_orchestrator_empty_diff():
    state = {"pr_number": 1, "repo_full_name": "test/repo", "diff": ""}
    result = orchestrator_node(state)
    assert result.get("error") == "Empty diff, nothing to review"


def test_orchestrator_valid_diff():
    state = {
        "pr_number": 1,
        "repo_full_name": "test/repo",
        "diff": "diff --git a/foo.py b/foo.py\n+print('hello')",
    }
    result = orchestrator_node(state)
    assert "error" not in result or result.get("error") is None


def test_orchestrator_whitespace_only_diff():
    state = {"pr_number": 1, "repo_full_name": "test/repo", "diff": "   \n  "}
    result = orchestrator_node(state)
    assert result.get("error") == "Empty diff, nothing to review"


# ── Supervisor prompt builder ─────────────────────────────────────────────────

def test_build_prompt_no_findings():
    state = {
        "security_findings": {},
        "performance_findings": {},
        "architecture_findings": {},
    }
    prompt = _build_prompt(state)
    assert "All checks passed" in prompt


def test_build_prompt_with_security_findings():
    state = {
        "security_findings": {
            "issues": [
                {
                    "line": 10,
                    "code": "B105",
                    "message": "Hardcoded password",
                    "severity": "high",
                    "source": "bandit",
                }
            ]
        },
        "performance_findings": {},
        "architecture_findings": {},
    }
    prompt = _build_prompt(state)
    assert "Security" in prompt
    assert "B105" in prompt
    assert "Hardcoded password" in prompt


def test_build_prompt_with_performance_findings():
    state = {
        "security_findings": {},
        "performance_findings": {
            "hotspots": [
                {
                    "function": "slow_fn",
                    "line": 42,
                    "issues": ["O(n^2) nested loop detected"],
                }
            ]
        },
        "architecture_findings": {},
    }
    prompt = _build_prompt(state)
    assert "Performance" in prompt
    assert "slow_fn" in prompt


def test_build_prompt_with_architecture_findings():
    state = {
        "security_findings": {},
        "performance_findings": {},
        "architecture_findings": {
            "notes": [
                {"type": "similar_code_found", "context": "def foo(): pass"}
            ]
        },
    }
    prompt = _build_prompt(state)
    assert "Architecture" in prompt
    assert "Similar patterns" in prompt


# ── Supervisor node ───────────────────────────────────────────────────────────

def test_supervisor_node_calls_groq():
    state = {
        "security_findings": {},
        "performance_findings": {},
        "architecture_findings": {},
    }

    mock_response = MagicMock()
    mock_response.choices[0].message.content = "APPROVE — no issues found."

    with patch("app.agents.supervisor_agent.client.chat.completions.create",
               return_value=mock_response):
        result = supervisor_node(state)

    assert result["final_review"] == "APPROVE — no issues found."
    assert result["model_version"] == "llama-3.3-70b-versatile"


def test_supervisor_node_groq_failure():
    state = {
        "security_findings": {},
        "performance_findings": {},
        "architecture_findings": {},
    }

    with patch("app.agents.supervisor_agent.client.chat.completions.create",
               side_effect=Exception("Groq timeout")):
        result = supervisor_node(state)

    assert "error" in result["final_review"].lower() or "autorereviewer" in result["final_review"].lower()
    assert result["model_version"] == "llama-3.3-70b-versatile"