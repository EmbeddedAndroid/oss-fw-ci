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
    assert t["bl2"]["fingerprint"] == "QCDFP-261102-526"
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


def test_submit_picks_an_idle_healthy_device_and_never_production(tmp_path, monkeypatch, td, board):
    from ossci import package
    monkeypatch.setattr(run.config, "board", lambda name: board)
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
