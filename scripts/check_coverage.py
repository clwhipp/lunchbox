"""CLI entry point; the tested gate lives in schoolmenu.quality."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schoolmenu.quality import check_coverage  # noqa: E402

for name, (lines, branches) in check_coverage(json.loads(Path(sys.argv[1]).read_text())).items():
    print(f"{name}: lines {lines:.2f}%, branches {branches:.2f}% (minimum 96% each)")
