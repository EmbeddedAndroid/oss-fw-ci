"""One LAVA job into a target of the run document (pure functions over
fetched data, so they test offline): fwci's collector for cases, links,
boot verdict and boot times, then the ossci rules: the fingerprint gate
on both boots, known flakes, justifications, the verdict, the counts and
the comparison with the board's baseline run."""
import datetime

from fwci import collect as fc
from fwci import flakes

from . import gate, justify


def mark_flakes(board, cases, entries, today=None):
    today = today or datetime.date.today()
    for c in cases:
        if c["result"] != "fail":
            continue
        cid = "%s/%s" % (c["suite"], c["name"])
        for e in flakes.active(entries, today):
            if e["case"] == cid and board in e.get("boards", [board]):
                c["flake"] = e["id"]
    return cases


def counts(cases):
    out = {"pass": 0, "fail": 0, "skip": 0, "unknown": 0, "justified": 0, "flaky": 0}
    for c in cases:
        out[c["result"]] += 1
        out["justified"] += 1 if c.get("justified") else 0
        out["flaky"] += 1 if c.get("flake") else 0
    return out


def target(base, board, job, results, entries, job_url, log=None, flake_entries=(), table=(),
           today=None):
    t = fc.target(base, job, results, entries, job_url, gate.GATE_SUITES,
                  board["lava"]["xbl_marker"], log=log)
    t.pop("stack", None)
    cases = t.get("cases", [])
    t["fingerprint_gate"] = gate.verdict(cases) if t["state"] == "done" else (
        "fail" if t.get("fingerprint_gate") == "fail" else "not-run")
    mark_flakes(t["board"], cases, flake_entries, today)
    if t["state"] == "done":
        t["verdict"] = justify.apply(t["board"], cases, table) if t["fingerprint_gate"] == "pass" else "fail"
    t["counts"] = counts(cases)
    return t


def case_ids(t):
    return {"%s/%s" % (c["suite"], c["name"]): c["result"] for c in t.get("cases", [])}


def compare(t, b, baseline_id):
    """The per-case delta against the board's baseline target, only when
    both passed the fingerprint gate (else the cell ran something else)."""
    if not b or t.get("fingerprint_gate") != "pass" or b.get("fingerprint_gate") != "pass":
        t.pop("diff", None)
        return t
    now, then = case_ids(t), case_ids(b)
    t["diff"] = {
        "baseline": baseline_id,
        "new_fail": sorted(c for c, r in now.items() if r == "fail" and then.get(c, "fail") != "fail"),
        "new_pass": sorted(c for c, r in now.items() if r == "pass" and then.get(c) in ("fail", "skip")),
        "still_fail": sorted(c for c, r in now.items() if r == "fail" and then.get(c) == "fail"),
        "missing": sorted(set(then) - set(now)),
        "added": sorted(set(now) - set(then)),
    }
    return t


def lava_reference(job_id, results, url):
    """A hand-run LAVA job as a baseline target (the phase-2 comparison):
    its cases, with the gate taken as passed when both gate suites passed."""
    cl = fc.cases(results, url)
    return {"board": "", "state": "done", "cases": cl, "fingerprint_gate": gate.verdict(
        [dict(c, suite=c["suite"]) for c in cl])}
