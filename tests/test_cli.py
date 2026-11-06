import argparse

import pytest

from ossci import cli


def doc(state, verdict, cases=()):
    return {"state": state, "targets": [{"board": "rb3gen2", "state": state, "verdict": verdict,
                                         "fingerprint_gate": "pass", "counts": {"pass": 3},
                                         "cases": list(cases),
                                         "diff": {"baseline": "b", "new_fail": [], "new_pass": [], "still_fail": [],
                                                  "missing": [], "added": []}}]}


def ns(**kw):
    return argparse.Namespace(**dict({"site": "s", "run": "1-1", "interval": 0, "timeout": 100}, **kw))


def test_wait_exit_codes():
    assert cli.wait(ns(), get=lambda s, r: doc("done", "pass"), sleep=lambda x: None) == 0
    assert cli.wait(ns(), get=lambda s, r: doc("done", "fail", [{"suite": "a", "name": "b", "result": "fail"}]),
                    sleep=lambda x: None) == 1
    assert cli.wait(ns(timeout=-1), get=lambda s, r: doc("testing", "not-run"), sleep=lambda x: None) == 2


def test_wait_polls_until_final():
    seq = [None, doc("testing", "not-run"), doc("done", "pass")]
    assert cli.wait(ns(), get=lambda s, r: seq.pop(0), sleep=lambda x: None) == 0 and not seq


def test_run_refuses_bad_input_before_dispatch():
    a = argparse.Namespace(tfa="pr:1", optee="", uboot="", linux="", boards="", title="", requester="",
                           repo="r", ref="main")
    with pytest.raises(cli.refs.BadInput):
        cli.dispatch(a, run=lambda *x: pytest.fail("dispatched"))


def test_run_dispatches_and_returns_the_new_run(monkeypatch):
    calls = []
    lists = iter(['[{"databaseId": 5}]', '[{"databaseId": 6}, {"databaseId": 5}]'])

    def gh(*args):
        calls.append(args)
        return next(lists) if args[0] == "run" else ""
    monkeypatch.setattr(cli.time, "sleep", lambda x: None)
    a = argparse.Namespace(tfa="", optee="EmbeddedAndroid/optee_os@x", uboot="", linux="", boards="rb3gen2",
                           title="t", requester="me", repo="r", ref="main")
    assert cli.dispatch(a, run=gh) == "6-1"
    wf = [c for c in calls if c[0] == "workflow"][0]
    assert "optee=EmbeddedAndroid/optee_os@x" in wf and "boards=rb3gen2" in wf
