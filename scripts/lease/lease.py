#!/usr/bin/env python3
"""lease.py new <requester> <cpu> <ram_mb> <disk_gb> [ttl_min] [pool] | wait <id> |
ssh-args <id> | extend <id> <min> | release <id>

The CIL lease of the lease driver (docs/setup.md). Prints only id, status
and expiry: the key goes to ~/.ssh/cil-oss-fw-ci/<id>.key (mode 600) and
is never printed; responses are parsed privately (they carry key material)."""
import json
import os
import sys
import time
import urllib.request

CIL = os.environ.get("CIL_URL", "http://127.0.0.1:8086")
KEYS = os.path.expanduser("~/.ssh/cil-oss-fw-ci")


def req(m, p, body=None):
    r = urllib.request.Request(CIL + p, method=m, data=json.dumps(body).encode() if body else None,
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=60) as f:
        t = f.read()
    return json.loads(t) if t else {}


def main(a):
    if a[0] == "new":
        pool = a[6] if len(a) > 6 else "xeon"
        image = "ubuntu-24.04"
        d = req("POST", "/api/v1/leases", dict(pool=pool, requester=a[1], image=image, cpu=int(a[2]),
                                              ram_mb=int(a[3]), disk_gb=int(a[4]),
                                              ttl_min=int(a[5]) if len(a) > 5 else 600))
        print("id", d["id"], "status", d.get("status"))
    elif a[0] == "wait":
        while True:
            d = req("GET", "/api/v1/leases/" + a[1])
            if d["status"] in ("ready", "failed", "released", "expired"):
                break
            time.sleep(15)
        print("id", a[1], "status", d["status"], "expires", d.get("expires_at"), "err", d.get("last_error"))
        if d["status"] == "ready":
            c = d["connection"]
            os.makedirs(KEYS, exist_ok=True)
            with open(os.open("%s/%s.key" % (KEYS, a[1]), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
                f.write(c["private_key_pem"])
            with open("%s/%s.conn" % (KEYS, a[1]), "w") as f:
                f.write("%s %s %s\n" % (c["user"], c["host"], c["port"]))
    elif a[0] == "ssh-args":
        u, h, p = open("%s/%s.conn" % (KEYS, a[1])).read().split()
        print("-i %s/%s.key -p %s -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "
              "-o LogLevel=ERROR -o ServerAliveInterval=30 %s@%s" % (KEYS, a[1], p, u, h))
    elif a[0] == "extend":
        d = req("POST", "/api/v1/leases/%s/extend" % a[1], dict(add_min=int(a[2])))
        print("id", a[1], "expires", d.get("expires_at"))
    elif a[0] == "release":
        req("DELETE", "/api/v1/leases/" + a[1])
        for ext in ("key", "conn"):
            try:
                os.remove("%s/%s.%s" % (KEYS, a[1], ext))
            except FileNotFoundError:
                pass
        print("id", a[1], "released")
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:] or ["help"])
