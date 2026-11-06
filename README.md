# oss-fw-ci

One way to validate the open firmware stack (TF-A, OP-TEE, U-Boot,
Linux) on Qualcomm boards, for people and agents alike: a
`workflow_dispatch` run (or `ossci run`) takes a branch, change, PR or
series for any component, builds all four with a fresh fingerprint,
boots them with the pinned qcom-buildroot test rootfs, runs the pinned
open-boot-stack suite (test-definitions, minus ACS) on every board in
LAVA, and publishes the results on GitHub Pages.

    ossci run --optee EmbeddedAndroid/optee_os@pkvm-p2/p22-fw-smmu --boards rb3gen2 --title "P2.2c"
    ossci wait <run>   # 0 when every case passed or is justified

- [Design](docs/DESIGN.md) (approved, the spec)
- [Architecture](docs/architecture.md): jobs, security split, the job
  template, the fingerprint gate, where this differs from the design
- [The ossci CLI](docs/ossci.md)
- [Results schema](docs/results-schema.md) (`ossci-run/1`)
- [Suite, rootfs and pins](docs/pins.md)
- [Setup](docs/setup.md): environment, secrets, the bridge, the lease driver
- [Shared fwci package](docs/fwci.md): what u-boot-ci and this repository share

Everything runs in the containers of `docker/` (`scripts/in-container.sh`),
on CIL VMs only: no GitHub-hosted runner. Unit tests:

    docker build --target control -t ossci-control:1 docker
    scripts/in-container.sh python3 -m pytest -q tests
