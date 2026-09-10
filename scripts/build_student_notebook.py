#!/usr/bin/env python3
"""Validate the checked-in workshop notebooks.

The 90-minute path keeps five TODO stubs (`notebook_student.ipynb`) and an
answer key (`notebook_complete.ipynb`). The reference notebooks
(`notebook_complete_with_setup_code.ipynb`, `enterprise_data_agent.ipynb`) must
parse and must not accidentally ship a stub.

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
FULL_SOURCE = ROOT / "notebook_complete_with_setup_code.ipynb"
ORIGINAL = ROOT / "enterprise_data_agent.ipynb"

REQUIRED_SYMBOLS = (
    "_scan_tables",
    "retrieve_knowledge",
    "hybrid_rrf_search_memories",
    "tool_run_sql",
    "agent_turn",
)
EXPECTED_STUBS = 5
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

    stubs = [source for source in student_sources if "NotImplementedError" in source]
    if len(stubs) != EXPECTED_STUBS:
        raise ValueError(f"student notebook should contain exactly {EXPECTED_STUBS} TODO stubs, found {len(stubs)}")
    if any("NotImplementedError" in source for source in complete_sources):
        raise ValueError("complete notebook still contains a TODO stub")

    joined = "\n".join(student_sources + complete_sources)
    missing = [name for name in REQUIRED_SYMBOLS if name not in joined]
    if missing:
        raise ValueError(f"required workshop symbols are missing: {', '.join(missing)}")

    for path in (STUDENT, COMPLETE, FULL_SOURCE, ORIGINAL):
        notebook = load(path)
        check_parses(path.name, notebook)
        check_no_secrets(path.name, notebook)

    print(f"student: {len(student_sources)} cells, {EXPECTED_STUBS} TODO stubs")
    print(f"complete: {len(complete_sources)} cells, no TODO stubs")
    for path in (FULL_SOURCE, ORIGINAL):
        print(f"{path.name}: parses cleanly")
    print("notebook validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
