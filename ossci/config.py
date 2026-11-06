"""The pinned configuration (config/*.yaml), read and checked.

python3 -m ossci.config get <board> <dotted.key>   one value for the shell
scripts (lists print one item per line, dicts as JSON)."""
import json
import os
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "config")
# A board entry may not carry any of these: the suite is the same for
# every board (config/suite.yaml).
TEST_LIST_KEYS = ("tests", "definitions", "suite", "skip_tests", "test_plan", "plan", "exclude")


def load(name, root=None):
    with open(os.path.join(root or CONFIG, name + ".yaml")) as f:
        return yaml.safe_load(f)


def suite(root=None):
    return load("suite", root)


def rootfs(root=None):
    return load("rootfs", root)


def baseline(root=None):
    return load("baseline", root)


def boards(root=None):
    b = load("boards", root)["boards"]
    for name, entry in b.items():
        check_board(name, entry)
    return b


def board(name, root=None):
    b = boards(root)
    if name not in b:
        raise SystemExit("unknown board %s (boards.yaml has %s)" % (name, " ".join(sorted(b))))
    return b[name]


def check_board(name, entry):
    bad = [k for k in TEST_LIST_KEYS if k in entry]
    if bad:
        raise ValueError("board %s: %s: a board takes the suite of config/suite.yaml, "
                         "not a test list of its own" % (name, ", ".join(bad)))
    for k in ("lava", "arch", "gate", "facts"):
        if k not in entry:
            raise ValueError("board %s: no %s" % (name, k))
    return entry


def get(obj, dotted):
    for k in dotted.split("."):
        obj = obj[int(k)] if isinstance(obj, list) else obj[k]
    return obj


def show(v):
    if isinstance(v, list):
        return "\n".join(str(x) for x in v)
    if isinstance(v, dict):
        return json.dumps(v)
    return str(v)


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "get":
        print(show(get(board(sys.argv[2]), sys.argv[3])))
    elif len(sys.argv) == 4 and sys.argv[1] == "top":
        print(show(get(load(sys.argv[2]), sys.argv[3])))
    else:
        raise SystemExit(__doc__)
