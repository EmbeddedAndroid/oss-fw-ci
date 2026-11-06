"""The suite every board runs: the plan of config/suite.yaml at the pinned
test-definitions commit, minus the excluded definitions, with each
definition's steps and default parameters from its own YAML.

python3 -m ossci.suite <test-definitions tree>   prints the definitions
in job order with their phase."""
import os
import re
import sys

import yaml

from . import config

PHASES = ("cold", "warm", "last")


def definition_name(path):
    return os.path.splitext(os.path.basename(path))[0]


def plan(td, cfg=None):
    cfg = cfg or config.suite()
    p = yaml.safe_load(open(os.path.join(td, cfg["plan"])))
    paths = [t["path"] for t in p["tests"]["automated"]]
    names = [definition_name(x) for x in paths]
    for x in cfg.get("exclude", {}):
        if x not in names:
            raise ValueError("suite.yaml excludes %s, which the plan does not have" % x)
    return [(definition_name(x), x) for x in paths if definition_name(x) not in cfg.get("exclude", {})]


def load(td, path):
    d = yaml.safe_load(open(os.path.join(td, path)))
    steps = d["run"]["steps"]
    params = {k: "" if v is None else str(v) for k, v in (d.get("params") or {}).items()}
    return steps, params


def definitions(td, cfg=None):
    """[(phase, name, path, steps, params)] in job order: cold, warm, last."""
    cfg = cfg or config.suite()
    phases = cfg.get("phases", {})
    for ph in phases:
        if ph not in PHASES or ph == "cold":
            raise ValueError("suite.yaml: unknown phase %s (cold is every definition not in last)" % ph)
    items = plan(td, cfg)
    names = [n for n, _ in items]
    for ph, members in phases.items():
        for n in members:
            if n not in names:
                raise ValueError("suite.yaml: %s in phase %s is not in the plan" % (n, ph))
    out = []
    last = set(phases.get("last", []))
    for ph in PHASES:
        for n, path in items:
            if ph == "cold" and n in last:
                continue
            if ph != "cold" and n not in phases.get(ph, []):
                continue
            steps, params = load(td, path)
            out.append((ph, n, path, steps, params))
    return out


def rebase_steps(steps, td_root):
    """The definition's steps run from the test-definitions tree at
    td_root on the target: the plan's relative `cd ./automated/...` becomes
    absolute, nothing else changes."""
    out = []
    for s in steps:
        s = str(s)
        m = re.match(r"^cd \./(automated/\S*)\s*$", s)
        out.append("cd %s/%s" % (td_root, m.group(1)) if m else s)
    return out


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    for ph, n, path, _, params in definitions(sys.argv[1]):
        print(ph, n, path, " ".join(sorted(params)))
