"""Forward compact agent operations to the local FlowReuse installation."""
import os
from pathlib import Path
import subprocess
import sys

DEFAULT_HOME = Path(__file__).resolve().parents[4]
home = Path(os.environ.get("FLOWREUSE_HOME", DEFAULT_HOME)).expanduser().resolve()
entry = home / "cli.py"
if not entry.is_file():
    print('{"status":"error","error":"FlowReuse project not found; set FLOWREUSE_HOME","requires_ai":true}')
    sys.exit(1)
sys.exit(subprocess.call([sys.executable, str(entry), *sys.argv[1:]], cwd=home))
