import pytest

from ossci import refs

SHA = "a" * 40
BASE = {c: {"repo": "https://github.com/EmbeddedAndroid/x", "ref": "qcom/integration-1", "commit": "b" * 40}
        for c in ("tfa", "optee", "uboot", "linux")}


def test_empty_is_baseline():
    for c in ("tfa", "optee", "uboot", "linux"):
        assert refs.parse(c, "") == {"kind": "baseline"}
        assert refs.parse(c, "   ") == {"kind": "baseline"}


def test_owner_repo_ref_every_component():
    for c in ("tfa", "optee", "uboot", "linux"):
        got = refs.parse(c, "EmbeddedAndroid/optee_os@pkvm-p2/p22-fw-smmu")
        assert got == {"kind": "repo", "repo": "https://github.com/EmbeddedAndroid/optee_os",
                       "ref": "pkvm-p2/p22-fw-smmu"}


def test_url_repo_and_commit_ref():
    got = refs.parse("uboot", "https://git.u-boot-project.org/u-boot/u-boot.git@" + SHA)
    assert got["repo"] == "https://git.u-boot-project.org/u-boot/u-boot.git" and got["ref"] == SHA


def test_gerrit_forms():
    assert refs.parse("tfa", "gerrit:56040") == {"kind": "gerrit", "change": 56040, "patchset": None}
    assert refs.parse("tfa", "gerrit:56040/3") == {"kind": "gerrit", "change": 56040, "patchset": 3}


def test_pr_and_lore_forms():
    assert refs.parse("optee", "pr:8223") == {"kind": "pr", "number": 8223}
    assert refs.parse("uboot", "lore:20261101-abc@linaro.org")["message_id"] == "20261101-abc@linaro.org"
    assert refs.parse("linux", "lore:<x.y@kernel.org>")["message_id"] == "x.y@kernel.org"


@pytest.mark.parametrize("comp,text", [
    ("optee", "gerrit:1"),          # gerrit is TF-A only
    ("tfa", "pr:1"),                # pr is OP-TEE only
    ("tfa", "lore:a@b"),            # lore is U-Boot and Linux only
    ("optee", "lore:a@b"),
    ("uboot", "pr:5"),
    ("linux", "gerrit:5"),
    ("tfa", "gerrit:abc"),
    ("tfa", "gerrit:1/x"),
    ("optee", "pr:"),
    ("uboot", "lore:not-a-message-id"),
    ("uboot", "EmbeddedAndroid/u-boot"),              # no ref
    ("uboot", "EmbeddedAndroid/u-boot@main;rm -rf /"),
    ("uboot", "EmbeddedAndroid/u-boot@$(id)"),
    ("uboot", "EmbeddedAndroid/u-boot@-c"),
    ("uboot", "EmbeddedAndroid/u-boot@a..b"),
    ("uboot", "../x@main"),
    ("uboot", "http://insecure.example/x.git@main"),
    ("uboot", "a/b/c@main"),
    ("fsbl", "a/b@main"),
])
def test_refused(comp, text):
    with pytest.raises(refs.BadInput):
        refs.parse(comp, text)


def test_resolve_baseline_keeps_pending():
    base = dict(BASE["linux"], pending="not published")
    s = refs.resolve("linux", {"kind": "baseline"}, base)
    assert s["role"] == "baseline" and s["commit"] == "b" * 40 and s["pending"] == "not published"


def test_resolve_repo_uses_ls_remote():
    calls = []

    def ls(repo, ref):
        calls.append((repo, ref))
        return SHA
    s = refs.resolve("optee", refs.parse("optee", "EmbeddedAndroid/optee_os@topic"), BASE["optee"], ls=ls)
    assert s["commit"] == SHA and s["role"] == "under-test"
    assert calls == [("https://github.com/EmbeddedAndroid/optee_os", "topic")]


def test_resolve_refuses_a_non_commit():
    with pytest.raises(refs.BadInput):
        refs.resolve("optee", refs.parse("optee", "a/b@x"), BASE["optee"], ls=lambda r, f: "zzz")


def gerrit_doc(project="TF-A/trusted-firmware-a"):
    return {"project": project, "subject": "feat(qcom): x",
            "revisions": {"1" * 40: {"_number": 1, "ref": "refs/changes/40/56040/1"},
                          "2" * 40: {"_number": 2, "ref": "refs/changes/40/56040/2"}}}


def test_resolve_gerrit_latest_and_given_patchset():
    s = refs.resolve("tfa", refs.parse("tfa", "gerrit:56040"), BASE["tfa"], get=lambda u: gerrit_doc())
    assert s["commit"] == "2" * 40 and s["ref"].endswith("/2") and s["link"].endswith("/56040/2")
    s = refs.resolve("tfa", refs.parse("tfa", "gerrit:56040/1"), BASE["tfa"], get=lambda u: gerrit_doc())
    assert s["commit"] == "1" * 40


def test_resolve_gerrit_wrong_project_or_patchset():
    with pytest.raises(refs.BadInput):
        refs.resolve("tfa", refs.parse("tfa", "gerrit:56040"), BASE["tfa"], get=lambda u: gerrit_doc("other"))
    with pytest.raises(refs.BadInput):
        refs.resolve("tfa", refs.parse("tfa", "gerrit:56040/9"), BASE["tfa"], get=lambda u: gerrit_doc())


def test_resolve_pr():
    doc = {"head": {"sha": SHA}, "html_url": "https://github.com/OP-TEE/optee_os/pull/8223", "title": "t"}
    s = refs.resolve("optee", refs.parse("optee", "pr:8223"), BASE["optee"], get=lambda u: doc)
    assert s["commit"] == SHA and s["ref"] == "refs/pull/8223/head"
    assert s["repo"] == "https://github.com/OP-TEE/optee_os"


def test_resolve_lore_applies_on_the_baseline():
    s = refs.resolve("uboot", refs.parse("uboot", "lore:a.b@c.d"), BASE["uboot"])
    assert s["commit"] == BASE["uboot"]["commit"] and s["series"]["message_id"] == "a.b@c.d"
    assert s["role"] == "under-test"


def test_resolve_all_takes_baseline_for_empty():
    got = refs.resolve_all({"optee": "a/b@x"}, baseline=BASE, ls=lambda r, f: SHA)
    assert got["tfa"]["role"] == "baseline" and got["optee"]["role"] == "under-test"
    assert set(got) == {"tfa", "optee", "uboot", "linux"}
