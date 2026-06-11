from typing import List
from dataclasses import dataclass


@dataclass
class CodeChunk:
    """A single chunk of code with metadata."""
    content: str          # The actual code text
    chunk_index: int      # Position within the original diff
    pr_number: int        # Which PR this came from
    repo: str             # e.g. "username/auto-reviewer"
    file_hint: str = ""   # Filename if parseable from diff header


def chunk_diff(
    diff_text: str,
    pr_number: int,
    repo: str,
    max_chunk_size: int = 512,
    overlap: int = 50,
) -> List[CodeChunk]:
    """
    Split a raw GitHub diff into overlapping chunks for embedding.

    Strategy:
    - First split by file boundary (lines starting with 'diff --git')
    - Then split each file section by hunks ('@@' markers)
    - If a hunk is still too large, do sliding-window chunking

    Why overlap? If a concept spans the boundary of two chunks,
    overlap ensures at least one chunk contains the full context.
    """
    if not diff_text or not diff_text.strip():
        return []

    chunks: List[CodeChunk] = []
    chunk_index = 0

    # Split diff into per-file sections
    file_sections = _split_by_file(diff_text)

    for file_hint, section in file_sections:
        # Split each file section into hunks
        hunks = _split_by_hunk(section)

        for hunk in hunks:
            hunk = hunk.strip()
            if not hunk:
                continue

            # If the hunk fits in one chunk, store it directly
            if len(hunk) <= max_chunk_size:
                chunks.append(CodeChunk(
                    content=hunk,
                    chunk_index=chunk_index,
                    pr_number=pr_number,
                    repo=repo,
                    file_hint=file_hint,
                ))
                chunk_index += 1
            else:
                # Sliding window for large hunks
                sub_chunks = _sliding_window(hunk, max_chunk_size, overlap)
                for sub in sub_chunks:
                    chunks.append(CodeChunk(
                        content=sub,
                        chunk_index=chunk_index,
                        pr_number=pr_number,
                        repo=repo,
                        file_hint=file_hint,
                    ))
                    chunk_index += 1

    return chunks


def _split_by_file(diff_text: str) -> List[tuple[str, str]]:
    """Split diff into (filename, section_text) tuples by 'diff --git' markers."""
    sections = []
    current_file = ""
    current_lines: List[str] = []

    for line in diff_text.splitlines(keepends=True):
        if line.startswith("diff --git"):
            if current_lines:
                sections.append((current_file, "".join(current_lines)))
            # Extract filename from "diff --git a/foo.py b/foo.py"
            parts = line.strip().split(" ")
            current_file = parts[-1][2:] if len(parts) >= 4 else ""
            current_lines = [line]
        else:
            current_lines.append(line)

    if current_lines:
        sections.append((current_file, "".join(current_lines)))

    return sections


def _split_by_hunk(section: str) -> List[str]:
    """Split a file section into individual diff hunks by '@@' markers."""
    hunks = []
    current: List[str] = []

    for line in section.splitlines(keepends=True):
        if line.startswith("@@") and current:
            hunks.append("".join(current))
            current = [line]
        else:
            current.append(line)

    if current:
        hunks.append("".join(current))

    return hunks


def _sliding_window(text: str, size: int, overlap: int) -> List[str]:
    """Chunk a long string using a sliding window (character-level)."""
    step = size - overlap
    return [text[i:i + size] for i in range(0, len(text), step) if text[i:i + size].strip()]