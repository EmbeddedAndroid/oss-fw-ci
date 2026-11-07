# Results schema (ossci-run/1)

One JSON document per run, `results/<run>.json` on gh-pages, checked
against `ossci/schema/run.schema.json` (JSON Schema 2020-12) every time
it is written or published. `index.json` lists the latest nightly per
board and the recent runs (schema `ossci-index/1`). Agents read these
two files; the dashboard reads nothing else.

- `run`: `id` (`<workflow run id>-<attempt>`), `kind` (`adhoc`,
  `nightly`), `title`, `requester`, `created`, `updated`, `ci_url`,
  `driver` (`workflow`: run.yml; `lease`: the same steps driven from one
  CIL lease, docs/setup.md), `baseline` (the run or `lava:<job>` the
  delta is against).
- `state`: `building`, `testing`, `done`, or `error` / `cancelled` when
  the workflow failed or was cancelled first; `note` says why.
- `inputs`: per component (`tfa`, `optee`, `uboot`, `linux`): `repo`,
  `ref`, `commit`, `role` (`baseline` or `under-test`), `link` and
  `title` for a Gerrit change or a PR, `series` for a lore series
  (message id, link), `pending` when the commit cannot be fetched
  publicly yet, and `input`, the input as given.
- `suite`: test-definitions `repo`, `branch`, `commit`, `plan` and the
  `exclude`d definitions with the reason.
- `rootfs`: qcom-buildroot `repo` and `commit`, `upstream` (false while
  the pin is not an upstream commit: the dashboard marks it "not yet
  upstream"), `note`, `overrides` (manifest projects taken at another
  revision, with the reason), and once built `fingerprint`, `sha256` (of
  rootfs.cpio.gz), `key` (the cache key id), `makefile`, `make_args`,
  `manifest` (the repo manifest as synced).
- `targets[]`, one per board:
  - `board`, `device_type`, `state` (`building`, `queued`, `flashing`,
    `testing`, `done`, `skipped`, `error`, `cancelled`), `state_detail`
    (why, for the last three), `queue_position`;
  - `fingerprint` (`ossci-<run>-<attempt>-<board>`) and `bl2` (the pinned
    image: the secret it comes from, file, sha256, fingerprint; documents
    before 2026-11-07 name the private-store `release` instead);
  - `builds`: per component the fingerprint, commit, sha256 of its images
    and its warnings count; `package` (file, sha256, size);
  - `lava`: job id, link, device, health;
  - `fingerprint_gate`: `pass` only when both boots showed every stage
    with its expected fingerprint;
  - `linux_boot`, `boot_time`: as fwci's collector writes them
    (u-boot-ci docs/results-schema.md);
  - `cases[]`: `suite`, `name`, `result` (`pass`, `fail`, `skip`,
    `unknown`), `url` (the LAVA log line), `flake`, `note`, `output`,
    and `justified` (`reason`, `evidence`, `reviewer`) when
    config/justifications.yaml covers the case;
  - `verdict`: `pass` when every case passed, is justified or a known
    flake, and the gate passed; `counts` (pass, fail, skip, unknown,
    justified, flaky);
  - `diff` (only when both gates passed): `baseline`, `new_fail`,
    `new_pass`, `still_fail`, `missing` (in the baseline, not here),
    `added`.
