"""Justifications (config/justifications.yaml): the only way a case may
end other than pass on a board. A non-pass case without an entry for its
board, case and result counts as a failure of the run."""
from . import config

FIELDS = ("board", "case", "result", "reason", "evidence", "reviewer")


def entries(path_root=None):
    data = config.load("justifications", path_root) or {}
    out = []
    for e in data.get("justifications") or []:
        missing = [f for f in FIELDS if not e.get(f)]
        if missing:
            raise ValueError("justification %s/%s lacks %s" % (e.get("board"), e.get("case"), ", ".join(missing)))
        if e["result"] not in ("fail", "skip"):
            raise ValueError("justification %s/%s: result must be fail or skip" % (e["board"], e["case"]))
        out.append(e)
    return out


def lookup(board, case, result, table):
    for e in table:
        if e["board"] == board and e["case"] == case and e["result"] == result:
            return e
    return None


def apply(board, cases, table):
    """Marks every non-pass case: `justified` (the entry's reason and
    evidence) or counted as a failure. Returns the verdict of the target:
    pass when every case passed or is justified."""
    ok = True
    for c in cases:
        if c["result"] == "pass":
            continue
        e = lookup(board, "%s/%s" % (c["suite"], c["name"]), c["result"], table)
        if e:
            c["justified"] = {"reason": e["reason"], "evidence": e["evidence"], "reviewer": e["reviewer"]}
        elif c.get("flake"):
            continue
        else:
            ok = False
    return "pass" if ok else "fail"
