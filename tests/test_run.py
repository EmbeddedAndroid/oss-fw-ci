import argparse
import json

import pytest

from ossci import run, schema

SHA = "c" * 40


def resolved(pending=None):
    out = {}
    for c in ("tfa", "optee", "uboot", "linux"):
        out[c] = {"repo": "https://github.com/EmbeddedAndroid/%s" % c, "ref": "r", "commit": SHA,
                  "role": "baseline", "input": {"kind": "baseline"}}
    if pending:
        out["linux"]["pending"] = pending
    return out


def new_doc(tmp_path, boards="rb3gen2"):
    inp = tmp_path / "resolved.json"
    inp.write_text(json.dumps(resolved()))
    doc = tmp_path / "doc.json"
    run.main(["new", str(doc), "--id", "123-1", "--inputs", str(inp), "--boards", boards,
              "--title", "t", "--requester", "agent"])
    return doc


def test_new_document_validates(tmp_path):
    d = json.load(open(new_doc(tmp_path)))
    schema.check(d)
    t = d["targets"][0]
    assert t["fingerprint"] == "ossci-123-1-rb3gen2" and t["state"] == "building"
    assert t["bl2"]["fingerprint"] == "QCDFP-261102-526" and t["bl2"]["secret"] == "PIN_BL2_RB3GEN2"
    assert d["rootfs"]["upstream"] is False and d["suite"]["commit"]


def test_bad_run_id_and_board_refused(tmp_path):
    inp = tmp_path / "r.json"
    inp.write_text(json.dumps(resolved()))
    with pytest.raises(SystemExit):
        run.main(["new", str(tmp_path / "d.json"), "--id", "abc", "--inputs", str(inp)])
    with pytest.raises(SystemExit):
        run.main(["new", str(tmp_path / "d.json"), "--id", "1-1", "--inputs", str(inp), "--boards", "nope"])


def test_skip_and_finished(tmp_path):
    doc = new_doc(tmp_path)
    with pytest.raises(SystemExit) as e:
        run.main(["finished", str(doc)])
    assert e.value.code == 1
    run.main(["skip", str(doc), "rootfs pin not public"])
    d = json.load(open(doc))
    assert d["targets"][0]["state"] == "skipped" and d["state"] == "done"
    with pytest.raises(SystemExit) as e:
        run.main(["finished", str(doc)])
    assert e.value.code == 0


def test_submit_without_token_skips(tmp_path, monkeypatch):
    monkeypatch.delenv("LAVA_TOKEN", raising=False)
    doc = new_doc(tmp_path)
    run.submit(argparse.Namespace(doc=str(doc), packages=str(tmp_path), td=str(tmp_path)))
    t = json.load(open(doc))["targets"][0]
    assert t["state"] == "skipped" and "LAVA_TOKEN" in t["state_detail"]


class FakeLava:
    def __init__(self):
        self.submitted = []

    def upload(self, path):
        return "https://lava/artifacts/x/p.tar.gz", "upload-token-name"

    def devices(self, dt):
        return [{"hostname": "rb3g2-matthart-production-01", "state": "Idle", "health": "Good"},
                {"hostname": "rb3g2-02", "state": "Busy", "health": "Good"},
                {"hostname": "rb3g2-03", "state": "Idle", "health": "Bad"},
                {"hostname": "rb3g2-01", "state": "Idle", "health": "Good"}]

    def submit(self, definition):
        self.submitted.append(definition)
        return 777


def test_submit_picks_an_idle_healthy_device_and_never_production(tmp_path, monkeypatch, td, board, suite_cfg):
    from ossci import jobs, package
    monkeypatch.setattr(run.config, "board", lambda name: board)
    monkeypatch.setattr(jobs.config, "suite", lambda: suite_cfg)
    monkeypatch.setenv("LAVA_TOKEN", "x")
    monkeypatch.setattr(package, "insert_bl2", lambda pkg, name, board=None: None)
    import ossci.suite as s
    real = s.definitions
    monkeypatch.setattr(s, "definitions", lambda tdir, cfg=None: real(td, cfg))
    doc = new_doc(tmp_path)
    (tmp_path / "rb3gen2.qcomflash.tar.gz").write_bytes(b"x")
    lava = FakeLava()
    run.submit(argparse.Namespace(doc=str(doc), packages=str(tmp_path), td=td), lava=lava)
    t = json.load(open(doc))["targets"][0]
    assert t["state"] == "queued" and t["lava"]["job_id"] == 777 and t["lava"]["device"] == "rb3g2-01"
    assert "device: rb3g2-01" in lava.submitted[0]
    assert "x" not in [line.split(": ")[-1] for line in lava.submitted[0].splitlines() if "Authorization" in line]


@pytest.mark.parametrize("value, why", [(None, "PIN_BL2_RB3GEN2 is not set"),
                                        ("H4sI", "PIN_BL2_RB3GEN2 is not gzip"),
                                        (None, "does not match the pinned sha256")])
def test_submit_without_a_usable_bl2_skips_the_board(tmp_path, monkeypatch, value, why):
    import base64
    import gzip
    monkeypatch.setattr(run.package, "WORK", str(tmp_path))
    monkeypatch.setenv("LAVA_TOKEN", "x")
    if "match" in why:
        value = base64.b64encode(gzip.compress(b"not the pinned BL2")).decode()
    if value is None:
        monkeypatch.delenv("PIN_BL2_RB3GEN2", raising=False)
    else:
        monkeypatch.setenv("PIN_BL2_RB3GEN2", value)
    doc = new_doc(tmp_path)
    (tmp_path / "rb3gen2.qcomflash.tar.gz").write_bytes(b"x")
    lava = FakeLava()
    lava.upload = lambda path: pytest.fail("uploaded a package without its BL2")
    run.submit(argparse.Namespace(doc=str(doc), packages=str(tmp_path), td=str(tmp_path)), lava=lava)
    t = json.load(open(doc))["targets"][0]
    assert t["state"] == "skipped" and t["state_detail"].startswith("BL2 pin not available: ")
    assert why in t["state_detail"] and not lava.submitted


def test_close_after_cancel(tmp_path):
    doc = new_doc(tmp_path)
    run.main(["close", str(doc), "cancelled"])
    d = json.load(open(doc))
    assert d["state"] == "cancelled" and d["targets"][0]["state"] == "cancelled"
    schema.check(d)


def test_preflight_reasons():
    from ossci import preflight
    r = preflight.reasons(resolved("not published"), {"commit": SHA, "upstream": False,
                                                      "source": {"repo": None, "note": "PR"}})
    assert len(r) == 2 and "linux baseline" in r[0] and "rootfs pin" in r[1]
    assert preflight.reasons(resolved(), {"commit": SHA, "upstream": True, "source": {}}) == []


def test_backstop_restore_job_when_the_restore_did_not_pass(board):
    from ossci import jobs
    assert jobs.restored([{"suite": "stock-restore", "name": "uefi_ver", "result": "pass"}])
    assert not jobs.restored([{"suite": "stock-restore", "name": "uefi_ver", "result": "skip"}])
    assert not jobs.restored([])
    lava = FakeLava()
    r = run.backstop(lava, "rb3gen2", board, "rb3g2-01", "1-1")
    assert r["result"] == "backstop" and r["backstop_job"] == 777
    y = lava.submitted[0]
    assert "device: rb3g2-01" in y and "stock-restore" in y and "qcomflash" in y
    assert "lava-test-shell" not in y and "definitions" not in y
    assert run.backstop(lava, "rb3gen2", board, None, "1-1")["result"] == "fail"
