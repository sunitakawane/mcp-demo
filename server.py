"""
Notes Assistant MCP server.

Exposes a folder of Markdown notes to any MCP client over stdio.

  Tools:     search_notes, read_note, create_note, append_to_note
  Resource:  notes://index  (list of all notes with titles and sizes)

Safety: every file path is resolved and must stay inside NOTES_DIR.

IMPORTANT: do not print() to stdout in this file. Over stdio, stdout carries
the MCP protocol, so stray output corrupts the session. Use stderr for logs.
"""

import os
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

BASE_DIR = Path(__file__).resolve().parent
NOTES_DIR = Path(os.environ.get("NOTES_DIR", BASE_DIR / "notes")).resolve()
NOTES_DIR.mkdir(parents=True, exist_ok=True)

mcp = FastMCP("notes-assistant")




# ---------- helpers ----------

def _note_path(name: str) -> Path:
    """Turn a user-supplied note name into a safe path inside NOTES_DIR."""
    name = name.strip()
    if not name:
        raise ValueError("Note name cannot be empty.")
    if not name.endswith(".md"):
        name += ".md"

    path = (NOTES_DIR / name).resolve()
    try:
        path.relative_to(NOTES_DIR)  # raises ValueError if path escapes the folder
    except ValueError:
        raise ValueError(f"Refused: '{name}' is outside the notes folder.") from None
    return path


def _all_notes() -> list[Path]:
    return sorted(NOTES_DIR.glob("*.md"))


def _title(path: Path) -> str:
    """Use the first '# ' heading as the title, falling back to the filename."""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return path.stem


# ---------- tools ----------

@mcp.tool()
def search_notes(query: str = "") -> str:
    """Search notes for a case-insensitive text match. Pass an empty query to list all notes with a short preview."""
    notes = _all_notes()
    if not notes:
        return "No notes yet."

    results = []
    q = query.strip().lower()
    for path in notes:
        lines = path.read_text(encoding="utf-8").splitlines()
        if not q:
            preview = next((l for l in lines if l.strip()), "")
            results.append(f"- {path.name}: {preview[:80]}")
            continue
        hits = [l.strip() for l in lines if q in l.lower()]
        if hits:
            results.append(f"- {path.name}:\n    " + "\n    ".join(hits[:3]))

    return "\n".join(results) if results else f"No notes match '{query}'."


@mcp.tool()
def read_note(name: str) -> str:
    """Return the full text of a note. The name can include or omit the .md extension."""
    path = _note_path(name)
    if not path.exists():
        return f"No note named '{path.name}'."
    return path.read_text(encoding="utf-8")


@mcp.tool()
def create_note(name: str, content: str) -> str:
    """Create a new note. Fails if a note with that name already exists."""
    path = _note_path(name)
    if path.exists():
        return f"'{path.name}' already exists. Use append_to_note to add to it."
    path.write_text(content, encoding="utf-8")
    return f"Created '{path.name}'."


@mcp.tool()
def append_to_note(name: str, text: str) -> str:
    """Append text to the end of an existing note."""
    path = _note_path(name)
    if not path.exists():
        return f"No note named '{path.name}'. Use create_note first."
    existing = path.read_text(encoding="utf-8")
    separator = "" if existing.endswith("\n") or not existing else "\n"
    path.write_text(existing + separator + text + "\n", encoding="utf-8")
    return f"Appended to '{path.name}'."


# ---------- resource ----------

@mcp.resource("notes://index")
def notes_index() -> str:
    """Index of all notes: file name, title, and size in bytes."""
    notes = _all_notes()
    if not notes:
        return "No notes yet."
    lines = [f"{p.name} | {_title(p)} | {p.stat().st_size} bytes" for p in notes]
    return "\n".join(lines)


if __name__ == "__main__":
    print(f"notes-assistant serving {NOTES_DIR}", file=sys.stderr)
    mcp.run()  # stdio transport