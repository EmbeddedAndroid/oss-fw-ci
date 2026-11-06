import json

from ossci import collect, gate

URL = "https://lava.example/scheduler/job/9"


def res(suite, name, result, line=10):
    return {"suite": "1_" + suite, "name": name, "result": result, "start_log_line": line,
            "metadata": "definition: 1_%s\nlevel: '5.1'\n" % suite}


def log_line(lvl, msg):
    return "- " + json.dumps({"dt": "2026-11-06T00:00:00", "lvl": lvl, "msg": msg})


def entries(lines):
    from fwci import collect as fc
    return fc.log_entries("\n".join(lines))


def finished_job():
    return {"id": 9, "state": "Finished", "health": "Complete", "actual_device": "rb3g2-01"}


GATES = [res(s, n, "pass") for s in gate.GATE_SUITES for n in ("bl2", "bl31", "op_tee_version", "u_boot")]
TABLE = [{"board": "rb3gen2", "case": "kvm-unit-tests/mte-sync", "result": "skip", "reason": "no MTE",
          "evidence": "e", "reviewer": "r"}]
LOG = [log_line("info", "start: 5.1 lava-test-shell"), log_line("target", "SBL1, End"),
       log_line("target", "buildroot login:")]


def base():
    return {"board": "rb3gen2", "stack": "open", "state": "queued", "fingerprint": "ossci-1-1-rb3gen2",
            "lava": {"job_id": 9, "url": URL}}


def test_pass_with_justified_skip(board):
    results = GATES + [res("boot-handoff", "el2", "pass"), res("kvm-unit-tests", "mte-sync", "skip")]
    t = collect.target(base(), board, finished_job(), results, entries(LOG), URL, table=TABLE)
    assert t["state"] == "done" and t["fingerprint_gate"] == "pass" and t["verdict"] == "pass"
    assert t["counts"]["justified"] == 1 and "stack" not in t
    mte = [c for c in t["cases"] if c["name"] == "mte-sync"][0]
    assert mte["url"] == URL + "#L10"


def test_unjustified_failure_fails_the_board(board):
    results = GATES + [res("kernel-health", "kernel-warning", "fail")]
    t = collect.target(base(), board, finished_job(), results, entries(LOG), URL, table=TABLE)
    assert t["verdict"] == "fail"


def test_failed_gate_is_not_counted(board):
    results = [r for r in GATES if r["suite"] != "1_firmware-fingerprint-warm"] + [res("boot-handoff", "el2", "pass")]
    t = collect.target(base(), board, finished_job(), results, entries(LOG), URL, table=TABLE)
    assert t["fingerprint_gate"] == "fail" and t["verdict"] == "fail"
    b = {"fingerprint_gate": "pass", "cases": [{"suite": "boot-handoff", "name": "el2", "result": "fail"}]}
    collect.compare(t, b, "base")
    assert "diff" not in t


def test_known_flake_marked(board):
    today = __import__("datetime").date(2026, 11, 6)
    flake = {"id": "F1", "case": "fastrpc/cdsp-unsigned-pd", "issue": "https://lava/1", "suspected_cause": "lab",
             "confirmed": "2026-11-05", "single_board_type": True,
             "failures": [{"run": str(i), "date": "2026-11-0%d" % i, "board": "rb3g2-01"} for i in (1, 2, 3)]}
    results = GATES + [res("fastrpc", "cdsp-unsigned-pd", "fail")]
    t = collect.target(base(), board, finished_job(), results, entries(LOG), URL, flake_entries=[flake],
                       today=today)
    fl = [c for c in t["cases"] if c["name"] == "cdsp-unsigned-pd"][0]
    assert fl.get("flake") == "F1" and t["verdict"] == "pass"


def test_compare_delta():
    t = {"fingerprint_gate": "pass", "cases": [
        {"suite": "a", "name": "x", "result": "fail"}, {"suite": "a", "name": "y", "result": "pass"},
        {"suite": "a", "name": "z", "result": "fail"}, {"suite": "a", "name": "new", "result": "pass"}]}
    b = {"fingerprint_gate": "pass", "cases": [
        {"suite": "a", "name": "x", "result": "pass"}, {"suite": "a", "name": "y", "result": "fail"},
        {"suite": "a", "name": "z", "result": "fail"}, {"suite": "a", "name": "gone", "result": "pass"}]}
    collect.compare(t, b, "lava:540899")
    d = t["diff"]
    assert d["new_fail"] == ["a/x"] and d["new_pass"] == ["a/y"] and d["still_fail"] == ["a/z"]
    assert d["missing"] == ["a/gone"] and d["added"] == ["a/new"] and d["baseline"] == "lava:540899"


def test_unfinished_job_has_no_verdict(board):
    job = dict(finished_job(), state="Running", health="Unknown")
    t = collect.target(base(), board, job, GATES[:4], entries(LOG), URL, table=TABLE)
    assert t["state"] == "testing" and "verdict" not in t
