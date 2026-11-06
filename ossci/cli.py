"""ossci: start a run and wait for it (docs/ossci.md).

  ossci run [--tfa X] [--optee X] [--uboot X] [--linux X] [--boards "a b"]
            [--title T] [--requester R] [--repo owner/name] [--ref main]
      dispatches run.yml (gh workflow run) and prints the run id
  ossci wait <run> [--site URL] [--interval S] [--timeout S]
      polls results/<run>.json until the run is final; prints per board
      the verdict and the per-case delta against the baseline; exits 0
      when every board passed (every case passed or is justified), 1 when
      one did not, 2 on timeout
Inputs are checked locally (ossci.refs.parse) before anything is sent."""
import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

from . import COMPONENTS, refs

REPO = "EmbeddedAndroid/oss-fw-ci"
SITE = "https://embeddedandroid.github.io/oss-fw-ci"
RAW = "https://raw.githubusercontent.com/%s/gh-pages" % REPO
FINAL = ("done", "skipped", "error", "cancelled")


def gh(*args):
    return subprocess.run(["gh"] + list(args), check=True, capture_output=True, text=True).stdout


def dispatch(a, run=gh):
    for c in COMPONENTS:
        refs.parse(c, getattr(a, c))
    args = ["workflow", "run", "run.yml", "--repo", a.repo, "--ref", a.ref]
    for c in COMPONENTS:
        args += ["-f", "%s=%s" % (c, getattr(a, c))]
    args += ["-f", "boards=%s" % a.boards, "-f", "title=%s" % a.title, "-f", "requester=%s" % a.requester]
    before = set(x["databaseId"] for x in json.loads(run("run", "list", "--repo", a.repo, "--workflow", "run.yml",
                                                         "--json", "databaseId", "--limit", "20")))
    run(*args)
    for _ in range(30):
        time.sleep(2)
        now = json.loads(run("run", "list", "--repo", a.repo, "--workflow", "run.yml", "--json",
                             "databaseId", "--limit", "20"))
        new = [x["databaseId"] for x in now if x["databaseId"] not in before]
        if new:
            return "%d-1" % max(new)
    raise SystemExit("dispatched, but the run did not show up; see gh run list --workflow run.yml")


def fetch_doc(base, run_id):
    try:
        with urllib.request.urlopen("%s/results/%s.json?t=%d" % (base, run_id, time.time()), timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def report(doc, out=sys.stdout):
    ok = True
    for t in doc["targets"]:
        v = t.get("verdict", "not-run")
        ok = ok and v == "pass"
        c = t.get("counts", {})
        print("%s: %s %s, gate %s, verdict %s, %d pass / %d fail / %d skip (%d justified)%s" % (
            t["board"], t["state"], t.get("state_detail", ""), t.get("fingerprint_gate", "not-run"), v,
            c.get("pass", 0), c.get("fail", 0), c.get("skip", 0), c.get("justified", 0),
            " %s" % t["lava"]["url"] if t.get("lava") else ""), file=out)
        d = t.get("diff")
        if d:
            print("  against %s: new fail %s; new pass %s; missing %s; added %s" % (
                d["baseline"], " ".join(d["new_fail"]) or "none", " ".join(d["new_pass"]) or "none",
                len(d["missing"]), len(d["added"])), file=out)
        for x in t.get("cases", []):
            if x["result"] != "pass" and not x.get("justified"):
                print("  %s %s/%s %s" % (x["result"], x["suite"], x["name"], x.get("url", "")), file=out)
    return ok


def wait(a, get=fetch_doc, sleep=time.sleep):
    start = time.time()
    while True:
        doc = get(a.site, a.run)
        if doc and doc["state"] in FINAL and all(t["state"] in FINAL for t in doc["targets"]):
            return 0 if report(doc) else 1
        if time.time() - start > a.timeout:
            if doc:
                report(doc)
            print("timed out waiting for %s" % a.run, file=sys.stderr)
            return 2
        sleep(a.interval)


def main(argv=None):
    p = argparse.ArgumentParser(prog="ossci")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    for c in COMPONENTS:
        r.add_argument("--" + c, default="")
    r.add_argument("--boards", default="")
    r.add_argument("--title", default="")
    r.add_argument("--requester", default="")
    r.add_argument("--repo", default=REPO)
    r.add_argument("--ref", default="main")
    w = sub.add_parser("wait")
    w.add_argument("run")
    w.add_argument("--site", default=RAW)
    w.add_argument("--interval", type=int, default=300)
    w.add_argument("--timeout", type=int, default=12 * 3600)
    a = p.parse_args(argv)
    if a.cmd == "run":
        try:
            print(dispatch(a))
        except refs.BadInput as e:
            raise SystemExit("bad input: %s" % e)
        return 0
    return wait(a)


if __name__ == "__main__":
    sys.exit(main())
