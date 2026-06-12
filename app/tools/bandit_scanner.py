import sys  # <--- Make sure sys is imported at the top of the file!
import subprocess
import json
import tempfile
import os
from dataclasses import dataclass, field
from typing import List, Dict, Any
import sys


@dataclass
class BanditIssue:
    rule_code: str    # e.g., 'B602'
    message: str      # e.g., 'subprocess call with shell=True'
    line: int
    severity: str     # LOW, MEDIUM, HIGH
    confidence: str   # LOW, MEDIUM, HIGH


@dataclass
class BanditResult:
    issues: List[BanditIssue] = field(default_factory=list)
    issue_count: int = 0
    has_tool_error: bool = False
    tool_error_msg: str = ""


def analyze_code_with_bandit(source: str) -> BanditResult:
    result = BanditResult()
    tmp_path = None

    # 1. Write code safely to a temporary file
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

    # 2. Run the actual Bandit CLI tool
    try:
        proc = subprocess.run(
            [
                sys.executable, "-m", "bandit",
                "-f", "json",       # Format output as JSON
                "-v",               # Verbose to ensure parsing is clear
                tmp_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        # Bandit returns exit code 1 if it finds issues, which is normal behavior!
        # Exit code 2+ means an actual internal tool error occurred.
        if proc.returncode > 1:
            result.has_tool_error = True
            result.tool_error_msg = f"Bandit internal error: {proc.stderr}"
            return result

        if not proc.stdout.strip():
            return result

        raw_data = json.loads(proc.stdout)
        raw_results = raw_data.get("results", [])

        for item in raw_results:
            issue = BanditIssue(
                rule_code=item.get("test_id", "UNKNOWN"),
                message=item.get("issue_text", ""),
                line=item.get("line_number", 0),
                severity=item.get("issue_severity", "UNKNOWN"),
                confidence=item.get("issue_confidence", "UNKNOWN"),
            )
            result.issues.append(issue)

        result.issue_count = len(result.issues)
        return result

    except json.JSONDecodeError as e:
        result.has_tool_error = True
        result.tool_error_msg = f"Failed to parse Bandit JSON output: {e}. Raw stdout: {proc.stdout}"
        return result
    except subprocess.TimeoutExpired:
        result.has_tool_error = True
        result.tool_error_msg = "Bandit execution timed out after 30 seconds"
        return result
    except FileNotFoundError:
        result.has_tool_error = True
        result.tool_error_msg = "Bandit binary not found. Run 'pip install bandit' inside your .venv"
        return result
    finally:
        # 3. Always clean up the filesystem
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


def run(code: str) -> dict:
    result = analyze_code_with_bandit(code)
    
    # Calculate custom metrics for your LangGraph agents down the road
    high_count = sum(1 for i in result.issues if i.severity == "HIGH")
    med_count = sum(1 for i in result.issues if i.severity == "MEDIUM")
    low_count = sum(1 for i in result.issues if i.severity == "LOW")

    return {
        "issues": [
            {
                "rule_code": i.rule_code,
                "message": i.message,
                "line": i.line,
                "severity": i.severity,
                "confidence": i.confidence,
            }
            for i in result.issues
        ],
        "issue_count": result.issue_count,
        "high_severity_count": high_count,
        "medium_severity_count": med_count,
        "low_severity_count": low_count,
        "has_tool_error": result.has_tool_error,
        "tool_error_msg": result.tool_error_msg,
    }