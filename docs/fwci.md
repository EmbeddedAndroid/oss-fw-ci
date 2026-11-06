# The shared fwci package

`fwci/` holds the framework that u-boot-ci and oss-fw-ci share and
nothing specific to either: LAVA job building blocks (qdl flash, the
fingerprint gate over any banner prefixes, interactive and shell checks,
login), the collector, the boot verdict, the baseline diff, the flake
list, the distance to upstream, the LAVA MCP and REST clients, the
links, the boot-time parser (`lava_boottime/`, vendored from
lava-boottime) and u-boot-ci's results schema.

It lives here as the canonical copy: oss-fw-ci imports it as it is, and
u-boot-ci vendors it byte for byte (its `scripts/vendor-fwci.sh` records
the oss-fw-ci commit and every file's sha256 in `fwci/VENDOR.json`, and
a test fails when the copy differs from that manifest), so a change to
the framework is made here, reviewed once, and vendored into u-boot-ci.
The copy in this repository was taken from u-boot-ci main f4a9ea1 and
is unchanged; oss-fw-ci adds what is its own in `ossci/` (the
multi-component inputs, the suite, the rootfs pin, justifications, its
schema `ossci-run/1`).

The u-boot-ci side is proposed as a local branch (not pushed):
`ci/vendor-fwci` in ~/monza/optee-int-refresh/u-boot-ci, which adds the
vendor script, the manifest and the test, and changes no fwci byte, so
u-boot-ci behaves as before.
