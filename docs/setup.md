# GitHub, lab and lease setup

## Runners: the CIL GitHub Actions bridge

Every job runs on an ephemeral CIL VM that cil-gha-bridge provisions
from the job's `runs-on` labels: `[self-hosted, cil, arm64, 2c-4g-20g]`
for resolve, submit, track, finalize and the unit tests (the arm64 pool),
`[self-hosted, cil, 32c-32g-200g]` for the rootfs and the builds (the
xeon pool). No GitHub-hosted runner, so no billed minutes.

Onboarding (Tyler, by hand): install the bridge's GitHub App on
EmbeddedAndroid/oss-fw-ci and set the repository's concurrency cap in
the bridge (a run holds at most 1 + boards xeon leases and one arm64
lease at a time; 4 is enough for one RB3 Gen 2 run and the unit tests).

## Environment `lava-hw`

Created with deployment branches `main` only and no reviewer (as
u-boot-ci's). Only `submit` and `track` declare it. Secrets (Tyler adds
them by hand: Settings, Environments, lava-hw, Add environment secret,
or `gh secret set <NAME> --env lava-hw --repo EmbeddedAndroid/oss-fw-ci`,
which prompts for the value):

| secret | content |
|---|---|
| `LAVA_TOKEN` | the LAVA token of the CI user (u-boot-ci uses `robotyler`) |
| `OSSCI_PRIVATE_TOKEN` | a fine-grained personal access token of EmbeddedAndroid: repository access only `EmbeddedAndroid/oss-fw-ci-private`, permission Contents read-only, nothing else, an expiry of a year at most |

Without `LAVA_TOKEN` a run builds everything and marks every board
`skipped` ("no LAVA_TOKEN"); without `OSSCI_PRIVATE_TOKEN` a board whose
BL2 is private is `skipped` ("BL2 pin not available"). Neither value is
ever printed: the private store errors say only an HTTP status.

The LAVA user needs submit rights on every device type of boards.yaml
and the LAVA MCP artifact store, and a remote artifact token named as
boards.yaml `lava.restore.token_name` for the lab image restore
(`Q_QLI_S3_TOKEN` for RB3 Gen 2, as the lab's own jobs use).

## Pages and permissions

- Settings, Pages: Deploy from a branch, `gh-pages`, `/`. The
  dashboard is then https://embeddedandroid.github.io/oss-fw-ci/.
- Actions, Workflow permissions: read by default; the jobs that write
  gh-pages declare `contents: write`.

## The lease driver

When a pin cannot be fetched publicly yet (config/baseline.yaml
`pending`, config/rootfs.yaml `source.repo: null`), the workflow skips
the run and says why. The same steps then run from one CIL lease that
holds those trees (bundles synced from the laptop, which stays
authoritative), with the operator's LAVA token in the environment only:

    python3 scripts/lease/lease.py new oss-fw-ci-<task> 32 32768 300 1440
    python3 scripts/lease/lease.py wait <id>
    S=$(python3 scripts/lease/lease.py ssh-args <id>)
    git archive HEAD | ssh $S 'mkdir -p oss-fw-ci && tar -x -C oss-fw-ci'
    ssh $S bash oss-fw-ci/scripts/lease/setup.sh
    # trees and bundles: see scripts/lease/drive.sh
    ssh $S oss-fw-ci/scripts/lease/drive.sh <run id> <board> [<component>=<input> ...]

`drive.sh` runs resolve (with the pending trees as staged checkouts),
the rootfs, the board build, then `ossci.run submit/monitor/collect` and
leaves the run document in `work/`; it is published to gh-pages from the
laptop checkout with `scripts/publish-site.sh`. Its documents say
`driver: lease`. Release the lease at the end (`lease.py release <id>`).
