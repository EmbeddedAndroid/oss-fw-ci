# Suite, rootfs and component pins

Every pin is a reviewed change to a file of `config/`:

- `suite.yaml`: test-definitions repository, branch and **commit**, the
  plan file, the excluded definitions with the reason, and the phases
  (which definitions repeat after the warm reboot, which run last).
  The list of tests is the plan at that commit; nothing else adds to it.
- `rootfs.yaml`: qcom-buildroot repository and **commit**, `upstream`
  (false while the pin is not an upstream commit), where the commit can
  be fetched meanwhile (`source.repo`, null when nowhere public), `watch`
  (the upstream change the pin moves to once it lands), the
  repo manifest, and per architecture the makefile, make arguments and
  output, and `manifest_overrides`: a revision for a project the
  manifest leaves on a moving branch that no longer builds with the
  manifest's own pins, each with its reason (a qcom-buildroot bug to fix
  upstream, then dropped here). The rootfs job builds the tree only when `ossci.rootfs check`
  finds it exactly at the pin with nothing applied, and checks the
  tracked files again after the build. To change the image, change
  qcom-buildroot upstream first, then move this pin.
- `baseline.yaml`: the baseline commit of each component (the
  integration branches, by dated tag). `pending` marks a commit that is
  not public yet: the workflow then refuses to run on that baseline and
  says so (give that component as an input, or use the lease driver).
- `boards.yaml`: per board everything the build, package, job and gate
  need, the pinned BL2 (`secret`, `file`, `sha256`, `fingerprint`: the
  image is the `PIN_BL2_<BOARD>` secret of `lava-hw`, docs/setup.md) and
  the facts (parameter values of the suite's
  definitions).
- `justifications.yaml`: the only way a case may end other than pass.
- `flakes.yaml`, `known-errors.yaml`: as in u-boot-ci.

## Today (2026-11-07)

| pin | value | public |
|---|---|---|
| suite | EmbeddedAndroid/test-definitions openbootstack-tests 81c6b8ef | yes |
| rootfs | qualcomm-linux/qcom-buildroot main 6bd87d7, TEST=y | yes; watch: the test-config PR (qcom-test-suite 79369f4) for tee-shm-reclaim, suspend-idle and the QEMU kvm-unit-tests |
| rootfs override | optee_test 953c169 (manifest leaves it on master; master since 00d4f0e needs an ASLR PTA the pinned optee_os 9bcaec96 lacks) | yes (qcom-buildroot fix needed) |
| TF-A | EmbeddedAndroid qcom/integration-20261102g 95a4c903a (= qcom/integration) | yes |
| OP-TEE | EmbeddedAndroid qcom/integration-20261105 b5e5f7a0f (= qcom/integration) | yes |
| U-Boot | EmbeddedAndroid qcom/integration-20261105a 55f4e43a871 (= qcom/integration) | yes |
| Linux | EmbeddedAndroid qcom/integration-20261107 0b3b9dd83f9e9 (linux-int qcom/integration, next-20261103 base) | yes |
| RB3 Gen 2 BL2 | QCDFP-261102-526, sha256 29344d74 (secret PIN_BL2_RB3GEN2, the image of LAVA 540899) | no, by design |
