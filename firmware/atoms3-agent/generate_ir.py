Import("env")

import subprocess
import sys
from pathlib import Path

proj = Path(env["PROJECT_DIR"]).resolve()
repo = proj.parents[1]
script = repo / "scripts" / "ir_to_rmt.py"
output = proj / "src" / "ir_timings.h"

print(f"Generating {output} from {repo / 'ir_codes'}")
subprocess.check_call(
    [
        sys.executable,
        str(script),
        "--ir-dir",
        str(repo / "ir_codes"),
        "--output",
        str(output),
    ]
)
