"""The fingerprint gate (docs/DESIGN.md "collect"): what each boot of a
board must print, and whether a collected target passed.

Every stage built from the run's inputs carries the run fingerprint
ossci-<run>-<attempt>-<board>; a pinned image (the BL2 of a board, a
private image) carries its own, from boards.yaml. A cell whose gate did
not pass ran something else: its results are not counted and it raises
no regression."""
import re

from fwci import lava_jobs

FP = re.compile(r"^ossci-[0-9]+-[0-9]+-[a-z0-9-]+$")
GATE_SUITES = ("firmware-fingerprint-cold", "firmware-fingerprint-warm")


def run_fingerprint(run_id, attempt, board):
    fp = "ossci-%s-%s-%s" % (run_id, attempt, board)
    if not FP.fullmatch(fp):
        raise ValueError("bad fingerprint %r" % fp)
    return fp


def expect(board, fp):
    """Banner prefix -> fingerprint that stage must print."""
    out = {}
    pins = {"bl2": (board.get("bl2") or {}).get("fingerprint"), "run": fp}
    for prefix, src in board["gate"]["stages"].items():
        if src not in pins or not pins[src]:
            raise ValueError("gate stage %s: no fingerprint for %r" % (prefix, src))
        out[prefix] = pins[src]
    return out


def monitors(board, fp):
    """The cold and warm gate monitors of a board's job."""
    g = board["gate"]
    e = expect(board, fp)
    out = []
    for name in GATE_SUITES:
        m = lava_jobs.fingerprint_gate(name, g["start"], g["end"], e, minutes=4)
        m["test"]["timeout"]["skip"] = True
        out.append(m)
    return out


def verdict(cases):
    """pass only when every expected stage passed on both boots; not-run
    when the first gate never ran; fail otherwise. cases: collected cases."""
    by = {s: [c for c in cases if c["suite"] == s] for s in GATE_SUITES}
    first = by[GATE_SUITES[0]]
    if not first:
        return "not-run"
    for s in GATE_SUITES:
        if not by[s] or any(c["result"] != "pass" for c in by[s]):
            return "fail"
    return "pass"
