"""Resolve the run inputs to commits (the resolve job).

Forms, per component (docs/DESIGN.md "Inputs"):
  ""                          the baseline pin (config/baseline.yaml)
  owner/repo@ref              a GitHub repository at a branch, tag or commit
  https://host/path.git@ref   any git repository at a branch, tag or commit
  gerrit:<change>[/<ps>]      a TF-A Gerrit change (latest patch set by default)
  pr:<number>                 an OP-TEE/optee_os pull request head
  lore:<message-id>           a series from lore, applied on the baseline pin
                              (U-Boot and Linux)
Free text from workflow_dispatch is validated here before anything uses
it; nothing from an input reaches a shell unquoted.

python3 -m ossci.refs <out.json> [--tfa X] [--optee X] [--uboot X] [--linux X]
"""
import argparse
import json
import re
import subprocess
import sys
import urllib.request

from . import COMPONENTS, config

GERRIT = "https://review.trustedfirmware.org"
GERRIT_PROJECT = "TF-A/trusted-firmware-a"
OPTEE_REPO = "OP-TEE/optee_os"
FORMS = {
    "tfa": ("repo", "gerrit"),
    "optee": ("repo", "pr"),
    "uboot": ("repo", "lore"),
    "linux": ("repo", "lore"),
}
SHA = re.compile(r"^[0-9a-f]{40}$")
REF = re.compile(r"^[A-Za-z0-9._/+-]{1,200}$")
OWNER_REPO = re.compile(r"^([A-Za-z0-9_.-]{1,100})/([A-Za-z0-9_.-]{1,100})$")
URL = re.compile(r"^https://[A-Za-z0-9.-]+(?::\d+)?/[A-Za-z0-9_./~+-]{1,300}$")
MSGID = re.compile(r"^<?([^<>\s@]{1,200}@[^<>\s@]{1,200})>?$")


class BadInput(ValueError):
    pass


def parse(component, text):
    """The input of one component as a dict: kind (baseline, repo, gerrit,
    pr, lore) and its fields. Raises BadInput for anything else."""
    if component not in FORMS:
        raise BadInput("unknown component %r" % component)
    text = (text or "").strip()
    if not text:
        return {"kind": "baseline"}
    if text.startswith("gerrit:"):
        m = re.fullmatch(r"gerrit:(\d{1,7})(?:/(\d{1,4}))?", text)
        if not m:
            raise BadInput("%s: gerrit:<change>[/<patch set>], got %r" % (component, text))
        out = {"kind": "gerrit", "change": int(m.group(1)),
               "patchset": int(m.group(2)) if m.group(2) else None}
    elif text.startswith("pr:"):
        m = re.fullmatch(r"pr:(\d{1,7})", text)
        if not m:
            raise BadInput("%s: pr:<number>, got %r" % (component, text))
        out = {"kind": "pr", "number": int(m.group(1))}
    elif text.startswith("lore:"):
        m = MSGID.fullmatch(text[5:])
        if not m:
            raise BadInput("%s: lore:<message-id>, got %r" % (component, text))
        out = {"kind": "lore", "message_id": m.group(1)}
    else:
        if "@" not in text:
            raise BadInput("%s: owner/repo@ref, got %r" % (component, text))
        repo, ref = text.rsplit("@", 1)
        if not REF.fullmatch(ref) or ".." in ref or ref.startswith("-"):
            raise BadInput("%s: bad ref %r" % (component, ref))
        if ".." in repo or repo.startswith(".") or "/." in repo:
            raise BadInput("%s: bad repository %r" % (component, repo))
        if OWNER_REPO.fullmatch(repo):
            url = "https://github.com/%s" % repo
        elif URL.fullmatch(repo) and ".." not in repo:
            url = repo
        else:
            raise BadInput("%s: bad repository %r" % (component, repo))
        out = {"kind": "repo", "repo": url, "ref": ref}
    if out["kind"] not in FORMS[component]:
        raise BadInput("%s does not take %s inputs (it takes %s, or empty for the baseline)"
                       % (component, out["kind"], ", ".join(FORMS[component])))
    return out


def ls_remote(repo, ref):
    """The commit a ref names in a remote (branch, tag peeled, or a full
    commit id as given)."""
    if SHA.fullmatch(ref):
        return ref
    out = subprocess.run(["git", "ls-remote", "--", repo, ref, "refs/heads/" + ref, "refs/tags/" + ref,
                          "refs/tags/%s^{}" % ref], check=True, capture_output=True, text=True).stdout
    found = {}
    for line in out.splitlines():
        sha, name = line.split("\t")
        found[name] = sha
    for name in ("refs/tags/%s^{}" % ref, "refs/tags/" + ref, "refs/heads/" + ref, ref):
        if name in found:
            return found[name]
    raise BadInput("%s has no ref %s" % (repo, ref))


def http_json(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"Accept": "application/json"}),
                                timeout=60) as r:
        text = r.read().decode()
    # Gerrit prefixes its JSON with )]}' against XSSI.
    return json.loads(text[4:] if text.startswith(")]}'") else text)


def gerrit(change, patchset, get=http_json):
    d = get("%s/changes/%d?o=ALL_REVISIONS" % (GERRIT, change))
    if d.get("project") != GERRIT_PROJECT:
        raise BadInput("gerrit change %d is in %s, not %s" % (change, d.get("project"), GERRIT_PROJECT))
    revs = {r["_number"]: (sha, r) for sha, r in d["revisions"].items()}
    ps = patchset or max(revs)
    if ps not in revs:
        raise BadInput("gerrit change %d has no patch set %d" % (change, ps))
    sha, r = revs[ps]
    return {"repo": "%s/%s" % (GERRIT, GERRIT_PROJECT), "ref": r["ref"], "commit": sha,
            "link": "%s/c/%s/+/%d/%d" % (GERRIT, GERRIT_PROJECT, change, ps),
            "title": d.get("subject", "")}


def pull(number, get=http_json):
    d = get("https://api.github.com/repos/%s/pulls/%d" % (OPTEE_REPO, number))
    return {"repo": "https://github.com/%s" % OPTEE_REPO, "ref": "refs/pull/%d/head" % number,
            "commit": d["head"]["sha"], "link": d["html_url"], "title": d.get("title", "")}


def resolve(component, spec, base, ls=ls_remote, get=http_json):
    """One component's source: repo, ref, commit, link, the input as given
    and, for a lore series, the base it is applied on (the build job
    fetches and applies it with b4: ossci.series)."""
    kind = spec["kind"]
    if kind == "baseline":
        src = {"repo": base["repo"], "ref": base["ref"], "commit": base["commit"]}
        if base.get("pending"):
            src["pending"] = base["pending"]
        role = "baseline"
    elif kind == "repo":
        src = {"repo": spec["repo"], "ref": spec["ref"], "commit": ls(spec["repo"], spec["ref"])}
        role = "under-test"
    elif kind == "gerrit":
        src = gerrit(spec["change"], spec["patchset"], get)
        role = "under-test"
    elif kind == "pr":
        src = pull(spec["number"], get)
        role = "under-test"
    elif kind == "lore":
        src = {"repo": base["repo"], "ref": base["ref"], "commit": base["commit"],
               "series": {"message_id": spec["message_id"],
                          "link": "https://lore.kernel.org/r/%s" % spec["message_id"]}}
        if base.get("pending"):
            src["pending"] = base["pending"]
        role = "under-test"
    else:
        raise BadInput(kind)
    src["role"] = role
    src["input"] = spec
    if not SHA.fullmatch(src["commit"]):
        raise BadInput("%s: %r is not a commit id" % (component, src["commit"]))
    return src


def resolve_all(inputs, baseline=None, ls=ls_remote, get=http_json):
    baseline = baseline or config.baseline()
    return {c: resolve(c, parse(c, inputs.get(c)), baseline[c], ls, get) for c in COMPONENTS}


def main(argv):
    p = argparse.ArgumentParser()
    p.add_argument("out")
    for c in COMPONENTS:
        p.add_argument("--" + c, default="")
    a = p.parse_args(argv)
    try:
        got = resolve_all({c: getattr(a, c) for c in COMPONENTS})
    except BadInput as e:
        raise SystemExit("bad input: %s" % e)
    json.dump(got, open(a.out, "w"), indent=1)
    for c, s in got.items():
        print("%s %s %s %s" % (c, s["role"], s["commit"][:12], s["repo"]))


if __name__ == "__main__":
    main(sys.argv[1:])
