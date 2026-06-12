import ast
import textwrap
from dataclasses import dataclass, field
from typing import List


@dataclass
class FunctionInfo:
    name: str
    line_start: int
    line_end: int
    num_args: int
    is_async: bool
    complexity: int
    is_too_complex: bool


@dataclass
class ClassInfo:
    name: str
    line_start: int
    line_end: int
    num_methods: int
    base_classes: List[str]


@dataclass
class ASTAnalysis:
    functions: List[FunctionInfo] = field(default_factory=list)
    classes: List[ClassInfo] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    has_parse_error: bool = False
    parse_error_msg: str = ""
    complexity_warnings: List[str] = field(default_factory=list)


def _count_complexity(node: ast.FunctionDef) -> int:
    complexity = 1
    for child in ast.walk(node):
        if isinstance(child, (
            ast.If, ast.For, ast.While,
            ast.ExceptHandler, ast.With,
            ast.Assert, ast.comprehension,
        )):
            complexity += 1
        elif isinstance(child, ast.BoolOp):
            complexity += len(child.values) - 1
    return complexity


def analyze_code(source: str, complexity_threshold: int = 10) -> ASTAnalysis:
    result = ASTAnalysis()
    source = textwrap.dedent(source)

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        result.has_parse_error = True
        result.parse_error_msg = f"SyntaxError at line {e.lineno}: {e.msg}"
        return result

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            complexity = _count_complexity(node)
            is_too_complex = complexity > complexity_threshold
            result.functions.append(FunctionInfo(
                name=node.name,
                line_start=node.lineno,
                line_end=node.end_lineno or node.lineno,
                num_args=len(node.args.args),
                is_async=isinstance(node, ast.AsyncFunctionDef),
                complexity=complexity,
                is_too_complex=is_too_complex,
            ))
            if is_too_complex:
                result.complexity_warnings.append(
                    f"Function '{node.name}' at line {node.lineno} has "
                    f"complexity {complexity} (threshold: {complexity_threshold}). "
                    f"Consider breaking it into smaller functions."
                )

        elif isinstance(node, ast.ClassDef):
            methods = [
                n for n in ast.walk(node)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            base_classes = []
            for base in node.bases:
                if isinstance(base, ast.Name):
                    base_classes.append(base.id)
                elif isinstance(base, ast.Attribute):
                    base_classes.append(f"{base.value.id}.{base.attr}")
            result.classes.append(ClassInfo(
                name=node.name,
                line_start=node.lineno,
                line_end=node.end_lineno or node.lineno,
                num_methods=len(methods),
                base_classes=base_classes,
            ))

        elif isinstance(node, ast.Import):
            for alias in node.names:
                result.imports.append(alias.name)

        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                result.imports.append(f"{module}.{alias.name}")

    return result


def run(code: str) -> dict:
    analysis = analyze_code(code)
    return {
        "functions": [
            {
                "name": f.name,
                "line_start": f.line_start,
                "line_end": f.line_end,
                "num_args": f.num_args,
                "is_async": f.is_async,
                "complexity": f.complexity,
                "is_too_complex": f.is_too_complex,
            }
            for f in analysis.functions
        ],
        "classes": [
            {
                "name": c.name,
                "line_start": c.line_start,
                "line_end": c.line_end,
                "num_methods": c.num_methods,
                "base_classes": c.base_classes,
            }
            for c in analysis.classes
        ],
        "imports": analysis.imports,
        "has_parse_error": analysis.has_parse_error,
        "parse_error_msg": analysis.parse_error_msg,
        "complexity_warnings": analysis.complexity_warnings,
    }