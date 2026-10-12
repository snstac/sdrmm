# DragonEgg SDR-- RX-only package runbook

Status: installable candidate for Debian 13 arm64. Package install creates users, directories and a local deployment secret placeholder but does not enable or start services. Ops/BT must gate any on-host install, enable or RF start.

Default receiver policy: LimeSDR Mini v2 serial 1DBB426135F6EC, RX0/LNAH, GMRS 462-468 MHz, initial 462.5625 MHz, 250 kS/s fixed, gain 0 tenths dB default, AGC/bias off. The bridge exposes rtl_tcp on 127.0.0.1:1234 only. The UI defaults to 127.0.0.1:18080. The UI service sets LD_LIBRARY_PATH=/opt/dragonegg-sdrmm/lib so SDR-- resolves the bundled FFmpeg sonames without host-global library fallback. SDR-- package integration does not enforce HTTP bearer authentication; exposure is loopback plus Ops-approved authenticated tunnel or firewall only. Use SSH tunnel or a separately approved tailnet firewall rule for the UI; do not open raw rtl_tcp off loopback.

Token/secret: /etc/dragonegg-sdrmm/token.env is generated during install with mode 0600 and is never printed by maintainer scripts. No token is embedded in the package. It is reserved for a future approved wrapper/tunnel integration; the current SDR-- UI service does not load it or claim that it enforces UI bearer auth.

USB gate: udev creates /dev/dragonegg-lime-rx only for exact serial 1DBB426135F6EC. ExecStartPre reads sysfs and requires one exact serial plus that symlink, so bus/device number changes on replug are handled without broad USB permission. The bridge service uses DevicePolicy=closed and DeviceAllow=/dev/dragonegg-lime-rx.

Health: sudo dragonegg-sdrmm-health status. Rollback: sudo dragonegg-sdrmm-health rollback, then verify ports 18080 and 1234 are absent. Removal stops/disables units; purge also removes token/state/logs.

Limits: LimeSuite startup may enable/calibrate TX circuitry even when this bridge requests RX only. This package makes no zero-emission claim. G accepted the current RX-only use with that uncertainty; there is no TX API/stream, bias control or stock SoapyRemote in this package. Fault policy is hold/alert, not infinite hardware restart. UI Restart=on-failure is bounded by systemd start limits and RuntimeMaxSec; bridge Restart=no.

Licensing/provenance: SDR-- v1.9.0 commit 3cc6ccb49a631d401f48cbd104eff18baa400e0d is AGPL-3.0-family upstream from https://github.com/Newspicel/sdrminusminus and is maintained for SNSTAC in the fork https://github.com/snstac/sdrmm. This package must preserve corresponding-source obligations and package build instructions before external distribution. FFmpeg libraries carry LGPL/GPL option obligations depending on build flags; keep the original build receipt with this package.

Readiness statement: this is a network-client interim package that reuses the reviewed rtl_tcp bridge path and packaged SDR-- network client. No live RF qualification is claimed here; native LimeSDR RX support remains a separately reviewed source candidate and still needs hardware admission before field-readiness claims.
