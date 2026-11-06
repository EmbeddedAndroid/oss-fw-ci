"""The flash package of one board (boards.yaml `package`), qcomflash:

python3 -m ossci.package build <board> <fip.elf> <efi.bin> <rootfs.img> <out.tar.gz>
python3 -m ossci.package insert-bl2 <package.tar.gz> <board>

build: the public downstream boot binaries and CDT the board pins, the
GPT, rawprogram and patch files qcom-ptool makes from its layout, then
uefi_a/uefi_b <- fip.elf (BL31 + OP-TEE + U-Boot of the run), efi <- the
ESP with the UKI (Linux of the run, the pinned rootfs), rootfs <- the
ext4 image with the test-definitions; tz is deferred: the BL2 is not
redistributable, so the build jobs (which hold no secret) leave it out
and the submit job adds it (insert-bl2), from $OSSCI_WORK/pins when
staged there or else from the private store (a release asset of
EmbeddedAndroid/oss-fw-ci-private, read with $OSSCI_PRIVATE_TOKEN),
checked against the pinned sha256 either way. SOURCES.json lists every
file with its sha256."""
import glob
import hashlib
import http.client
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile

from . import config
from .fetch import WORK, fetch, sha256

PTOOL = os.environ.get("QCOM_PTOOL_DIR", "/opt/qcom-ptool")
PRIVATE_STORE = "EmbeddedAndroid/oss-fw-ci-private"
GITHUB_API = "https://api.github.com"
REQUIRED = ("xbl.elf", "xbl_config.elf", "cdt.bin", "uefi.elf", "efi.bin", "rootfs.img")


def unzip_top(zpath, dest):
    with zipfile.ZipFile(zpath) as z:
        for info in z.infolist():
            parts = info.filename.split("/")
            if info.is_dir() or len(parts) != 2:
                continue
            with z.open(info) as src, open(os.path.join(dest, parts[1]), "wb") as dst:
                shutil.copyfileobj(src, dst)


def partitions(layout, dest):
    work = tempfile.mkdtemp(dir=dest)
    subprocess.run(["qcom-ptool", "gen_partition", "-i", os.path.join(PTOOL, layout["conf"]),
                    "-o", os.path.join(work, "partitions.xml")], check=True)
    subprocess.run(["qcom-ptool", "ptool", "-x", "partitions.xml"], cwd=work, check=True,
                   stdout=subprocess.DEVNULL)
    for pat in ("rawprogram*.xml", "patch*.xml", "gpt_*.bin", "zeros_*.bin"):
        for f in glob.glob(os.path.join(work, pat)):
            shutil.move(f, os.path.join(dest, os.path.basename(f)))
    shutil.rmtree(work)


def skip_missing(d, keep=()):
    """Blank the filename of program entries whose file the package does
    not carry, so qdl leaves those partitions alone."""
    skipped = []
    for rp in sorted(glob.glob(os.path.join(d, "rawprogram*.xml"))):
        text = open(rp).read()

        def blank(m):
            name = m.group(2)
            if name and name not in keep and not os.path.exists(os.path.join(d, name)):
                label = re.search(r'label="([^"]*)"', m.group(0))
                skipped.append("%s (%s)" % (label.group(1) if label else "?", name))
                return m.group(0).replace('filename="%s"' % name, 'filename=""')
            return m.group(0)
        open(rp, "w").write(re.sub(r'<program ([^>]*?)filename="([^"]*)"[^>]*/>', blank, text))
    return skipped


def written_images(d):
    out = set()
    for rp in glob.glob(os.path.join(d, "rawprogram*.xml")):
        out.update(re.findall(r'<program [^>]*?filename="([^"]+)"', open(rp).read()))
    return out


def top_dir(board_name):
    return "ossci-%s" % board_name


def build(board_name, fip, efi, rootfs_img, out, board=None):
    b = board or config.board(board_name)
    p = b["package"]
    if p["format"] != "qcomflash":
        raise SystemExit("%s: package format %s is not supported" % (board_name, p["format"]))
    dirname = top_dir(board_name)
    stage = tempfile.mkdtemp(dir=WORK)
    d = os.path.join(stage, dirname)
    os.makedirs(d)
    try:
        for bb in p["bootbinaries"]:
            unzip_top(fetch(bb["url"], bb["sha256"]), d)
        for pat in ("partition_*.xml", "rawprogram*.xml", "patch*.xml", "gpt_*.bin"):
            for f in glob.glob(os.path.join(d, pat)):
                os.remove(f)
        if p.get("cdt"):
            with zipfile.ZipFile(fetch(p["cdt"]["url"], p["cdt"]["sha256"])) as z, \
                    open(os.path.join(d, "cdt.bin"), "wb") as f:
                f.write(z.read(p["cdt"]["file"]))
        partitions(p["partitions"], d)
        # Never the downstream QTEE in place of the pinned BL2.
        if os.path.exists(os.path.join(d, "tz.mbn")):
            os.remove(os.path.join(d, "tz.mbn"))
        deferred = ["tz.mbn"]
        shutil.copy(fip, os.path.join(d, "uefi.elf"))
        shutil.copy(efi, os.path.join(d, "efi.bin"))
        shutil.copy(rootfs_img, os.path.join(d, "rootfs.img"))
        for f in REQUIRED:
            if not os.path.exists(os.path.join(d, f)):
                raise SystemExit("package lacks %s" % f)
        skipped = skip_missing(d, keep=deferred)
        written = written_images(d)
        for f in ("uefi.elf", "efi.bin", "rootfs.img", "tz.mbn"):
            if f not in written:
                raise SystemExit("the %s layout writes no %s" % (board_name, f))
        files = sorted(os.listdir(d))
        json.dump({"board": board_name, "downstream": p["release"], "bl2": b["bl2"]["fingerprint"],
                   "deferred": deferred, "not_written": skipped,
                   "files": {f: sha256(os.path.join(d, f)) for f in files}},
                  open(os.path.join(d, "SOURCES.json"), "w"), indent=1)
        with tarfile.open(out, "w:gz", compresslevel=6) as t:
            t.add(d, arcname=dirname)
    finally:
        shutil.rmtree(stage)
    return dirname, skipped


def rewrite(package, add):
    """Add files (name -> bytes) to a package, keeping SOURCES.json true."""
    tmp = package + ".tmp"
    top = None
    with tarfile.open(package) as src, tarfile.open(tmp, "w:gz", compresslevel=6) as dst:
        for m in src.getmembers():
            name = m.name.split("/", 1)[-1]
            if name in add:
                continue
            f = src.extractfile(m) if m.isfile() else None
            if name == "SOURCES.json":
                meta = json.load(f)
                meta["deferred"] = [x for x in meta.get("deferred", []) if x not in add]
                for x, data in add.items():
                    meta["files"][x] = hashlib.sha256(data).hexdigest()
                blob = json.dumps(meta, indent=1).encode()
                m.size = len(blob)
                f = io.BytesIO(blob)
                top = m.name.split("/")[0]
            dst.addfile(m, f)
        if top is None:
            raise SystemExit("%s has no SOURCES.json" % package)
        for x, data in sorted(add.items()):
            info = tarfile.TarInfo(top + "/" + x)
            info.size, info.mode = len(data), 0o644
            dst.addfile(info, io.BytesIO(data))
    os.replace(tmp, package)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def github_get(url, token, accept):
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token, "Accept": accept,
                                               "X-GitHub-Api-Version": "2022-11-28"})
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=300) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        if e.code not in (301, 302, 303, 307, 308) or not e.headers.get("Location"):
            raise
        location = urllib.parse.urljoin(url, e.headers["Location"])
    if urllib.parse.urlsplit(location).scheme != "https":
        raise ValueError("redirect leaves https")
    # The asset host gets no token.
    with urllib.request.urlopen(urllib.request.Request(location), timeout=300) as r:
        return r.read()


def private_file(pin, env=os.environ, store=PRIVATE_STORE, get=github_get):
    """A private pin's bytes: staged in $OSSCI_WORK/pins, or the asset
    <file> of release <release> of the private store; checked against the
    pinned sha256. Errors never quote a URL or the token."""
    if os.path.exists(os.path.join(WORK, "pins", pin["file"])):
        return open(fetch(None, pin["sha256"], pin["file"]), "rb").read()
    token = env.get("OSSCI_PRIVATE_TOKEN", "").strip()
    if not token:
        raise SystemExit("%s is not staged and OSSCI_PRIVATE_TOKEN is not set" % pin["file"])
    try:
        release = json.loads(get("%s/repos/%s/releases/tags/%s" % (GITHUB_API, store, pin["release"]),
                                 token, "application/vnd.github+json"))
        url = [a["url"] for a in release.get("assets", []) if a.get("name") == pin["file"]]
        if not url:
            raise SystemExit("%s: not in release %s of the private store" % (pin["file"], pin["release"]))
        if not url[0].startswith(GITHUB_API + "/"):
            raise ValueError("asset URL outside the API")
        data = get(url[0], token, "application/octet-stream")
    except (OSError, ValueError, KeyError, http.client.HTTPException) as e:
        why = "HTTP Error %d" % e.code if isinstance(e, urllib.error.HTTPError) else type(e).__name__
        raise SystemExit("%s: cannot be read from the private store (%s)" % (pin["file"], why))
    if hashlib.sha256(data).hexdigest() != pin["sha256"]:
        raise SystemExit("%s does not match the pinned sha256" % pin["file"])
    return data


def insert_bl2(package, board_name, env=os.environ, board=None, get=github_get):
    b = board or config.board(board_name)
    rewrite(package, {"tz.mbn": private_file(b["bl2"], env, get=get)})


def sources(package):
    with tarfile.open(package) as t:
        for m in t.getmembers():
            if m.name.endswith("/SOURCES.json"):
                return json.load(t.extractfile(m))
    raise SystemExit("%s has no SOURCES.json" % package)


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) == 6 and a[0] == "build":
        name, skipped = build(*a[1:6])
        print(json.dumps({"path": name, "not_written": skipped}))
    elif len(a) == 3 and a[0] == "insert-bl2":
        insert_bl2(a[1], a[2])
    else:
        raise SystemExit(__doc__)
