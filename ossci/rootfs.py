"""The pinned test rootfs (config/rootfs.yaml).

python3 -m ossci.rootfs check <qcom-buildroot tree> [--tracked]
    exits 1 unless the tree is the pinned commit, unchanged: HEAD is the
    pin, nothing staged, modified or untracked (ignored build output
    aside), no commit on top, no stash, no am/rebase/merge in progress.
python3 -m ossci.rootfs key <test-definitions commit> <arch>
    prints the cache key: qcom-buildroot commit, test-definitions commit,
    architecture (and the makefile and make arguments it uses).
python3 -m ossci.rootfs fingerprint <test-definitions commit> <arch>
    prints the rootfs fingerprint, derived from the key: the image is
    built once per key, so every board and run boots the same bytes and
    the same fingerprint."""
import hashlib
import json
import os
import subprocess
import sys

from . import config


class NotPristine(Exception):
    pass


def git(tree, *args):
    return subprocess.run(["git", "-C", tree] + list(args), check=True, capture_output=True,
                          text=True).stdout


def check(tree, pin=None, tracked_only=False):
    """tracked_only: after the build, which stages output (firmware, the
    inference model) into untracked directories of the tree: only HEAD
    and the tracked files must be unchanged."""
    pin = pin or config.rootfs()
    head = git(tree, "rev-parse", "HEAD").strip()
    if head != pin["commit"]:
        raise NotPristine("HEAD is %s, the pin is %s" % (head, pin["commit"]))
    dirty = git(tree, "status", "--porcelain",
                "--untracked-files=%s" % ("no" if tracked_only else "all")).strip()
    if dirty:
        raise NotPristine("the tree is changed:\n" + dirty)
    gitdir = git(tree, "rev-parse", "--git-dir").strip()
    gitdir = gitdir if os.path.isabs(gitdir) else os.path.join(tree, gitdir)
    for state in ("rebase-apply", "rebase-merge", "MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD"):
        if os.path.exists(os.path.join(gitdir, state)):
            raise NotPristine("a %s is in progress" % state)
    if git(tree, "stash", "list").strip():
        raise NotPristine("the tree has stashed changes")
    return head


def key(td_commit, arch, pin=None):
    pin = pin or config.rootfs()
    a = pin["arch"][arch]
    return {"qcom_buildroot": pin["commit"], "test_definitions": td_commit, "arch": arch,
            "makefile": a["makefile"], "make_args": a["make_args"], "manifest": pin["manifest"],
            "manifest_overrides": {k: v["revision"] for k, v in (pin.get("manifest_overrides") or {}).items()}}


def key_id(k):
    return hashlib.sha256(json.dumps(k, sort_keys=True).encode()).hexdigest()[:16]


def fingerprint(td_commit, arch, pin=None):
    k = key(td_commit, arch, pin)
    return "ossci-rootfs-%s-%s-%s" % (k["qcom_buildroot"][:8], td_commit[:8], key_id(k)[:8])


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) in (2, 3) and a[0] == "check" and (len(a) == 2 or a[2] == "--tracked"):
        try:
            print("pristine %s" % check(a[1], tracked_only=len(a) == 3))
        except NotPristine as e:
            raise SystemExit("rootfs tree refused: %s" % e)
    elif len(a) == 3 and a[0] == "key":
        k = key(a[1], a[2])
        print(json.dumps(dict(k, id=key_id(k))))
    elif len(a) == 3 and a[0] == "fingerprint":
        print(fingerprint(a[1], a[2]))
    else:
        raise SystemExit(__doc__)
