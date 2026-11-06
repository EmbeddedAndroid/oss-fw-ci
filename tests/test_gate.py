import re

import pytest

from ossci import gate


def test_run_fingerprint_form():
    assert gate.run_fingerprint("19254", "1", "rb3gen2") == "ossci-19254-1-rb3gen2"
    with pytest.raises(ValueError):
        gate.run_fingerprint("12 ; x", "1", "rb3gen2")


def test_expect_pinned_bl2_and_run_stages(board):
    e = gate.expect(board, "ossci-7-1-rb3gen2")
    assert e == {"BL2": "QCDFP-261102-526", "BL31": "ossci-7-1-rb3gen2",
                 "OP-TEE version": "ossci-7-1-rb3gen2", "U-Boot": "ossci-7-1-rb3gen2"}


def test_expect_refuses_a_stage_without_fingerprint(board):
    board["gate"]["stages"]["SPL"] = "spl"
    with pytest.raises(ValueError):
        gate.expect(board, "ossci-7-1-rb3gen2")


def matches(board, fp, line):
    m = gate.monitors(board, fp)[0]["test"]["monitors"][0]
    hit = re.search(m["pattern"], line)
    return hit and (hit.group("test_case_id"), m["fixupdict"].get(hit.group("result")))


def test_monitor_pattern_on_console_lines(board):
    fp = "ossci-7-1-rb3gen2"
    assert matches(board, fp, "NOTICE:  BL31: v2.13.0(release):ossci-7-1-rb3gen2") == ("BL31", "pass")
    assert matches(board, fp, "NOTICE:  BL2: v2.13.0(release):QCDFP-261102-526") == ("BL2", "pass")
    assert matches(board, fp, "U-Boot 2026.01-rc1-ossci-7-1-rb3gen2 (Nov 06 2026)") == ("U-Boot", "pass")
    # Another run's build, or a longer fingerprint, never passes.
    assert not matches(board, fp, "NOTICE:  BL31: v2.13.0(release):ossci-7-1-rb3gen2x")
    assert not matches(board, "ossci-7-1-rb3gen2", "NOTICE:  BL31: v2.13.0(release):ossci-7-10-rb3gen2")
    # The BL2 stage needs the pinned fingerprint, not the run's.
    assert not matches(board, fp, "NOTICE:  BL2: v2.13.0(release):ossci-7-1-rb3gen2")


def case(suite, name, result):
    return {"suite": suite, "name": name, "result": result}


def test_verdict():
    both = [case(s, n, "pass") for s in gate.GATE_SUITES for n in ("bl2", "bl31")]
    assert gate.verdict(both) == "pass"
    assert gate.verdict([]) == "not-run"
    assert gate.verdict(both[:2]) == "fail"  # the warm gate never ran
    bad = list(both)
    bad[3] = case(gate.GATE_SUITES[1], "bl31", "fail")
    assert gate.verdict(bad) == "fail"
