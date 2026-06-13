import subprocess
import json
import tempfile
import os
from dataclasses import dataclass, field
from typing import List


@dataclass
class LintIssue:
    rule_code: str
    message: str
    line: int
    column: int
    severity: str


@dataclass
class LintResult:
    issues: List[LintIssue] = field(default_factory=list)
    issue_count: int = 0
    error_codes: List[str] = field(default_factory=list)
    has_tool_error: bool = False
    tool_error_msg: str = ""


def analyze_code(source: str) -> LintResult:
    result = LintResult()
    tmp_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            delete=False,
            encoding="utf-8",
        ) as tmp:
            tmp.write(source)
            tmp_path = tmp.name
    except OSError as e:
        result.has_tool_error = True
        result.tool_error_msg = f"Failed to write temp file: {e}"
        return result

    try:
        proc = subprocess.run(
            [
                "ruff", "check",
                "--output-format", "json",
                "--select", "ALL",
                "--ignore", "D,ANN,ERA,INP001",
                tmp_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if proc.returncode == 2:
            result.has_tool_error = True
            result.tool_error_msg = f"Ruff internal error: {proc.stderr}"
            return result

        if not proc.stdout.strip():
            return result

        raw_issues = json.loads(proc.stdout)

        for item in raw_issues:
            issue = LintIssue(
                rule_code=item.get("code", "UNKNOWN"),
                message=item.get("message", ""),
                line=item.get("location", {}).get("row", 0),
                column=item.get("location", {}).get("column", 0),
                severity="error" if (item.get("code") or "").startswith("E") else "warning",
            )
            result.issues.append(issue)

        result.issue_count = len(result.issues)
        result.error_codes = list(set(i.rule_code for i in result.issues))
        return result

    except json.JSONDecodeError as e:
        result.has_tool_error = True
        result.tool_error_msg = f"Failed to parse Ruff output: {e}"
        return result
    except subprocess.TimeoutExpired:
        result.has_tool_error = True
        result.tool_error_msg = "Ruff timed out after 30 seconds"
        return result
    except FileNotFoundError:
        result.has_tool_error = True
        result.tool_error_msg = "Ruff not found — is it installed in this environment?"
        return result
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


def run(code: str) -> dict:
    result = analyze_code(code)
    return {
        "issues": [
            {
                "rule_code": i.rule_code,
                "message": i.message,
                "line": i.line,
                "column": i.column,
                "severity": i.severity,
            }
            for i in result.issues
        ],
        "issue_count": result.issue_count,
        "error_codes": result.error_codes,
        "has_tool_error": result.has_tool_error,
        "tool_error_msg": result.tool_error_msg,
    }