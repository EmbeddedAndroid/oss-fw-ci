import base64
import gzip
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


def bl2(data):
    return {"file": "tz-rb3gen2.mbn", "secret": "PIN_BL2_RB3GEN2", "sha256": hashlib.sha256(data).hexdigest()}


def secret(data):
    return base64.b64encode(gzip.compress(data, 9)).decode()


def test_insert_bl2_from_the_secret(monkeypatch, tmp_path):
    monkeypatch.setattr(package, "WORK", str(tmp_path))
    data = b"BL2 from the secret"
    pkg = tmp_path / "p.tar.gz"
    make_pkg(pkg)
    package.insert_bl2(str(pkg), "rb3gen2", env={"PIN_BL2_RB3GEN2": secret(data) + "\n"},
                       board={"bl2": bl2(data)})
    src = package.sources(str(pkg))
    assert src["deferred"] == [] and src["files"]["tz.mbn"] == hashlib.sha256(data).hexdigest()
    with tarfile.open(pkg) as t:
        assert t.extractfile("ossci-rb3gen2/tz.mbn").read() == data


@pytest.mark.parametrize("value, why", [
    (None, "PIN_BL2_RB3GEN2 is not set"),
    ("", "PIN_BL2_RB3GEN2 is not set"),
    ("not base64 !", "is not gzip \\+ base64"),
    (base64.b64encode(b"plain, not gzip").decode(), "is not gzip \\+ base64"),
    (secret(b"another image"), "does not match the pinned sha256"),
])
def test_secret_file_refusals(monkeypatch, tmp_path, value, why):
    monkeypatch.setattr(package, "WORK", str(tmp_path))
    env = {} if value is None else {"PIN_BL2_RB3GEN2": value}
    with pytest.raises(SystemExit, match=why) as e:
        package.secret_file(bl2(b"the pinned image"), env)
    if value:
        assert value not in str(e.value)


def test_insert_bl2_refusal_leaves_the_package(monkeypatch, tmp_path):
    monkeypatch.setattr(package, "WORK", str(tmp_path))
    pkg = tmp_path / "p.tar.gz"
    make_pkg(pkg)
    before = pkg.read_bytes()
    with pytest.raises(SystemExit):
        package.insert_bl2(str(pkg), "rb3gen2", env={"PIN_BL2_RB3GEN2": secret(b"wrong")},
                           board={"bl2": bl2(b"right")})
    assert pkg.read_bytes() == before and package.sources(str(pkg))["deferred"] == ["tz.mbn"]


def test_every_board_pins_its_bl2_by_secret():
    from ossci import config
    for name, b in config.boards().items():
        p = b["bl2"]
        assert p["secret"] == "PIN_BL2_" + name.upper().replace("-", "_")
        assert len(p["sha256"]) == 64 and p["file"] and p["fingerprint"]
        assert "release" not in p and "private" not in p


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
    package.insert_bl2(str(pkg), "rb3gen2", env={}, board={"bl2": bl2(data)})
    src = package.sources(str(pkg))
    assert src["deferred"] == [] and src["files"]["tz.mbn"] == hashlib.sha256(data).hexdigest()
    with tarfile.open(pkg) as t:
        assert t.extractfile("ossci-rb3gen2/tz.mbn").read() == data
