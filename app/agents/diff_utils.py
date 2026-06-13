# app/agents/diff_utils.py

def extract_code_from_diff(diff: str) -> str:
    """
    Extracts added lines from a unified diff and returns them
    as plain Python source code the tools can parse.

    Unified diff format:
        --- a/file.py
        +++ b/file.py
        @@ -1,3 +1,6 @@
         unchanged line
        +added line
        -removed line

    We only want the added lines (starting with +), stripped of
    the leading + character. We skip the +++ file header lines.
    """
    lines = []
    for line in diff.splitlines():
        if line.startswith("+++ "):   # file header — skip
            continue
        if line.startswith("+"):      # added line — keep, strip the +
            lines.append(line[1:])
    return "\n".join(lines)