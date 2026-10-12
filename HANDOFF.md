# HANDOFF — AryaOS DragonEgg SDR-- RX package release candidate

Task: t_62ccff1e
Branch: snstac/aryaos-arm64-package
Fork: https://github.com/snstac/sdrmm
Upstream: https://github.com/Newspicel/sdrminusminus

## Built

- Added an AryaOS/Debian 13 arm64 package candidate under `package/aryaos/dragonegg-sdrmm-rx`.
- Package name/version: `dragonegg-sdrmm-rx` `0.1.0-3`, distinct from upstream `sdrmm` and the prior DragonEgg live install.
- Built artifact: `dist/dragonegg-sdrmm-rx_0.1.0-3_arm64.deb`.
- Package SHA256: `0c40ff6f81ff2e91e07618cdda0db326b16a20f022924172736f145f09c73f6f`.
- Added `scripts/build-aryaos-dragonegg-sdrmm-rx.sh` to normalize modes/timestamps, build with `dpkg-deb --root-owner-group`, emit build info and SHA256 sums.
- Added `.github/workflows/aryaos-dragonegg-sdrmm-rx.yml` to build/test/hash and upload package assets for PR/branch CI.
- Reused reviewed `package-candidate` package root and rtl_tcp bridge, plus the reviewed SDR-- network-client binary and bundled FFmpeg sonames. This is explicitly a network-client interim package; no native live RF qualification is claimed.

## Safety and acceptance notes

- Services install disabled; maintainer scripts do not enable or start DragonEgg services.
- Defaults are loopback-only: `RTL_TCP_BIND=127.0.0.1`, `SDRMM_BIND=127.0.0.1`, `TAILNET_EXPOSURE=disabled`.
- No `token.env` is packaged. The package still creates a local 0600 placeholder secret on install for future approved wrapper/tunnel integration; the UI service does not load it or claim bearer-auth enforcement.
- Lime RX gate remains exact serial `1DBB426135F6EC`, udev symlink `/dev/dragonegg-lime-rx`, and service `DevicePolicy=closed`/`DeviceAllow=/dev/dragonegg-lime-rx rw`.
- Package policy and runbook state no TX API/stream, bias control, or stock SoapyRemote path. No live Egg, host install, service start, RF command, GitHub Release, apt repository publication, or production host change was performed.
- Source/license provenance is documented in the runbook: AGPL-3.0-family SDR-- upstream from Newspicel/sdrminusminus, maintained in snstac/sdrmm; corresponding source and package build instructions must ship before external distribution.

## TDD evidence

Initial failing test command before package files/scripts existed:

```text
$ PYTHONWARNINGS=error python3 -m unittest tests.test_aryaos_package -v
Ran 6 tests in 0.014s
FAILED (failures=1, errors=5)
Representative failures: missing scripts/build-aryaos-dragonegg-sdrmm-rx.sh, missing package/aryaos/dragonegg-sdrmm-rx/pkgroot/DEBIAN/control, missing package config/runbook/service files.
```

Final warnings-as-errors test command and output:

```text
$ PYTHONWARNINGS=error python3 -m unittest tests.test_aryaos_package -v > dist/test-output-aryaos-package.txt 2>&1
$ tail-equivalent excerpt from recorded output:
test_bridge_fails_closed_for_nonloopback_without_admission (tests.test_aryaos_package.AryaOSPackageTests.test_bridge_fails_closed_for_nonloopback_without_admission) ... ok
test_build_script_and_release_workflow_exist (tests.test_aryaos_package.AryaOSPackageTests.test_build_script_and_release_workflow_exist) ... ok
test_control_package_identity_and_arm64 (tests.test_aryaos_package.AryaOSPackageTests.test_control_package_identity_and_arm64) ... ok
test_deb_builds_and_arm64_binary_runs_under_qemu (tests.test_aryaos_package.AryaOSPackageTests.test_deb_builds_and_arm64_binary_runs_under_qemu) ... dpkg-deb: building package 'dragonegg-sdrmm-rx' in '/home/hermes/work/snstac/dragonegg-platform/sdrmm-release-candidate/dist/dragonegg-sdrmm-rx_0.1.0-3_arm64.deb'.
/home/hermes/work/snstac/dragonegg-platform/sdrmm-release-candidate/dist/dragonegg-sdrmm-rx_0.1.0-3_arm64.deb
/home/hermes/work/snstac/dragonegg-platform/sdrmm-release-candidate/dist/dragonegg-sdrmm-rx_0.1.0-3_SHA256SUMS
ok
test_deb_modes_and_no_packaged_token_env (tests.test_aryaos_package.AryaOSPackageTests.test_deb_modes_and_no_packaged_token_env) ... ok
test_extract_upgrade_remove_rollback_simulation_by_inspection (tests.test_aryaos_package.AryaOSPackageTests.test_extract_upgrade_remove_rollback_simulation_by_inspection) ... ok
test_no_tx_or_generic_remote_paths_in_package_policy (tests.test_aryaos_package.AryaOSPackageTests.test_no_tx_or_generic_remote_paths_in_package_policy) ... ok
test_services_disabled_loopback_no_token_exact_lime_serial (tests.test_aryaos_package.AryaOSPackageTests.test_services_disabled_loopback_no_token_exact_lime_serial) ... ok
test_source_license_and_provenance_are_declared (tests.test_aryaos_package.AryaOSPackageTests.test_source_license_and_provenance_are_declared) ... ok

----------------------------------------------------------------------
Ran 9 tests in 18.325s

OK
```

## Package metadata, contents and dependency evidence

Command:

```text
$ dpkg-deb --field dist/dragonegg-sdrmm-rx_0.1.0-3_arm64.deb Package Version Architecture Depends
Package: dragonegg-sdrmm-rx
Version: 0.1.0-3
Architecture: arm64
Depends: adduser, systemd, python3, ca-certificates, iproute2
```

Dynamic dependency evidence:

```text
$ readelf -d package/aryaos/dragonegg-sdrmm-rx/pkgroot/opt/dragonegg-sdrmm/bin/sdrmm | grep -E 'NEEDED|RPATH|RUNPATH'
 0x0000000000000001 (NEEDED)             Shared library: [libm.so.6]
 0x0000000000000001 (NEEDED)             Shared library: [libavutil.so.61]
 0x0000000000000001 (NEEDED)             Shared library: [libavcodec.so.63]
 0x0000000000000001 (NEEDED)             Shared library: [libswscale.so.10]
 0x0000000000000001 (NEEDED)             Shared library: [libswresample.so.7]
 0x0000000000000001 (NEEDED)             Shared library: [libgcc_s.so.1]
 0x0000000000000001 (NEEDED)             Shared library: [libc.so.6]
 0x0000000000000001 (NEEDED)             Shared library: [ld-linux-aarch64.so.1]
 0x000000000000000f (RPATH)              Library rpath: [$ORIGIN:$ORIGIN/../lib/sdrmm:$ORIGIN/../lib/sdrminusminus]
```

Runtime proof is included in `test_deb_builds_and_arm64_binary_runs_under_qemu`: it extracts the built arm64 `.deb`, sets `LD_LIBRARY_PATH` to the extracted package FFmpeg lib directory, and runs `qemu-aarch64 -L /usr/aarch64-linux-gnu <extracted>/opt/dragonegg-sdrmm/bin/sdrmm --help`; the test requires exit 0 and `Usage: sdrmm` in stdout.

## Artifact manifest

```text
0c40ff6f81ff2e91e07618cdda0db326b16a20f022924172736f145f09c73f6f  dist/dragonegg-sdrmm-rx_0.1.0-3_arm64.deb
13fd8aa581529122e71a354e286f89116e43cb45c2f88e950d89839c0e0a9e35  dist/dragonegg-sdrmm-rx_0.1.0-3_BUILDINFO.txt
86702b3ec7b277a74b69d00190f610feec4f5542e0072b7c0300330a82decd8f  dist/dragonegg-sdrmm-rx_0.1.0-3_SHA256SUMS
1cd10178a10d4a66815273bcfd1fdf1487e07fd73df8ea85c70541e1b97ed364  dist/test-output-aryaos-package.txt
61cf97dea623b4b00c141eade1626859e8be06d1f09b9ea87459fe42edd31a06  tests/test_aryaos_package.py
cbb8f800022c3c372c7f2b1c32dda85dc0cc51e4d7426dd76b50c228e347b8d1  scripts/build-aryaos-dragonegg-sdrmm-rx.sh
716afb8e48b8504d4d01864c371936037fb85fba3003f2c1b0cd452d6825f2e1  .github/workflows/aryaos-dragonegg-sdrmm-rx.yml
```

Full build info: `dist/dragonegg-sdrmm-rx_0.1.0-3_BUILDINFO.txt`.
Full test log: `dist/test-output-aryaos-package.txt`.
Full manifest: `dist/FINAL-SHA256SUMS`.

## Changed files

- `.github/workflows/aryaos-dragonegg-sdrmm-rx.yml`
- `HANDOFF.md`
- `package/aryaos/dragonegg-sdrmm-rx/**`
- `scripts/build-aryaos-dragonegg-sdrmm-rx.sh`
- `tests/test_aryaos_package.py`

## Known limitations / gates

- Native LimeSDR RX source work remains the previously reviewed candidate and is not claimed field-ready here. This branch packages the reviewed network-client/rtl_tcp interim path.
- Full disposable Debian 13 arm64 `dpkg -i`, systemd manager lifecycle, udev event handling and live RF remain QA/Ops/BT gates. This run used package extraction, maintainer-script inspection, dpkg metadata/content checks and qemu-aarch64 runtime proof only.
- GitHub Release and signed apt repository publication were intentionally not performed.
