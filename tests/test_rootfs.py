import os

import pytest

from conftest import git
from ossci import rootfs


def pin(commit):
    return {"commit": commit, "manifest": "manifests/kodiak.xml",
            "arch": {"arm64": {"makefile": "kodiak.mk", "make_args": ["TEST=y"]}}}


def test_pristine_tree_passes(repo):
    r, c = repo
    assert rootfs.check(str(r), pin(c)) == c


def test_ignored_build_output_is_fine(repo):
    r, c = repo
    os.makedirs(r / "out")
    (r / "out" / "x").write_text("built")
    assert rootfs.check(str(r), pin(c)) == c


def test_other_commit_refused(repo):
    r, c = repo
    with pytest.raises(rootfs.NotPristine, match="the pin is"):
        rootfs.check(str(r), pin("f" * 40))


def test_patched_tree_refused(repo):
    """A patch applied as a commit on top of the pin: HEAD moves."""
    r, c = repo
    (r / "qcom.mk").write_text("BR2_PACKAGE_X = y\n")
    git(r, "add", "-A")
    git(r, "commit", "-qm", "local patch")
    with pytest.raises(rootfs.NotPristine, match="HEAD is"):
        rootfs.check(str(r), pin(c))


def test_patch_applied_to_the_worktree_refused(repo):
    """git apply without a commit: HEAD is the pin, the tree is not."""
    r, c = repo
    (r / "kodiak.mk").write_text("all:\n\techo patched\n")
    with pytest.raises(rootfs.NotPristine, match="changed"):
        rootfs.check(str(r), pin(c))


def test_untracked_file_refused(repo):
    r, c = repo
    (r / "extra.patch").write_text("diff")
    with pytest.raises(rootfs.NotPristine, match="changed"):
        rootfs.check(str(r), pin(c))


def test_untracked_allowed_after_build_but_not_tracked_changes(repo):
    r, c = repo
    (r / "staged-firmware.bin").write_text("x")
    assert rootfs.check(str(r), pin(c), tracked_only=True) == c
    (r / "kodiak.mk").write_text("changed\n")
    with pytest.raises(rootfs.NotPristine):
        rootfs.check(str(r), pin(c), tracked_only=True)


def test_am_in_progress_refused(repo):
    r, c = repo
    os.makedirs(r / ".git" / "rebase-apply")
    with pytest.raises(rootfs.NotPristine, match="rebase-apply"):
        rootfs.check(str(r), pin(c))


def test_stash_refused(repo):
    r, c = repo
    (r / "kodiak.mk").write_text("changed\n")
    git(r, "stash", "-q")
    with pytest.raises(rootfs.NotPristine, match="stash"):
        rootfs.check(str(r), pin(c))


def test_key_and_fingerprint_follow_the_inputs(repo):
    _, c = repo
    k1 = rootfs.key("1" * 40, "arm64", pin(c))
    k2 = rootfs.key("2" * 40, "arm64", pin(c))
    assert rootfs.key_id(k1) != rootfs.key_id(k2)
    assert rootfs.fingerprint("1" * 40, "arm64", pin(c)) == rootfs.fingerprint("1" * 40, "arm64", pin(c))
    assert rootfs.fingerprint("1" * 40, "arm64", pin(c)).startswith("ossci-rootfs-%s-11111111-" % c[:8])
    p2 = pin(c)
    p2["arch"]["arm64"]["make_args"] = ["TEST=n"]
    assert rootfs.key_id(rootfs.key("1" * 40, "arm64", p2)) != rootfs.key_id(k1)
