# HANDOFF — AryaOS DragonEgg SDR-- RX package release candidate

Task: t_62ccff1e
Branch: snstac/aryaos-arm64-package
Draft PR: https://github.com/snstac/sdrmm/pull/1
Fork: https://github.com/snstac/sdrmm
Upstream: https://github.com/Newspicel/sdrminusminus

## Targeted QA repair

- Fixed native ARM64 CI runtime proof: aarch64 runs the extracted package binary directly with `LD_LIBRARY_PATH`; x86_64 keeps `qemu-aarch64 -L /usr/aarch64-linux-gnu`.
- Added tests for both runtime command-selection paths.
- Fixed mutable artifact path: builds now stage in a unique `dist/.dragonegg-sdrmm-rx-build.*` directory, then copy and `mv -f` finished `.deb`, buildinfo and manifest into stable `dist/` names.
- Fixed reproducibility: fixed package mtimes, `SOURCE_DATE_EPOCH`, deterministic build stamp and stable buildinfo. Two clean builds now produce identical hashes.
- Added a tag-gated release job for `aryaos-rx-v*` tags. It runs only after green build/test, grants `contents: write` only to the release job and attaches the `.deb`, SHA256 manifest and buildinfo to a GitHub Release. No tag or release was created in this run.

## Built

- Package path: `package/aryaos/dragonegg-sdrmm-rx`.
- Package name/version: `dragonegg-sdrmm-rx` `0.1.0-3`, distinct from upstream `sdrmm` and the prior DragonEgg live install.
- Built artifact: `dist/dragonegg-sdrmm-rx_0.1.0-3_arm64.deb`.
- Package SHA256: `45e80fbfba836dfd7cdb63a1cb770da666f65810ccd0882598e78db501f73515`.
- Release workflow assets: versioned `.deb`, `dragonegg-sdrmm-rx_0.1.0-3_SHA256SUMS`, `dragonegg-sdrmm-rx_0.1.0-3_BUILDINFO.txt`.
- Source archive for AGPL correspondence is the tagged fork source archive from `snstac/sdrmm`.

## Safety and acceptance notes

- Services install disabled; maintainer scripts do not enable or start DragonEgg services.
- Defaults are loopback-only: `RTL_TCP_BIND=127.0.0.1`, `SDRMM_BIND=127.0.0.1`, `TAILNET_EXPOSURE=disabled`.
- No `token.env` is packaged. The package still creates a local 0600 placeholder secret on install for future approved wrapper/tunnel integration; the UI service does not load it or claim bearer-auth enforcement.
- Lime RX gate remains exact serial `1DBB426135F6EC`, udev symlink `/dev/dragonegg-lime-rx`, and service `DevicePolicy=closed`/`DeviceAllow=/dev/dragonegg-lime-rx rw`.
- Package policy and runbook state no TX API/stream, bias control, or stock SoapyRemote path. No live Egg, host install, service start, RF command, GitHub Release, apt repository publication, or production host change was performed.
- Source/license provenance is documented in the runbook: AGPL-3.0-family SDR-- upstream from Newspicel/sdrminusminus, maintained in snstac/sdrmm; corresponding source and package build instructions must ship before external distribution.

## Test evidence

Command:

```text
$ PYTHONWARNINGS=error python3 -m unittest tests.test_aryaos_package -v > dist/test-output-aryaos-package.txt 2>&1
```

Recorded result:

```text
test_arm64_runtime_command_selects_native_on_arm64 ... ok
test_arm64_runtime_command_selects_qemu_on_x86_64 ... ok
test_bridge_fails_closed_for_nonloopback_without_admission ... ok
test_build_script_and_release_workflow_exist ... ok
test_control_package_identity_and_arm64 ... ok
test_deb_build_is_reproducible ... ok
test_deb_builds_and_arm64_binary_runs ... ok
test_deb_modes_and_no_packaged_token_env ... ok
test_extract_upgrade_remove_rollback_simulation_by_inspection ... ok
test_no_tx_or_generic_remote_paths_in_package_policy ... ok
test_release_workflow_publishes_tagged_deb_assets ... ok
test_services_disabled_loopback_no_token_exact_lime_serial ... ok
test_source_license_and_provenance_are_declared ... ok

----------------------------------------------------------------------
Ran 13 tests in 24.322s

OK
```

Full log: `dist/test-output-aryaos-package.txt`.

## Reproducibility evidence

Command:

```text
$ scripts/build-aryaos-dragonegg-sdrmm-rx.sh > dist/build-1.txt
$ sha256sum dist/dragonegg-sdrmm-rx_0.1.0-3_arm64.deb dist/dragonegg-sdrmm-rx_0.1.0-3_BUILDINFO.txt dist/dragonegg-sdrmm-rx_0.1.0-3_SHA256SUMS > dist/build-1-sha256.txt
$ scripts/build-aryaos-dragonegg-sdrmm-rx.sh > dist/build-2.txt
$ sha256sum dist/dragonegg-sdrmm-rx_0.1.0-3_arm64.deb dist/dragonegg-sdrmm-rx_0.1.0-3_BUILDINFO.txt dist/dragonegg-sdrmm-rx_0.1.0-3_SHA256SUMS > dist/build-2-sha256.txt
$ diff -u dist/build-1-sha256.txt dist/build-2-sha256.txt
$ sha256sum -c dist/dragonegg-sdrmm-rx_0.1.0-3_SHA256SUMS
```

Result:

```text
No diff between build-1-sha256.txt and build-2-sha256.txt.
dist/dragonegg-sdrmm-rx_0.1.0-3_arm64.deb: OK
dist/dragonegg-sdrmm-rx_0.1.0-3_BUILDINFO.txt: OK
package/aryaos/dragonegg-sdrmm-rx/pkgroot/DEBIAN/control: OK
package/aryaos/dragonegg-sdrmm-rx/pkgroot/etc/dragonegg-sdrmm/dragonegg-sdrmm.conf: OK
package/aryaos/dragonegg-sdrmm-rx/pkgroot/usr/lib/systemd/system/dragonegg-sdrmm-ui.service: OK
package/aryaos/dragonegg-sdrmm-rx/pkgroot/usr/lib/systemd/system/dragonegg-rtltcp-bridge.service: OK
package/aryaos/dragonegg-sdrmm-rx/pkgroot/usr/share/doc/dragonegg-sdrmm-rx/RUNBOOK.md: OK
scripts/build-aryaos-dragonegg-sdrmm-rx.sh: OK
```

Rebuilt artifact hashes:

```text
45e80fbfba836dfd7cdb63a1cb770da666f65810ccd0882598e78db501f73515  dist/dragonegg-sdrmm-rx_0.1.0-3_arm64.deb
d71dd83ee87fe10966ea9d1472d3d72dd223ae4bb4796c0e0aaf28b619ece43e  dist/dragonegg-sdrmm-rx_0.1.0-3_BUILDINFO.txt
f3be528dee1b247214b120194946f71f24bf5a97f972c24fa555bb9218578855  dist/dragonegg-sdrmm-rx_0.1.0-3_SHA256SUMS
```

## Package metadata and content evidence

Command:

```text
$ dpkg-deb --field dist/dragonegg-sdrmm-rx_0.1.0-3_arm64.deb Package Version Architecture Depends
Package: dragonegg-sdrmm-rx
Version: 0.1.0-3
Architecture: arm64
Depends: adduser, systemd, python3, ca-certificates, iproute2
```

Content spot check:

```text
-rwxr-xr-x root/root  52181368 2026-10-11 17:00 ./opt/dragonegg-sdrmm/bin/sdrmm
-rw-r--r-- root/root      1890 2026-10-11 17:00 ./usr/lib/systemd/system/dragonegg-rtltcp-bridge.service
-rw-r--r-- root/root       133 2026-10-11 17:00 ./usr/lib/systemd/system/dragonegg-rx-hold.service
-rw-r--r-- root/root      1424 2026-10-11 17:00 ./usr/lib/systemd/system/dragonegg-sdrmm-ui.service
-rwxr-xr-x root/root     27391 2026-10-11 17:00 ./usr/libexec/dragonegg-sdrmm/rx_only_rtltcp_bridge.py
```

Dynamic dependency evidence remains in `dist/dragonegg-sdrmm-rx_0.1.0-3_BUILDINFO.txt`.

## Release path

Do not run before QA/BT approval. After merge and release approval, tag the approved commit with an `aryaos-rx-v*` tag and push it:

```text
git tag -a aryaos-rx-v0.1.0-3 -m "AryaOS DragonEgg SDR-- RX 0.1.0-3"
git push origin aryaos-rx-v0.1.0-3
```

The tag workflow runs build/test first. On success, it executes:

```text
gh release create "$GITHUB_REF_NAME" \
  --repo "$GITHUB_REPOSITORY" \
  --title "AryaOS DragonEgg SDR-- RX $GITHUB_REF_NAME" \
  --notes "AryaOS DragonEgg SDR-- RX arm64 package. Source archive is the tagged fork source for AGPL-3.0 correspondence." \
  dist/dragonegg-sdrmm-rx_0.1.0-3_arm64.deb \
  dist/dragonegg-sdrmm-rx_0.1.0-3_SHA256SUMS \
  dist/dragonegg-sdrmm-rx_0.1.0-3_BUILDINFO.txt
```

This satisfies the `snstac/packages/build-repo.sh` path that uses `gh release download --repo snstac/sdrmm --pattern *.deb`.

## Artifact manifest

```text
45e80fbfba836dfd7cdb63a1cb770da666f65810ccd0882598e78db501f73515  dist/dragonegg-sdrmm-rx_0.1.0-3_arm64.deb
d71dd83ee87fe10966ea9d1472d3d72dd223ae4bb4796c0e0aaf28b619ece43e  dist/dragonegg-sdrmm-rx_0.1.0-3_BUILDINFO.txt
f3be528dee1b247214b120194946f71f24bf5a97f972c24fa555bb9218578855  dist/dragonegg-sdrmm-rx_0.1.0-3_SHA256SUMS
ab8e849104d2e4a7d067f5907319cb125692229e28232c665b98dd912b1f518a  dist/test-output-aryaos-package.txt
4aace794f09cca718202604fc403befe5b14d63ad66f30ff2cfa46a2443afddc  tests/test_aryaos_package.py
fa413700b1e4f3fc0b8d1203f74110958d31e99de0824a0247efcab0742296c2  scripts/build-aryaos-dragonegg-sdrmm-rx.sh
8e83fce0726581237c99697c5a03a3da4c0bc1891839d5531772cc404c55029f  .github/workflows/aryaos-dragonegg-sdrmm-rx.yml
```

Full manifest: `dist/FINAL-SHA256SUMS`.

## Changed files

- `.github/workflows/aryaos-dragonegg-sdrmm-rx.yml`
- `HANDOFF.md`
- `dist/FINAL-SHA256SUMS`
- `scripts/build-aryaos-dragonegg-sdrmm-rx.sh`
- `tests/test_aryaos_package.py`

## Known limitations / gates

- Native LimeSDR RX source work remains the previously reviewed candidate and is not claimed field-ready here. This branch packages the reviewed network-client/rtl_tcp interim path.
- Full disposable Debian 13 arm64 `dpkg -i`, systemd manager lifecycle, udev event handling and live RF remain QA/Ops/BT gates. This run used package extraction, maintainer-script inspection, dpkg metadata/content checks and qemu/native runtime proof only.
- GitHub tag, GitHub Release and signed apt repository publication were intentionally not performed.
