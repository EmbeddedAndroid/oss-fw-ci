"""Why a run cannot be built from public sources, or nothing.

python3 -m ossci.preflight <resolved.json>   prints the reason (empty
when every input and the rootfs pin can be fetched). The CI holds no
private source: a pin marked pending (config/baseline.yaml) or a rootfs
pin with no public source (config/rootfs.yaml) skips the run with the
reason; a lease driver that holds those trees runs it (docs/setup.md)."""
import json
import sys

from . import config


def reasons(resolved, rootfs=None):
    rootfs = rootfs or config.rootfs()
    out = []
    for c in ("tfa", "optee", "uboot", "linux"):
        if resolved[c].get("pending"):
            out.append("%s baseline %s not public (%s): give a %s input" % (
                c, resolved[c]["commit"][:12], resolved[c]["pending"], c))
    if not (rootfs.get("source") or {}).get("repo") and not rootfs.get("upstream"):
        out.append("rootfs pin qcom-buildroot %s not public yet (%s)" % (
            rootfs["commit"][:12], (rootfs.get("source") or {}).get("note", "")))
    return out


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    print("; ".join(reasons(json.load(open(sys.argv[1])))))
