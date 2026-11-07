"""The LAVA job of one board: the one template, the pinned suite.

Flash the package with qdl, power on, the fingerprint gate on the cold
boot, log in, every definition of the suite (cold phase), warm reboot,
the gate again, the warm-phase definitions as <name>-after-reboot, the
last phase, poweroff, then the lab's own image back (stock restore at the
end of every job). Every action before the restore has its timeout
skipped, so a hang ends that action and the restore still runs.
The definitions and their order come from ossci.suite only: a board
gives parameter values (facts), and an unknown parameter is refused, so
a board cannot add, drop or rename a test."""
import copy

from fwci import lava_jobs

from . import config, gate, suite

TD_ROOT = "/lava-ovl/td"
MOUNT_OVL = ("mkdir -p /lava-ovl; for p in /sys/class/block/*; do grep -qx PARTNAME=rootfs $p/uevent "
             "&& mount -t ext4 /dev/${p##*/} /lava-ovl; done; ln -sf /lava-ovl/lava-* /")
PROMPT = "\\n# "


def skip(action):
    for v in action.values():
        v.setdefault("timeout", {})["skip"] = True
    return action


def fingerprints(fp, rootfs_fp):
    return {"FINGERPRINT": fp, "LINUX_FINGERPRINT": fp, "ROOTFS_FINGERPRINT": rootfs_fp,
            "FIRMWARE_FINGERPRINT": fp}


def params_for(name, defaults, facts, extra, suite_params=None):
    """The definition's defaults, then the suite's values (every board),
    then the board's facts, then the run's (fingerprints, resources)."""
    p = dict(defaults)
    for src, values in (("suite.yaml params", (suite_params or {}).get(name)), ("facts", facts.get(name))):
        for k, v in (values or {}).items():
            if k not in defaults:
                raise ValueError("%s of %s: %s is not a parameter of the definition" % (src, name, k))
            p[k] = "" if v is None else str(v)
    for k, v in extra.items():
        if k in defaults:
            p[k] = v
    return p


def check_facts(facts, defs, suite_params=None):
    names = {n for _, n, _, _, _ in defs}
    for what, given in (("facts", facts), ("suite.yaml params", suite_params or {})):
        unknown = sorted(set(given) - names)
        if unknown:
            raise ValueError("%s for %s, which the suite does not run" % (what, ", ".join(unknown)))


def test_action(defs, minutes):
    return skip({"test": {"definitions": defs, "timeout": {"minutes": minutes}}})


def inline(name, steps, params):
    return {"from": "inline", "name": name, "path": "inline/%s.yaml" % name,
            "repository": {"metadata": {"format": "Lava-Test Test Definition 1.0", "name": name},
                           "run": {"steps": suite.rebase_steps(steps, TD_ROOT)}},
            "parameters": params}


def resource_needed(res, params):
    for k, sub in (res.get("when_param") or {}).items():
        if sub not in params.get(k, ""):
            return False
    return True


def login(board):
    a = lava_jobs.login(board["lava"]["login_prompt"], PROMPT, commands=("dmesg -n 1", MOUNT_OVL))
    return skip(a)


def restore(board):
    r = board["lava"]["restore"]
    lv = board["lava"]
    a = r["anchor"]
    pat = "(?P<test_case_id>%s)\\s*:\\s*(?P<result>%s)" % (a["pattern"], a["value"].replace(".", "\\."))
    return [
        {"deploy": {"to": "qdl", "qcomflash": {"url": r["url"], "headers": {r["header"]: r["token_name"]}},
                    "timeout": {"minutes": 30}}},
        lava_jobs.boot_qdl(r["path"], lv["storage"], lv["luns"], lv["firehose"], minutes=20),
        {"boot": {"method": "minimal", "timeout": {"minutes": 3}}},
        lava_jobs.monitor("stock-restore", a["start"], a["end"], pat, {a["value"]: "pass"}, [a["name"]],
                          minutes=10),
    ]


def generate(board_name, board, fp, rootfs_fp, td, url, token_name, package_dir, run_meta,
             suite_cfg=None, device=None):
    """The job definition (a dict). td: the test-definitions tree at the
    pinned commit; url/token_name: the uploaded package and its LAVA remote
    artifact token name; package_dir: the top directory in the package."""
    suite_cfg = suite_cfg or config.suite()
    defs = suite.definitions(td, suite_cfg)
    check_facts(board["facts"], defs, suite_cfg.get("params"))
    resources = suite_cfg.get("resources", {})
    fps = fingerprints(fp, rootfs_fp)
    lv = board["lava"]
    overlays = {"lava": True}
    phases = {"cold": [], "warm": [], "last": []}
    for ph, name, _, steps, defaults in defs:
        extra = dict(fps)
        sp = suite_cfg.get("params") or {}
        params = params_for(name, defaults, board["facts"], {}, sp)
        for rname, res in resources.items():
            if res.get("for") == name and resource_needed(res, params):
                overlays[rname] = {"url": res["url"], "format": "file", "path": res["path"]}
                extra.update(res.get("params", {}))
        params = params_for(name, defaults, board["facts"], extra, sp)
        shown = name if ph != "warm" else name + "-after-reboot"
        phases[ph].append(inline(shown, steps, params))
    actions = [
        skip({"deploy": {"to": "qdl", "rootfs_image": "%s/rootfs.img" % package_dir,
                         "qcomflash": {"url": url, "headers": {"Authorization": token_name},
                                       "format": "ext4", "overlays": overlays},
                         "timeout": {"minutes": 30}}}),
        skip(lava_jobs.boot_qdl(package_dir, lv["storage"], lv["luns"], lv["firehose"])),
        skip(lava_jobs.power_on()),
    ]
    cold_gate, warm_gate = gate.monitors(board, fp)
    actions += [cold_gate, login(board), test_action(phases["cold"], 150)]
    actions.append(skip(lava_jobs.interactive("warm-reboot", ["reboot: Restarting system"],
                                              [{"name": "reboot", "command": "reboot"}], minutes=3)))
    actions += [warm_gate, login(board), test_action(phases["warm"], 10)]
    if phases["last"]:
        actions.append(test_action(phases["last"], 20))
    actions.append(skip(lava_jobs.interactive("poweroff", ["reboot: Power down"],
                                              [{"name": "poweroff", "command": "poweroff"}], minutes=3)))
    actions += restore(board)
    meta = dict(run_meta, fingerprint=fp, rootfs_fingerprint=rootfs_fp, board=board_name)
    job = lava_jobs.job(lv["device_type"], "oss-fw-ci %s %s" % (board_name, fp), actions,
                        {k: str(v) for k, v in meta.items()}, job_minutes=300)
    job["timeouts"]["connection"] = {"minutes": 160}
    if lv.get("tags"):
        job["tags"] = list(lv["tags"])
    if device:
        job["device"] = device
    return job


def cases_expected(board, td, suite_cfg=None):
    """Suite names the job reports (definition names as LAVA shows them)."""
    return [n if ph != "warm" else n + "-after-reboot" for ph, n, _, _, _ in suite.definitions(td, suite_cfg)]


def redact(job):
    """A copy safe to print or publish: token names stay (they name a lab
    secret, they are not one), nothing else is secret in a job."""
    return copy.deepcopy(job)


def restore_job(board_name, board, device, run_meta):
    """A job that only puts the lab's own image back on device: the
    backstop for a job that ended before its restore (a login that never
    came is a job error, which no timeout skip covers)."""
    lv = board["lava"]
    meta = dict(run_meta, board=board_name, purpose="stock restore backstop")
    job = lava_jobs.job(lv["device_type"], "oss-fw-ci %s stock restore backstop" % board_name, restore(board),
                        {k: str(v) for k, v in meta.items()}, job_minutes=60)
    job["device"] = device
    if lv.get("tags"):
        job["tags"] = list(lv["tags"])
    return job


def restored(cases):
    """Whether the job's stock restore passed."""
    got = [c["result"] for c in cases if c["suite"] == "stock-restore"]
    return bool(got) and all(r == "pass" for r in got)
