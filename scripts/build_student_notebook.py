#!/usr/bin/env python3
"""Validate the checked-in workshop notebooks.

The 90-minute path keeps eight TODO stubs plus the in-cell TODO 1 prompt
(`notebook_student.ipynb`) and an answer key (`notebook_complete.ipynb`). Both
must parse, neither may ship a credential or leave a stub in the answer key, the
student notebook must be output-free, and the two must be identical apart from the
TODO cells and the two answer-key banner cells.

Run from the repository root:

    python scripts/build_student_notebook.py
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STUDENT = ROOT / "notebook_student.ipynb"
COMPLETE = ROOT / "notebook_complete.ipynb"

REQUIRED_SYMBOLS = (
    "_scan_tables",
    "retrieve_knowledge",
    "hybrid_rrf_search_memories",
    "tool_run_sql",
    "agent_turn",
    "OracleONNXEmbedder",
    "retrieve_tools",
    "tool_list_skills",
)
EXPECTED_STUBS = 8
# A stub is a cell that *raises* NotImplementedError (a checkpoint may merely mention it).
STUB_RE = re.compile(r"raise\s+NotImplementedError")
# A checkpoint cell has a comment line that opens with the marker (stubs only *mention* it).
CHECKPOINT_RE = re.compile(r"(?m)^#\s*Hard-stop checkpoint")
# A TODO cell: carries a `# TODO n` header comment. These legitimately differ between the notebooks.
TODO_CELL_RE = re.compile(r"(?m)^\s*#\s*TODO [1-9]\b")
# The answer key's title and overview cells say it is the answer key.
BANNER_RE = re.compile(r"^(# Financial Data Agent Workshop|## At a glance)")
EXPECTED_CHECKPOINT_CELLS = 8  # TODO 6 and 7 share the run_sql checkpoint cell
# A literal OCI/OpenAI-style key assigned in notebook source. The notebooks must
# prompt for (or read from the environment) credentials, never embed them.
SECRET_RE = re.compile(r'(?:OCI_GENAI_API_KEY|OPENAI_API_KEY|TAVILY_API_KEY)"\]\s*=\s*"(?:sk|tvly)-[A-Za-z0-9_-]{16,}"')


def load(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        notebook = json.load(handle)
    if not isinstance(notebook.get("cells"), list):
        raise ValueError(f"{path.name}: missing cells list")
    return notebook


def sources(notebook: dict) -> list[str]:
    return ["".join(cell.get("source", [])) for cell in notebook["cells"]]


def code_sources(notebook: dict) -> list[str]:
    return ["".join(cell.get("source", [])) for cell in notebook["cells"] if cell.get("cell_type") == "code"]


def check_parses(name: str, notebook: dict) -> None:
    for index, source in enumerate(code_sources(notebook)):
        if source.lstrip().startswith(("!", "%")):
            continue
        try:
            ast.parse(source)
        except SyntaxError as error:
            raise ValueError(f"{name}: code cell {index} does not parse: {error}") from error


def check_no_outputs(name: str, notebook: dict) -> None:
    for index, cell in enumerate(notebook["cells"]):
        if cell.get("cell_type") == "code" and (cell.get("outputs") or cell.get("execution_count")):
            raise ValueError(f"{name}: cell {index} carries outputs; the student notebook must ship clean")


def check_no_drift(student: dict, complete: dict) -> None:
    """Outside TODO cells and banners the two notebooks must be the same, cell for cell."""
    def shared(notebook):
        return [(cell["cell_type"], "".join(cell["source"])) for cell in notebook["cells"]
                if not TODO_CELL_RE.search("".join(cell["source"]))
                and not BANNER_RE.match("".join(cell["source"]))]
    left, right = shared(student), shared(complete)
    for index, (a, b) in enumerate(zip(left, right)):
        if a != b:
            raise ValueError(f"notebooks drifted at shared cell {index}: {a[1][:70]!r} != {b[1][:70]!r}")
    if len(left) != len(right):
        raise ValueError(f"notebooks have {len(left)} vs {len(right)} shared cells")


def check_no_secrets(name: str, notebook: dict) -> None:
    joined = "\n".join(sources(notebook))
    match = SECRET_RE.search(joined)
    if match:
        raise ValueError(f"{name}: a hard-coded credential is present in the notebook source")


def main() -> int:
    student = load(STUDENT)
    complete = load(COMPLETE)

    student_sources = sources(student)
    complete_sources = sources(complete)

    stubs = [source for source in student_sources if STUB_RE.search(source)]
    if len(stubs) != EXPECTED_STUBS:
        raise ValueError(f"student notebook should contain exactly {EXPECTED_STUBS} TODO stubs, found {len(stubs)}")
    checkpoints = [source for source in student_sources if CHECKPOINT_RE.search(source)]
    if len(checkpoints) != EXPECTED_CHECKPOINT_CELLS:
        raise ValueError(
            "student notebook should contain exactly "
            f"{EXPECTED_CHECKPOINT_CELLS} checkpoint cells, found {len(checkpoints)}"
        )
    if any(STUB_RE.search(source) for source in complete_sources):
        raise ValueError("complete notebook still contains a TODO stub")

    joined = "\n".join(student_sources + complete_sources)
    missing = [name for name in REQUIRED_SYMBOLS if name not in joined]
    if missing:
        raise ValueError(f"required workshop symbols are missing: {', '.join(missing)}")

    check_parses(STUDENT.name, student)
    check_parses(COMPLETE.name, complete)
    check_no_outputs(STUDENT.name, student)
    check_no_drift(student, complete)
    check_no_secrets(STUDENT.name, student)
    check_no_secrets(COMPLETE.name, complete)

    print(f"student: {len(student_sources)} cells, {len(stubs)} TODO stubs, {len(checkpoints)} checkpoints")
    print(f"complete: {len(complete_sources)} cells, no TODO stubs")
    print("notebook validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
