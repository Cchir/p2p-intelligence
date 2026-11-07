"""Sync the jupytext .py sources to .ipynb and execute them so outputs render on GitHub.

    uv run python scripts/build_notebooks.py
"""

import sys
from pathlib import Path

import jupytext
import nbformat
from nbclient import NotebookClient

NB_DIR = Path(__file__).resolve().parents[1] / "notebooks"

for src in sorted(NB_DIR.glob("[0-9][0-9]_*.py")):
    nb = jupytext.read(src)
    print(f"executing {src.name} ...", flush=True)
    NotebookClient(nb, timeout=900, kernel_name="python3",
                   resources={"metadata": {"path": str(NB_DIR)}}).execute()
    errors = [o for c in nb.cells if c.cell_type == "code" for o in c.get("outputs", [])
              if o.output_type == "error"]
    if errors:
        print(f"  {errors[0].ename}: {errors[0].evalue}")
        sys.exit(1)
    nbformat.write(nb, src.with_suffix(".ipynb"))
print("done")
