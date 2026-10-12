#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PKG="$ROOT/package/aryaos/dragonegg-sdrmm-rx"
PKGROOT="$PKG/pkgroot"
DIST="$ROOT/dist"
OUT="$DIST/dragonegg-sdrmm-rx_0.1.0-3_arm64.deb"
MANIFEST="$DIST/dragonegg-sdrmm-rx_0.1.0-3_SHA256SUMS"
BUILDINFO="$DIST/dragonegg-sdrmm-rx_0.1.0-3_BUILDINFO.txt"

mkdir -p "$DIST"
rm -f "$OUT" "$MANIFEST" "$BUILDINFO"

# Deterministic metadata for repository/release asset reproducibility.
find "$PKGROOT" -type d -exec chmod 0755 {} +
find "$PKGROOT" -type f -exec chmod 0644 {} +
chmod 0755 \
  "$PKGROOT/DEBIAN/postinst" \
  "$PKGROOT/DEBIAN/prerm" \
  "$PKGROOT/DEBIAN/postrm" \
  "$PKGROOT/usr/bin/dragonegg-sdrmm-health" \
  "$PKGROOT/usr/libexec/dragonegg-sdrmm/dragonegg-fault-hold" \
  "$PKGROOT/usr/libexec/dragonegg-sdrmm/dragonegg-health" \
  "$PKGROOT/usr/libexec/dragonegg-sdrmm/dragonegg-lime-gate" \
  "$PKGROOT/usr/libexec/dragonegg-sdrmm/dragonegg-shutdown-receipt" \
  "$PKGROOT/usr/libexec/dragonegg-sdrmm/rx_only_rtltcp_bridge.py" \
  "$PKGROOT/opt/dragonegg-sdrmm/bin/sdrmm"

find "$PKGROOT" -print0 | xargs -0 touch --date='2026-10-12T00:00:00Z'

dpkg-deb --root-owner-group --build "$PKGROOT" "$OUT"

{
  echo "Package: $OUT"
  echo "Built: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "Source fork: https://github.com/snstac/sdrmm"
  echo "Upstream: https://github.com/Newspicel/sdrminusminus"
  echo "Debian control:"
  dpkg-deb --info "$OUT"
  echo
  echo "Contents:"
  dpkg-deb --contents "$OUT"
  echo
  echo "Dynamic dependencies:"
  readelf -d "$PKGROOT/opt/dragonegg-sdrmm/bin/sdrmm" | grep -E 'NEEDED|RPATH|RUNPATH' || true
} > "$BUILDINFO"

(
  cd "$ROOT"
  sha256sum \
    "dist/$(basename "$OUT")" \
    "dist/$(basename "$BUILDINFO")" \
    "package/aryaos/dragonegg-sdrmm-rx/pkgroot/DEBIAN/control" \
    "package/aryaos/dragonegg-sdrmm-rx/pkgroot/etc/dragonegg-sdrmm/dragonegg-sdrmm.conf" \
    "package/aryaos/dragonegg-sdrmm-rx/pkgroot/usr/lib/systemd/system/dragonegg-sdrmm-ui.service" \
    "package/aryaos/dragonegg-sdrmm-rx/pkgroot/usr/lib/systemd/system/dragonegg-rtltcp-bridge.service" \
    "package/aryaos/dragonegg-sdrmm-rx/pkgroot/usr/share/doc/dragonegg-sdrmm-rx/RUNBOOK.md" \
    "scripts/build-aryaos-dragonegg-sdrmm-rx.sh" \
    > "$MANIFEST"
)

echo "$OUT"
echo "$MANIFEST"
