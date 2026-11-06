import hashlib
import io
import json
import tarfile

import pytest

from ossci import package


def make_pkg(path):
    with tarfile.open(path, "w:gz") as t:
        meta = json.dumps({"deferred": ["tz.mbn"], "files": {}}).encode()
        info = tarfile.TarInfo("ossci-rb3gen2/SOURCES.json")
        info.size = len(meta)
        t.addfile(info, io.BytesIO(meta))


def pin(data):
    return {"file": "tz-rb3gen2.mbn", "release": "bl2-x", "sha256": hashlib.sha256(data).hexdigest()}


def test_private_file_from_the_store(monkeypatch, tmp_path):
    monkeypatch.setattr(package, "WORK", str(tmp_path))
    data = b"BL2 bytes"
    seen = []

    def get(url, token, accept):
        seen.append((url, token))
        if url.endswith("/releases/tags/bl2-x"):
            return json.dumps({"assets": [{"name": "tz-rb3gen2.mbn",
                                           "url": "https://api.github.com/repos/o/r/releases/assets/1"}]}).encode()
        return data
    assert package.private_file(pin(data), {"OSSCI_PRIVATE_TOKEN": "t"}, get=get) == data
    assert all(u.startswith("https://api.github.com/") for u, _ in seen)


def test_private_file_refusals(monkeypatch, tmp_path):
    monkeypatch.setattr(package, "WORK", str(tmp_path))
    with pytest.raises(SystemExit, match="OSSCI_PRIVATE_TOKEN is not set"):
        package.private_file(pin(b"x"), {})
    rel = json.dumps({"assets": [{"name": "tz-rb3gen2.mbn", "url": "https://api.github.com/a/1"}]}).encode()
    with pytest.raises(SystemExit, match="does not match"):
        package.private_file(pin(b"x"), {"OSSCI_PRIVATE_TOKEN": "t"},
                             get=lambda u, t, a: rel if "tags" in u else b"other")
    evil = json.dumps({"assets": [{"name": "tz-rb3gen2.mbn", "url": "https://evil.example/a"}]}).encode()
    with pytest.raises(SystemExit, match="cannot be read") as e:
        package.private_file(pin(b"x"), {"OSSCI_PRIVATE_TOKEN": "secret-token"}, get=lambda u, t, a: evil)
    assert "secret-token" not in str(e.value) and "evil" not in str(e.value)
    with pytest.raises(SystemExit, match="not in release"):
        package.private_file(pin(b"x"), {"OSSCI_PRIVATE_TOKEN": "t"},
                             get=lambda u, t, a: json.dumps({"assets": []}).encode())


def test_staged_pin_and_insert(monkeypatch, tmp_path):
    monkeypatch.setattr(package, "WORK", str(tmp_path))
    import ossci.fetch as f
    monkeypatch.setattr(f, "WORK", str(tmp_path))
    data = b"staged BL2"
    (tmp_path / "pins").mkdir()
    (tmp_path / "pins" / "tz-rb3gen2.mbn").write_bytes(data)
    pkg = tmp_path / "p.tar.gz"
    make_pkg(pkg)
    package.insert_bl2(str(pkg), "rb3gen2", env={}, board={"bl2": pin(data)})
    src = package.sources(str(pkg))
    assert src["deferred"] == [] and src["files"]["tz.mbn"] == hashlib.sha256(data).hexdigest()
    with tarfile.open(pkg) as t:
        assert t.extractfile("ossci-rb3gen2/tz.mbn").read() == data
