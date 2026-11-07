# oss-fw-ci: one way to validate the open firmware stack

Status: design, 2026-11-06. Repository: EmbeddedAndroid/oss-fw-ci (public).

## Goal

Any change to the open stack (TF-A, OP-TEE, U-Boot, Linux) is validated
the same way, by people and by agents:

1. one trigger: a `workflow_dispatch` run (or the `ossci` CLI around it);
2. one test set on every platform: the open-boot-stack plan of
   test-definitions minus ACS, pinned to one commit;
3. one root filesystem: qcom-buildroot's test image (`TEST=y`) from an
   upstream commit, unchanged. A change to it goes upstream first, then the
   pin moves.

Given a branch (or change, PR, series) for each component, a run builds
them with fingerprints, builds the pinned test rootfs, submits the same
suite to LAVA for each board, monitors it and publishes the results on
GitHub Pages.

## Inputs

`run.yml` (`workflow_dispatch`):

| input | form | default |
|---|---|---|
| `tfa` | `owner/repo@ref`, or `gerrit:<change>[/<ps>]` | baseline pin |
| `optee` | `owner/repo@ref`, or `pr:<number>` (OP-TEE/optee_os) | baseline pin |
| `uboot` | `owner/repo@ref`, or `lore:<message-id>` (applied on the pinned base) | baseline pin |
| `linux` | `owner/repo@ref`, or `lore:<message-id>` | baseline pin |
| `boards` | space separated | all boards |
| `title` | free text for the dashboard | |
| `requester` | agent or person | actor |

An empty component input takes the baseline pin, so a change to one
component is an A/B against the baseline with everything else equal.

## Pinned configuration (changes only by reviewed PR)

- `config/suite.yaml`: test-definitions repository and commit, the plan
  file, and the excluded definitions (`systemready-acs`). Every board runs
  this list. The job generator has no per-board test list.
- `config/rootfs.yaml`: qcom-buildroot upstream repository and commit, the
  board makefile per architecture and `TEST=y`. The build job checks the
  checked-out tree equals that upstream commit and has no patches; it
  refuses anything else. The rootfs is built once per (qcom-buildroot SHA,
  test-definitions SHA, architecture) and cached, so every board runs
  byte-identical userspace.
- `config/boards.yaml`: per board: LAVA device type, TF-A `PLAT`, OP-TEE
  `PLATFORM`/flavor, U-Boot defconfig and fragments, kernel config
  fragment and DTB, flash package format, signing, and the BL2 pin.
- `config/baseline.yaml`: the baseline pin of each component (the
  integration branches), moved by the nightly when it is green.
- `config/justifications.yaml`: the only way a case may not pass on a
  board: board, case, reason, evidence link, reviewer. A non-pass without
  an entry is a failure. This is the port-complete bar.
- `config/flakes.yaml`, `config/known-errors.yaml`: as in u-boot-ci.

## Privately hosted BL2s and blobs (Nord, Shikra, Wildcat boards)

As u-boot-ci (docs/setup.md and docs/private-firmware.md there):

- A board whose BL2 cannot be public pins it by
  `{secret, file, sha256, fingerprint}` in `boards.yaml`: the image is
  the value (gzip -9, base64) of the `PIN_BL2_<BOARD>` secret of the
  `lava-hw` environment, the same secret u-boot-ci holds for that board.
- Private TF-A and OP-TEE images of boards whose sources CI may not see
  (Wildcat-style) live as release assets of a private store repository
  (EmbeddedAndroid/oss-fw-ci-private), pinned by
  `{private, release, file, sha256, fingerprint}` and read with a
  read-only token that is a secret of `lava-hw` (none yet).
- Only the `submit` job reads them, checks the sha256 and inserts them
  into the package; it builds nothing from the trees under test. The build
  jobs hold no secret.
- The fingerprint gate expects the pinned image's own fingerprint on that
  stage and the run's fingerprint on the stages built from the inputs.
- If the pinned image cannot be had, the board is `skipped` with a public
  reason (never a URL or the token).
- Signing that needs an internal service (production-fused Nord: CASS) is
  done once when the image is pinned, not per run. Test-key boards sign in
  the submit job with the pinned signer, as u-boot-ci does.

## Pipeline

```
resolve -> build (per component x board) -> rootfs (cached) -> package
        -> submit (lava-hw env) -> monitor -> collect -> publish
```

1. **resolve** (arm64 2c VM): pin every input to a SHA (Gerrit patch set,
   PR head, lore series applied on the base), allocate the run
   fingerprint `ossci-<run>-<attempt>-<board>`, write `run.json`.
2. **build** (xeon VMs for kernel and firmware, the bigger runner labels):
   each component built in the repository's container with the
   fingerprint in its version string; warnings collected.
3. **rootfs** (xeon, cached): qcom-buildroot at the pin, `TEST=y`, the
   per-architecture board makefile; cache key as above.
4. **package** (arm64 4c): the board flash image from the built
   components and the rootfs, by `boards.yaml` format.
5. **submit** (arm64 2c, `lava-hw` environment): private images inserted
   and signed where needed, artifacts uploaded to LAVA, the job generated
   from the one template with the pinned suite, low priority, stock
   restore at the end of every job.
6. **monitor** (arm64 2c): poll the jobs; state per cell (queued with queue
   position, flashing, testing, done, cancelled, error) published as it
   changes.
7. **collect** (arm64 2c): fingerprint gate on every boot (a cell whose
   gate failed is not counted and raises no regression), per-case results,
   comparison with the board's latest baseline run, flake and known-error
   handling, justification lookup.
8. **publish** (arm64 2c): `results/<run>.json`, `index.json` and the pages
   to `gh-pages`.

Runners: the GitHub Actions CIL bridge (self-hosted, `cil` label) as
u-boot-ci uses it; arm64 VMs (`[self-hosted, cil, arm64, 2c-4g-20g]`) for
every low-load job (resolve, submit, monitor, collect, publish), xeon VMs
only for the builds. No GitHub-hosted runners, so no billed minutes.

## Results and dashboard

Per run page: the input SHAs and links, the fingerprints, and per board
the matrix of suite cases (pass, fail, skip, justified, flaky), the delta
against the baseline, and for every result a LAVA link anchored to the
line that proves it. The front page: the latest nightly per board and the
recent ad-hoc runs. `results/<run>.json` follows a published schema
(reused from u-boot-ci's results schema where it fits) and is what agents
read.

## Agent interface

```
ossci run --optee EmbeddedAndroid/optee_os@pkvm-p2/p22-fw-smmu --boards eliza-evk --title "P2.2c"
ossci wait <run>        # exits 0 when every cell passes or is justified;
                        # prints the per-case delta against the baseline
```

`ossci` wraps `gh workflow run` and reads `results/<run>.json`. Agent
briefs state that validation is an `ossci` run; hand-built LAVA jobs and
rootfs overlays are not validation.

## Reuse from u-boot-ci

`fwci/` (lava_jobs, lava_rest, lava_mcp, collect, flakes, links, schema,
site, pinwatch, baseline) becomes a shared Python package used by both
repositories. u-boot-ci keeps its U-Boot-specific `ubci/`; oss-fw-ci adds
the multi-component build and the suite collection.

## Phases

1. This design, the results schema, the repository skeleton.
2. RB3 Gen 2 end to end: all four components from inputs, pinned rootfs,
   full suite, published results; equal case for case to the latest
   hand-run RB3 Gen 2 suite.
3. Every LAVA board: VENTUNO Q, UNO Q, QCS615 Ride, IQ-9075 EVK, Eliza EVK,
   Hamoa and Purwa, SM8750 MTP (Pakala), Mahua, Lanai and Kailua (brgl lab
   via cdba: an adapter, or LAVA when they move), Shikra and Nord with
   private BL2 pins.
4. The `ossci` CLI and the agent rule in every brief.
5. Nightly baseline runs of the integration branches; pin-watch for the
   suite and rootfs pins.

## Open

- The rootfs pin waits on the qcom-buildroot reconcile work (test-config
  PR: QEMU kvm-unit-tests, tee-shm-reclaim, suspend-idle); until it lands
  the pin is the reconcile branch, marked as such on the dashboard.
- Boards in the brgl lab (Lanai, Kailua) are cdba, not LAVA: decide
  whether phase 3 covers them through an adapter.
- LAVA board time per run: a cap per requester, or only the boards a
  change can affect.
