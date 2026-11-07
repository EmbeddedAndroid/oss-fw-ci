import re
import subprocess
import sys
from pathlib import Path

import yaml

RUN = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "run.yml"


def submit_script():
    jobs = yaml.safe_load(RUN.read_text())["jobs"]
    return [s["run"] for s in jobs["submit"]["steps"] if "run" in s and "ossci.run submit" in s["run"]][0]


def test_submit_reads_the_boards_of_the_resolve_output():
    # resolve publishes the boards as a JSON list (GITHUB_OUTPUT); the
    # submit step must turn that text, not a file of that name, into names.
    script = submit_script()
    m = re.search(r"^\s*boards=\$\(python3 -c '([^']*)' \"\$BOARDS\"\)$", script, re.M)
    assert m, "the submit step parses $BOARDS in an assignment"
    out = subprocess.run([sys.executable, "-c", m.group(1), '["rb3gen2", "other"]'],
                         capture_output=True, text=True, check=True).stdout.split()
    assert out == ["rb3gen2", "other"]
    bad = subprocess.run([sys.executable, "-c", m.group(1), "not json"], capture_output=True, text=True)
    assert bad.returncode != 0
    assert re.search(r"^\s*for b in \$boards; do$", script, re.M)
