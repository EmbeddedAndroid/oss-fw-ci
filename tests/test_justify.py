import pytest

from ossci import justify

TABLE = [{"board": "rb3gen2", "case": "kvm-unit-tests/mte-sync", "result": "skip", "reason": "no MTE",
          "evidence": "https://lava/1", "reviewer": "r"}]


def c(suite, name, result):
    return {"suite": suite, "name": name, "result": result}


def test_lookup_needs_board_case_and_result():
    assert justify.lookup("rb3gen2", "kvm-unit-tests/mte-sync", "skip", TABLE)
    assert not justify.lookup("uno-q", "kvm-unit-tests/mte-sync", "skip", TABLE)
    assert not justify.lookup("rb3gen2", "kvm-unit-tests/mte-sync", "fail", TABLE)
    assert not justify.lookup("rb3gen2", "kvm-unit-tests/mte-async", "skip", TABLE)


def test_apply_marks_and_decides():
    cases = [c("kvm-unit-tests", "mte-sync", "skip"), c("boot-handoff", "el", "pass")]
    assert justify.apply("rb3gen2", cases, TABLE) == "pass"
    assert cases[0]["justified"]["reason"] == "no MTE"
    cases.append(c("kvm-unit-tests", "pmu", "skip"))
    assert justify.apply("rb3gen2", cases, TABLE) == "fail"


def test_unjustified_failure_fails_and_flake_does_not():
    cases = [dict(c("x", "y", "fail"), flake="F1")]
    assert justify.apply("rb3gen2", cases, []) == "pass"
    cases = [c("x", "y", "fail")]
    assert justify.apply("rb3gen2", cases, []) == "fail"


def test_entries_of_the_real_file_are_complete():
    assert all(e["result"] in ("fail", "skip") for e in justify.entries())


def test_incomplete_entry_refused(tmp_path):
    (tmp_path / "justifications.yaml").write_text(
        "justifications:\n  - {board: b, case: s/c, result: skip, reason: r}\n")
    with pytest.raises(ValueError, match="lacks"):
        justify.entries(str(tmp_path))
    (tmp_path / "justifications.yaml").write_text(
        "justifications:\n  - {board: b, case: s/c, result: pass, reason: r, evidence: e, reviewer: v}\n")
    with pytest.raises(ValueError, match="fail or skip"):
        justify.entries(str(tmp_path))
