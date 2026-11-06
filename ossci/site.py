"""The published site (gh-pages): results/<run>.json, the run documents,
and index.json, what the front page and agents read: per board the
latest nightly, and the recent runs with their state and counts.

python3 -m ossci.site <site dir> [<run doc>...]   copies the documents in
and rebuilds index.json."""
import json
import os
import shutil
import sys

from . import schema

RECENT = 50


def summary(doc):
    return {"id": doc["run"]["id"], "kind": doc["run"]["kind"], "title": doc["run"].get("title", ""),
            "requester": doc["run"].get("requester", ""), "created": doc["run"]["created"],
            "updated": doc["run"]["updated"], "state": doc["state"], "ci_url": doc["run"].get("ci_url"),
            "driver": doc["run"].get("driver"),
            "inputs": {c: {"role": v["role"], "commit": v["commit"], "repo": v["repo"],
                           "ref": v.get("ref", ""), "pending": v.get("pending")}
                       for c, v in doc["inputs"].items()},
            "rootfs": {"commit": doc["rootfs"]["commit"], "upstream": doc["rootfs"]["upstream"],
                       "note": doc["rootfs"].get("note", "")},
            "suite": doc["suite"]["commit"],
            "targets": [{"board": t["board"], "state": t["state"], "state_detail": t.get("state_detail", ""),
                         "queue_position": t.get("queue_position"),
                         "fingerprint_gate": t.get("fingerprint_gate", "not-run"),
                         "verdict": t.get("verdict", "not-run"), "counts": t.get("counts", {}),
                         "lava": t.get("lava"), "diff": t.get("diff")} for t in doc["targets"]]}


def build(site):
    runs = []
    d = os.path.join(site, "results")
    os.makedirs(d, exist_ok=True)
    for name in sorted(os.listdir(d)):
        if name.endswith(".json"):
            runs.append(schema.check(json.load(open(os.path.join(d, name)))))
    runs.sort(key=lambda r: r["run"]["created"], reverse=True)
    latest = {}
    for r in runs:
        if r["run"]["kind"] != "nightly":
            continue
        for t in r["targets"]:
            latest.setdefault(t["board"], r["run"]["id"])
    index = {"schema": "ossci-index/1", "updated": schema.now(), "latest_nightly": latest,
             "runs": [summary(r) for r in runs[:RECENT]]}
    tmp = os.path.join(site, "index.json.tmp")
    json.dump(index, open(tmp, "w"), indent=1)
    os.replace(tmp, os.path.join(site, "index.json"))
    return index


def add(site, docs):
    os.makedirs(os.path.join(site, "results"), exist_ok=True)
    for p in docs:
        doc = schema.check(json.load(open(p)))
        shutil.copy(p, os.path.join(site, "results", doc["run"]["id"] + ".json"))
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for f in os.listdir(os.path.join(here, "dashboard")):
        shutil.copy(os.path.join(here, "dashboard", f), os.path.join(site, f))
    return build(site)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    add(sys.argv[1], sys.argv[2:])
