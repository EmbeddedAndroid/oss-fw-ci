import copy
import re

import pytest
import yaml

from ossci import config, jobs, suite


def gen(board, td, suite_cfg, name="rb3gen2", fp="ossci-1-1-rb3gen2"):
    return jobs.generate(name, board, fp, "ossci-rootfs-x", td, "https://lava/a/p.tar.gz", "tok-name",
                         "ossci-%s" % name, {"run": "1-1"}, suite_cfg=suite_cfg)


def defs_of(job):
    out = []
    for a in job["actions"]:
        for d in a.get("test", {}).get("definitions", []):
            out.append(d["name"])
    return out


def test_suite_excludes_and_phases(td, suite_cfg):
    d = suite.definitions(td, suite_cfg)
    names = [(ph, n) for ph, n, _, _, _ in d]
    assert ("cold", "systemready-acs") not in names and ("cold", "maxcpus") not in names
    assert names == [("cold", "boot-fingerprint"), ("cold", "boot-handoff"), ("cold", "inference"),
                     ("cold", "kernel-health"), ("warm", "boot-fingerprint"), ("warm", "boot-handoff"),
                     ("warm", "kernel-health"), ("last", "suspend-idle")]


def test_same_suite_for_every_board(td, suite_cfg, board):
    other = copy.deepcopy(board)
    other["facts"] = {"boot-handoff": {"CPUS": "4"}}
    other["lava"]["device_type"] = "qrb2210-arduino-imola"
    a = gen(board, td, suite_cfg)
    b = gen(other, td, suite_cfg, name="uno-q", fp="ossci-1-1-uno-q")
    assert defs_of(a) == defs_of(b) == jobs.cases_expected(board, td, suite_cfg)
    assert defs_of(a)[-4:] == ["boot-fingerprint-after-reboot", "boot-handoff-after-reboot",
                               "kernel-health-after-reboot", "suspend-idle"]


@pytest.mark.parametrize("key", config.TEST_LIST_KEYS)
def test_board_with_a_test_list_refused(board, key):
    bad = dict(board, **{key: ["boot-handoff"]})
    with pytest.raises(ValueError, match="not a test list"):
        config.check_board("rb3gen2", bad)


def test_boards_yaml_has_no_test_list():
    for name, b in config.boards().items():
        config.check_board(name, b)


def test_facts_for_a_test_not_in_the_suite_refused(td, suite_cfg, board):
    board["facts"]["video-codec"] = {"DEVICE": "x"}
    with pytest.raises(ValueError, match="does not run"):
        gen(board, td, suite_cfg)


def test_unknown_parameter_refused(td, suite_cfg, board):
    board["facts"]["boot-handoff"]["TESTS"] = "all"
    with pytest.raises(ValueError, match="not a parameter"):
        gen(board, td, suite_cfg)


def test_parameters_defaults_facts_and_fingerprints(td, suite_cfg, board):
    j = gen(board, td, suite_cfg)
    params = {d["name"]: d["parameters"] for a in j["actions"] for d in a.get("test", {}).get("definitions", [])}
    assert params["boot-handoff"]["CPUS"] == "8" and params["boot-handoff"]["TEE"] == "optee"
    bf = params["boot-fingerprint"]
    assert bf["FINGERPRINT"] == bf["LINUX_FINGERPRINT"] == bf["FIRMWARE_FINGERPRINT"] == "ossci-1-1-rb3gen2"
    assert bf["ROOTFS_FINGERPRINT"] == "ossci-rootfs-x"
    assert params["inference"]["QAIRT_ZIP"].endswith(".zip")


def test_steps_run_from_the_rootfs_partition(td, suite_cfg, board):
    j = gen(board, td, suite_cfg)
    d = [d for a in j["actions"] for d in a.get("test", {}).get("definitions", [])][0]
    assert d["repository"]["run"]["steps"][0] == "cd /lava-ovl/td/automated/linux/boot-fingerprint/"


def test_qairt_only_when_a_qnn_unit_runs(td, suite_cfg, board):
    j = gen(board, td, suite_cfg)
    assert "qairt" in j["actions"][0]["deploy"]["qcomflash"]["overlays"]
    board["facts"]["inference"]["PUS"] = "cpu:tflite"
    j = gen(board, td, suite_cfg)
    assert "qairt" not in j["actions"][0]["deploy"]["qcomflash"]["overlays"]


def test_gates_restore_and_skipped_timeouts(td, suite_cfg, board):
    j = gen(board, td, suite_cfg)
    mons = [a["test"]["monitors"][0] for a in j["actions"] if "monitors" in a.get("test", {})]
    assert [m["name"] for m in mons] == ["firmware-fingerprint-cold", "firmware-fingerprint-warm", "stock-restore"]
    assert mons[0]["expected"] == ["bl2", "bl31", "op_tee_version", "u_boot"]
    assert re.escape("QCDFP-261102-526") in mons[0]["pattern"]
    assert re.escape("ossci-1-1-rb3gen2") in mons[0]["pattern"]
    # Everything before the restore deploy has its timeout skipped; the restore does not.
    restore = [i for i, a in enumerate(j["actions"]) if "deploy" in a][1]
    for a in j["actions"][:restore]:
        assert list(a.values())[0]["timeout"]["skip"] is True
    for a in j["actions"][restore:]:
        assert "skip" not in list(a.values())[0]["timeout"]
    assert j["priority"] == "low" and j["visibility"] == "public"
    # The connection timeout outlasts every action.
    longest = max(list(a.values())[0]["timeout"]["minutes"] for a in j["actions"])
    assert j["timeouts"]["connection"]["minutes"] > longest
    yaml.safe_load(jobs.lava_jobs.to_yaml(j))


def test_real_suite_config_is_consistent():
    s = config.suite()
    assert s["commit"] and len(s["commit"]) == 40
    assert "systemready-acs" in s["exclude"]
    assert set(s["phases"]) <= {"warm", "last"}


def test_suite_params_apply_to_every_board_and_facts_win(td, suite_cfg, board):
    suite_cfg["params"] = {"kernel-health": {"MAX": "3"}, "boot-handoff": {"CPUS": "4"}}
    j = gen(board, td, suite_cfg)
    params = {d["name"]: d["parameters"] for a in j["actions"] for d in a.get("test", {}).get("definitions", [])}
    assert params["kernel-health"]["MAX"] == "3" and params["kernel-health-after-reboot"]["MAX"] == "3"
    assert params["boot-handoff"]["CPUS"] == "8"


def test_unknown_suite_param_refused(td, suite_cfg, board):
    suite_cfg["params"] = {"kernel-health": {"NOPE": "1"}}
    with pytest.raises(ValueError, match="suite.yaml params"):
        gen(board, td, suite_cfg)


def test_suite_params_for_a_test_not_in_the_suite_refused(td, suite_cfg, board):
    suite_cfg["params"] = {"video-codec": {"DEVICE": "x"}}
    with pytest.raises(ValueError, match="suite.yaml params for video-codec"):
        gen(board, td, suite_cfg)
