# Architecture

## Pipeline (`.github/workflows/run.yml`)

| job | runner | runs code under test | secrets | does |
|---|---|---|---|---|
| resolve | CIL arm64 `2c-4g-20g` | no | none (writes gh-pages) | checks every input (`ossci.refs.parse`), pins it to a commit (Gerrit patch set, PR head, branch or tag; a lore series is recorded with its base), allocates the fingerprint `ossci-<run>-<attempt>-<board>` per board, writes and publishes the run document; `ossci.preflight` skips the run with the reason when a pin cannot be fetched publicly |
| rootfs | CIL xeon `32c-32g-200g` | no (pinned qcom-buildroot only) | none | the pinned test rootfs, from the Actions cache when its key (`ossci.rootfs key`) was built before |
| build | CIL xeon `32c-32g-200g`, one per board | yes | none, read-only token not kept | `scripts/build-board.sh`: OP-TEE, U-Boot, Linux, TF-A BL31 and the FIP (each its own step, log and warnings count), the ESP, the rootfs partition, the qcomflash package without the BL2 |
| submit | CIL arm64 `2c-4g-20g`, environment `lava-hw` | no | `LAVA_TOKEN`, `PIN_BL2_<BOARD>` | records the builds and the rootfs, adds the pinned BL2 from its secret (sha256 checked; missing or mismatching: the board is `skipped`, "BL2 pin not available"), uploads the package to the LAVA artifact store, generates the job (`ossci.jobs`), picks a healthy idle device (never `*-production-*`), submits |
| track | CIL arm64 `2c-4g-20g`, environment `lava-hw` | no | `LAVA_TOKEN` | every 5 minutes: job state and queue position (`ossci.run monitor`), results of finished jobs (`ossci.run collect`), publish; until every board is final |
| finalize | CIL arm64 `2c-4g-20g`, after a cancel or failure only | no | none (writes gh-pages) | closes the run document (`cancelled` or `error`) |

The build jobs hold no secret and declare no environment: the inputs
are untrusted code. The submit job only moves opaque packages and adds a
pinned image to them; it executes nothing from the inputs. Console text
that comes back is data: the dashboard sets it as text.

## The job (`ossci/jobs.py`)

One template for every board, at low priority, public:

1. qdl flash of the package (every partition the layout writes; tz with
   the pinned BL2, uefi with the run's fip.elf, efi with the UKI, rootfs
   with the test-definitions at `/td`), LAVA's overlay in the rootfs
   partition, the QAIRT SDK zip when the board's inference units need it.
2. Power on; **cold fingerprint gate** from XBL's `SBL1, End` to `Booting
   Linux`: BL2 must print its pinned fingerprint, BL31, OP-TEE and
   U-Boot the run's.
3. Login on the Buildroot prompt; the rootfs partition is mounted at
   `/lava-ovl`.
4. The suite, cold phase: every definition of the plan at the pinned
   commit that is not excluded, in plan order, with each definition's
   own steps and default parameters, the board's facts and the
   fingerprints (`FINGERPRINT`, `LINUX_FINGERPRINT`,
   `FIRMWARE_FINGERPRINT` = the run's, `ROOTFS_FINGERPRINT` = the
   rootfs's).
5. `reboot`; **warm fingerprint gate**; login; the warm phase
   (boot-fingerprint, boot-handoff, kernel-health `-after-reboot`); the
   last phase (suspend-idle).
6. `poweroff`; the lab's own image is flashed back and its UEFI version
   checked (`stock-restore`).

Every action before the restore has its timeout skipped (a hang ends
that action, the job goes on), so the restore runs on every job. A board
supplies parameter values only; the generator refuses a board entry with
a test list, facts for a definition the suite does not run and a
parameter the definition does not have.

## Collect (`ossci/collect.py`)

fwci's collector turns the job into cases with links to their log line,
the boot verdict and boot times. Then: the fingerprint gate passes only
when both gates passed every stage (a cell whose gate failed is not
counted and raises no regression); known flakes are marked
(config/flakes.yaml, u-boot-ci's bar); every other non-pass case needs a
justification for its board, case and result (config/justifications.yaml),
else the board's verdict is fail; the per-case delta against the board's
latest nightly (or a given baseline, for example `lava:<job>` for a
hand-run job) lists new failures, new passes, still failing, missing and
added cases.

## Where this differs from the design, and why

- **build per board, not per component and board.** TF-A's FIP needs the
  OP-TEE and U-Boot of the same run, and four xeon leases per board
  would only add queueing; each component is a step of its own, with its
  own log, warnings count and fingerprint check.
- **package runs in the build job** (xeon), not on an arm64 4c runner:
  it needs the build outputs, and the package without the BL2 holds no
  secret.
- **monitor, collect and publish share the `track` job.** Both read LAVA
  with the token; the design's separate jobs would be one lease each for
  a loop that sleeps.
- **The rootfs is cached per (qcom-buildroot commit, test-definitions
  commit, makefile and arguments).** The design says per architecture;
  qcom-buildroot builds the rootfs through a board makefile (`kodiak.mk`
  for arm64 today), which stages that board family's firmware into the
  image. Other boards will need either their firmware in the package or
  one rootfs per makefile.
- **test-definitions are in the rootfs partition, not the initramfs.**
  The qcom-buildroot image is used unchanged; the package writes the
  pinned test-definitions to the rootfs partition, as the hand-run jobs
  do.
- **maxcpus and memtest** need a kernel command line of their own; they
  are excluded from the generated job until their jobs exist
  (config/suite.yaml says so with the reason).
