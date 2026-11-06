import copy
import os
import subprocess
import sys

import pytest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from ossci import config  # noqa: E402

PLAN_TESTS = ["boot-fingerprint", "boot-handoff", "inference", "kernel-health", "suspend-idle",
              "maxcpus", "memtest", "systemready-acs"]


def write_def(td, name, params, steps=None):
    d = os.path.join(td, "automated", "linux", name)
    os.makedirs(d, exist_ok=True)
    doc = {"metadata": {"name": name, "format": "Lava-Test Test Definition 1.0"},
           "params": params,
           "run": {"steps": steps or ["cd ./automated/linux/%s/" % name, "./%s.sh" % name,
                                      "../../utils/send-to-lava.sh ./output/result.txt"]}}
    yaml.safe_dump(doc, open(os.path.join(d, name + ".yaml"), "w"))


@pytest.fixture
def td(tmp_path):
    """A test-definitions tree with a plan like open-boot-stack."""
    root = tmp_path / "td"
    plan = {"metadata": {"name": "open-boot-stack"},
            "tests": {"automated": [{"path": "automated/linux/%s/%s.yaml" % (n, n),
                                     "repository": "https://github.com/Linaro/test-definitions.git"}
                                    for n in PLAN_TESTS]}}
    os.makedirs(root / "plans" / "open-boot-stack")
    yaml.safe_dump(plan, open(root / "plans" / "open-boot-stack" / "open-boot-stack.yaml", "w"))
    write_def(str(root), "boot-fingerprint", {"FINGERPRINT": "", "LINUX_FINGERPRINT": "",
                                              "ROOTFS_FINGERPRINT": "", "FIRMWARE_FINGERPRINT": "",
                                              "ROOTFS_FILES": "/etc/issue"})
    write_def(str(root), "boot-handoff", {"BOOT_CPU": "", "CPUS": "", "KVM": "", "PSCI_MODE": "",
                                          "EXCEPTION_LEVEL": "EL2", "TEE": "optee"})
    write_def(str(root), "inference", {"PUS": "", "QAIRT_ZIP": "", "QAIRT_SHA256": "", "QAIRT_ROOT": ""})
    write_def(str(root), "kernel-health", {"MAX": "0", "IGNORE": ""})
    write_def(str(root), "suspend-idle", {"PSCI_MODE": "", "CYCLES": "3"})
    for n in ("maxcpus", "memtest", "systemready-acs"):
        write_def(str(root), n, {})
    return str(root)


@pytest.fixture
def suite_cfg():
    s = config.suite()
    s = copy.deepcopy(s)
    s["phases"] = {"warm": ["boot-fingerprint", "boot-handoff", "kernel-health"], "last": ["suspend-idle"]}
    return s


@pytest.fixture
def board():
    b = copy.deepcopy(config.board("rb3gen2"))
    b["facts"] = {"boot-handoff": {"BOOT_CPU": "0x0", "CPUS": "8", "KVM": "vhe", "PSCI_MODE": "osi"},
                  "inference": {"PUS": "cpu:qnn cpu:tflite"},
                  "suspend-idle": {"PSCI_MODE": "osi"}}
    return b


def git(path, *args):
    return subprocess.run(["git", "-C", str(path), "-c", "user.name=t", "-c", "user.email=t@t"] + list(args),
                          check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    """A small git tree with one commit; returns (path, commit)."""
    r = tmp_path / "qb"
    os.makedirs(r)
    git(r, "init", "-q")
    (r / "kodiak.mk").write_text("all:\n")
    (r / ".gitignore").write_text("out/\n")
    git(r, "add", "-A")
    git(r, "commit", "-qm", "base")
    return r, git(r, "rev-parse", "HEAD")
