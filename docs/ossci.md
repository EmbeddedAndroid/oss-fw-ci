# The ossci CLI

Validation of any open-stack change is an `ossci` run; hand-built LAVA
jobs and rootfs overlays are not validation.

    python3 -m ossci run [--tfa X] [--optee X] [--uboot X] [--linux X]
                         [--boards "rb3gen2 ..."] [--title T] [--requester R]
    python3 -m ossci wait <run> [--interval 300] [--timeout 43200]

`run` checks every input locally (the forms below), dispatches
`run.yml` with `gh workflow run` and prints the run id
(`<workflow run id>-<attempt>`). It needs `gh` logged in with the right
to dispatch workflows on EmbeddedAndroid/oss-fw-ci.

`wait` polls `results/<run>.json` on gh-pages until every board is final,
then prints per board the state, the fingerprint gate, the verdict, the
counts, the per-case delta against the baseline and every case that is
neither passed nor justified, with its LAVA link. Exit status: 0 when
every board's verdict is pass (every case passed, is justified or a
known flake), 1 when one is not, 2 on timeout.

## Inputs

| component | forms |
|---|---|
| `--tfa` | `owner/repo@ref`, `https://host/repo.git@ref`, `gerrit:<change>[/<patch set>]` (review.trustedfirmware.org) |
| `--optee` | `owner/repo@ref`, `pr:<number>` (OP-TEE/optee_os) |
| `--uboot` | `owner/repo@ref`, `lore:<message-id>` (applied on the baseline pin) |
| `--linux` | `owner/repo@ref`, `lore:<message-id>` (applied on the baseline pin) |

An empty input is the baseline pin (config/baseline.yaml), so a run
that sets one input is an A/B against the baseline with everything else
equal. A ref is a branch, a tag or a full commit id; the run pins it to
the commit it named when the run started.

## Example

    $ python3 -m ossci run --optee EmbeddedAndroid/optee_os@pkvm-p2/p22-fw-smmu --boards rb3gen2 --title "P2.2c"
    19312345678-1
    $ python3 -m ossci wait 19312345678-1
    rb3gen2: done , gate pass, verdict fail, 410 pass / 4 fail / 21 skip (9 justified) https://lava.infra.foundries.io/scheduler/job/...
      against 19300000000-1: new fail none; new pass none; missing 0; added 0
      fail kernel-health/kernel-warning https://lava.infra.foundries.io/scheduler/job/...#L...
