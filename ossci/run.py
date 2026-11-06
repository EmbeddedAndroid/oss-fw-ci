"""The run document (results/<run>.json, ossci-run/1) and the steps that
move it, one subcommand per pipeline step; run.yml and the lease driver
call the same ones.

  new <doc> --id ID --inputs resolved.json [--boards "a b"] [--title T]
      [--requester R] [--ci-url U] [--kind adhoc|nightly] [--driver workflow|lease]
  rootfs <doc> <rootfs.json>           the rootfs that was built (or reused)
  built <doc> <board> <builds.json>    what the build jobs made for a board
  skip <doc> <reason> [--board B]      mark targets skipped (all when no board)
  submit <doc> <packages dir> <test-definitions tree>
  monitor <doc>                        job state and queue position
  collect <doc> [--baseline <doc or lava:<job id>>]
  finished <doc>                       exit 0 when every target is final
  close <doc> <cancelled|failure>
LAVA is reached with $LAVA_TOKEN (fwci.lava_mcp); nothing secret is ever
written to the document or printed."""
import argparse
import fnmatch
import json
import os
import re
import sys

from fwci import lava_jobs

from . import collect, config, gate, jobs, justify, package, schema

FINAL = ("done", "skipped", "error", "cancelled")
LAVA_URL = os.environ.get("LAVA_URL", "https://lava.infra.foundries.io")


def load(path):
    return schema.check(json.load(open(path)))


def save(path, doc):
    doc["run"]["updated"] = schema.now()
    schema.check(doc)
    tmp = path + ".tmp"
    json.dump(doc, open(tmp, "w"), indent=1, sort_keys=False)
    os.replace(tmp, path)


def overall(doc):
    states = [t["state"] for t in doc["targets"]]
    if all(s in FINAL for s in states):
        return "done"
    if any(s in ("flashing", "testing") for s in states):
        return "testing"
    if any(s == "queued" for s in states):
        return "testing"
    return "building"


def new(a):
    inputs = json.load(open(a.inputs))
    all_boards = config.boards()
    names = a.boards.split() if a.boards else sorted(all_boards)
    for n in names:
        if n not in all_boards:
            raise SystemExit("unknown board %s" % n)
    m = re.match(r"^(\d+)-(\d+)$", a.id)
    if not m:
        raise SystemExit("run id is <run>-<attempt>")
    s = config.suite()
    r = config.rootfs()
    targets = []
    for n in names:
        b = all_boards[n]
        targets.append({"board": n, "device_type": b["lava"]["device_type"], "state": "building",
                        "fingerprint": gate.run_fingerprint(m.group(1), m.group(2), n),
                        "bl2": {k: b["bl2"][k] for k in ("release", "file", "sha256", "fingerprint")}})
    doc = {"schema": "ossci-run/1",
           "run": {"id": a.id, "kind": a.kind, "title": a.title or "", "requester": a.requester or "",
                   "created": schema.now(), "updated": schema.now(), "ci_url": a.ci_url,
                   "driver": a.driver, "baseline": None},
           "state": "building",
           "inputs": {c: {k: v for k, v in inputs[c].items()} for c in ("tfa", "optee", "uboot", "linux")},
           "suite": {"repo": s["repo"], "branch": s["branch"], "commit": s["commit"], "plan": s["plan"],
                     "exclude": s.get("exclude", {})},
           "rootfs": {"repo": r["repo"], "commit": r["commit"], "upstream": bool(r.get("upstream")),
                      "note": (r.get("source") or {}).get("note", "")},
           "targets": targets}
    save(a.doc, doc)


def target(doc, board):
    for t in doc["targets"]:
        if t["board"] == board:
            return t
    raise SystemExit("no target %s" % board)


def rootfs(a):
    doc = load(a.doc)
    info = json.load(open(a.info))
    doc["rootfs"].update({k: info[k] for k in ("fingerprint", "sha256", "key", "makefile", "make_args", "manifest")
                          if k in info})
    save(a.doc, doc)


def built(a):
    doc = load(a.doc)
    t = target(doc, a.board)
    info = json.load(open(a.info))
    t["builds"] = info.get("components", {})
    t["package"] = info.get("package")
    if info.get("error"):
        t["state"], t["state_detail"] = "error", info["error"][:500]
    save(a.doc, doc)


def skip(a):
    doc = load(a.doc)
    for t in doc["targets"]:
        if (not a.board or t["board"] == a.board) and t["state"] not in FINAL:
            t["state"], t["state_detail"] = "skipped", a.reason
    doc["state"] = overall(doc)
    save(a.doc, doc)


def choose_devices(lava, device_type, exclude):
    devs = [d for d in lava.devices(device_type) if d.get("health") == "Good"
            and not any(fnmatch.fnmatch(d["hostname"], p) for p in exclude)]
    devs.sort(key=lambda d: (d.get("state") != "Idle", d["hostname"]))
    return [d["hostname"] for d in devs]


def submit(a, lava=None):
    from fwci.lava_mcp import Lava, Rejected
    doc = load(a.doc)
    if not os.environ.get("LAVA_TOKEN"):
        for t in doc["targets"]:
            if t["state"] not in FINAL:
                t["state"], t["state_detail"] = "skipped", "hardware skipped: no LAVA_TOKEN in the lava-hw environment"
        doc["state"] = overall(doc)
        save(a.doc, doc)
        return
    lava = lava or Lava()
    rootfs_fp = doc["rootfs"].get("fingerprint", "")
    meta = {"run": doc["run"]["id"], "ci_url": doc["run"].get("ci_url") or "", "requester": doc["run"].get("requester", ""),
            "suite": doc["suite"]["commit"], "rootfs": doc["rootfs"]["commit"]}
    for c in ("tfa", "optee", "uboot", "linux"):
        meta[c] = doc["inputs"][c]["commit"]
    for t in doc["targets"]:
        if t["state"] in FINAL or t.get("lava"):
            continue
        b = config.board(t["board"])
        pkg = os.path.join(a.packages, "%s.qcomflash.tar.gz" % t["board"])
        if not os.path.exists(pkg):
            t["state"], t["state_detail"] = "error", "no package was built"
            continue
        try:
            package.insert_bl2(pkg, t["board"], board=b)
        except SystemExit as e:
            t["state"], t["state_detail"] = "skipped", "BL2 pin not available: %s" % e
            continue
        url, token_name = lava.upload(pkg)
        devices = choose_devices(lava, b["lava"]["device_type"], b["lava"].get("exclude_devices", []))
        refused = []
        for dev in devices:
            definition = jobs.generate(t["board"], b, t["fingerprint"], rootfs_fp, a.td, url, token_name,
                                       package.top_dir(t["board"]), meta, device=dev)
            try:
                job_id = lava.submit(lava_jobs.to_yaml(definition))
            except Rejected as e:
                if "permission" in e.message:
                    refused.append(dev)
                    continue
                t["state"], t["state_detail"] = "error", "LAVA refused the job: %s" % e.message[:300]
                break
            except Exception as e:
                t["state"], t["state_detail"] = "error", "submit outcome unknown: %s" % type(e).__name__
                break
            t["lava"] = {"job_id": job_id, "url": "%s/scheduler/job/%d" % (LAVA_URL, job_id),
                         "device": dev, "health": None}
            t["state"] = "queued"
            break
        else:
            t["state"] = "error"
            t["state_detail"] = ("no healthy %s device accepts the job (refused: %s)"
                                 % (b["lava"]["device_type"], " ".join(refused) or "none healthy"))
        save(a.doc, doc)
    doc["state"] = overall(doc)
    save(a.doc, doc)


def monitor(a, lava=None):
    from fwci import collect as fc
    from fwci.lava_mcp import Lava
    doc = load(a.doc)
    lava = lava or Lava()
    queue = None
    for t in doc["targets"]:
        if not t.get("lava") or t["state"] in FINAL:
            continue
        j = lava.job(t["lava"]["job_id"])
        t["state"] = fc.STATE.get(j.get("state"), "queued")
        t["lava"]["device"] = j.get("actual_device") or t["lava"].get("device")
        t["lava"]["health"] = j.get("health")
        if t["state"] == "queued":
            queue = queue if queue is not None else lava.queue()
            t["queue_position"] = fc.queue_position(queue, t["lava"]["job_id"], t["device_type"])
        else:
            t.pop("queue_position", None)
        if t["state"] == "done":
            # Final only once collected.
            t["state"] = "testing"
    doc["state"] = overall(doc)
    save(a.doc, doc)


def site_baseline(site, board):
    """The board's latest nightly in a gh-pages worktree, as a path."""
    idx = os.path.join(site, "index.json")
    if not os.path.exists(idx):
        return None
    rid = json.load(open(idx)).get("latest_nightly", {}).get(board)
    path = os.path.join(site, "results", "%s.json" % rid) if rid else None
    return path if path and os.path.exists(path) else None


def baseline_target(spec, board, lava):
    if not spec:
        return None, None
    if spec.startswith("lava:"):
        job_id = int(spec[5:])
        url = "%s/scheduler/job/%d" % (LAVA_URL, job_id)
        return collect.lava_reference(job_id, lava.results(job_id), url), "lava:%d" % job_id
    b = load(spec)
    for t in b["targets"]:
        if t["board"] == board:
            return t, b["run"]["id"]
    return None, None


def do_collect(a, lava=None):
    from fwci import collect as fc
    from fwci.lava_mcp import Lava
    doc = load(a.doc)
    lava = lava or Lava()
    table = justify.entries()
    flakes = (config.load("flakes") or {}).get("flakes") or []
    for i, t in enumerate(doc["targets"]):
        if not t.get("lava") or t["state"] in FINAL:
            continue
        j = lava.job(t["lava"]["job_id"])
        if j.get("state") != "Finished":
            continue
        url = t["lava"]["url"]
        log = lava.log(t["lava"]["job_id"])
        entries = fc.log_entries(log)
        b = config.board(t["board"])
        base = {k: v for k, v in t.items() if k not in ("cases", "diff", "verdict", "counts")}
        base["stack"] = "open"
        nt = collect.target(base, b, j, lava.results(t["lava"]["job_id"]), entries, url, log, flakes, table)
        spec = a.baseline or (site_baseline(a.baseline_site, t["board"]) if a.baseline_site else "")
        bt, bid = baseline_target(spec, t["board"], lava)
        if bt is not None:
            collect.compare(nt, bt, bid)
            doc["run"]["baseline"] = bid
        doc["targets"][i] = nt
    doc["state"] = overall(doc)
    save(a.doc, doc)


def finished(a):
    doc = load(a.doc)
    sys.exit(0 if all(t["state"] in FINAL for t in doc["targets"]) else 1)


def close(a):
    doc = load(a.doc)
    final = "cancelled" if a.conclusion == "cancelled" else "error"
    for t in doc["targets"]:
        if t["state"] not in FINAL:
            t["state"] = final
            t["state_detail"] = "the workflow was %s before this target finished" % (
                "cancelled" if final == "cancelled" else "stopped by a failure")
    doc["state"] = final if any(t["state"] == final for t in doc["targets"]) else "done"
    doc["note"] = "closed after the workflow ended (%s)" % a.conclusion
    save(a.doc, doc)


def main(argv):
    p = argparse.ArgumentParser(prog="ossci.run")
    sub = p.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("new")
    n.add_argument("doc")
    n.add_argument("--id", required=True)
    n.add_argument("--inputs", required=True)
    n.add_argument("--boards", default="")
    n.add_argument("--title", default="")
    n.add_argument("--requester", default="")
    n.add_argument("--ci-url", default=None)
    n.add_argument("--kind", default="adhoc", choices=("adhoc", "nightly"))
    n.add_argument("--driver", default="workflow", choices=("workflow", "lease"))
    r = sub.add_parser("rootfs")
    r.add_argument("doc")
    r.add_argument("info")
    bu = sub.add_parser("built")
    bu.add_argument("doc")
    bu.add_argument("board")
    bu.add_argument("info")
    s = sub.add_parser("skip")
    s.add_argument("doc")
    s.add_argument("reason")
    s.add_argument("--board")
    su = sub.add_parser("submit")
    su.add_argument("doc")
    su.add_argument("packages")
    su.add_argument("td")
    m = sub.add_parser("monitor")
    m.add_argument("doc")
    c = sub.add_parser("collect")
    c.add_argument("doc")
    c.add_argument("--baseline", default="")
    c.add_argument("--baseline-site", default="")
    f = sub.add_parser("finished")
    f.add_argument("doc")
    cl = sub.add_parser("close")
    cl.add_argument("doc")
    cl.add_argument("conclusion")
    a = p.parse_args(argv)
    {"new": new, "rootfs": rootfs, "built": built, "skip": skip, "submit": submit, "monitor": monitor,
     "collect": do_collect, "finished": finished, "close": close}[a.cmd](a)


if __name__ == "__main__":
    main(sys.argv[1:])
