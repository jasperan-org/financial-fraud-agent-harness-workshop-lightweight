# Contributing

Workshop attendees join this repository as collaborators through [workshopwaitingroom.com](https://workshopwaitingroom.com): enter your GitHub username, then accept the invitation GitHub emails you (or open the [invitations page](https://github.com/jasperan-org/financial-fraud-agent-harness-workshop-lightweight/invitations)). Collaborator access gives your Codespaces the shared OCI Generative AI keys, and it is how you contribute back.

## How changes land

1. Open an [issue](https://github.com/jasperan-org/financial-fraud-agent-harness-workshop-lightweight/issues) for a bug, a confusing step, or an idea, unless the fix is obvious.
2. Work on a branch in your Codespace: `git switch -c <your-handle>/<topic>`.
3. Push the branch and open a pull request against `main`. `main` is protected: it only changes through a pull request with an approving review from a maintainer.

Keep a pull request to one topic, and say in its description what you ran to check it.

## Where things live

| You want to change | Edit | Then run |
|---|---|---|
| A notebook cell, a TODO, a checkpoint | `.nbwork/parts/<part>/NNNN-*.{md,py,student.md,student.py}`, never the `.ipynb` files | `python3 .nbwork/nbparts.py assemble`, then `python3 scripts/check_notebooks.py` |
| A notebook figure | `figures_new/<figure>/` (manifest, SVG) | `python3 .nbwork/sync_figures.py`, then assemble and check as above |
| The harness the notebook imports | `workshop/*.py` | the affected notebook Part, top to bottom |
| The model router (keys, fallback lanes) | `oci_key_rotation.py` | `pip install pytest` once, then `python3 -m pytest tests/` |
| The app backend | `app/backend/` | `cd app/backend && python app.py`, then `curl http://localhost:8000/api/health` |
| The app front end | `app/frontend/src/` | `cd app/frontend && npm run build` (and `npm run dev` to try it on port 3000) |
| Database provisioning, seed data, identity rules | `app/scripts/*.py` | `bash .devcontainer/provision.sh --probe-only`; to rebuild a layer, run its script (`seed.py` drops and recreates `FINANCE`, so run `setup_deep_security.py` after it) |
| Guides | `docs/`, `README.md`, `app/README.md` | check that every command and number you mention matches the code |

## Ground rules

- Never commit a key. The shared keys arrive as Codespaces secrets; `app/.env` and every `*.env` are git-ignored, and `scripts/check_notebooks.py` fails on a notebook that embeds a credential.
- Commit notebooks only as `nbparts.py assemble` writes them. `notebook_student.ipynb` carries no outputs; `notebook_complete.ipynb` keeps the outputs of an executed run.
- Keep the harness framework-free: `python-oracledb`, `oracleagentmemory`, and the `openai` SDK. LangChain stays limited to the Part 3 interop example.
