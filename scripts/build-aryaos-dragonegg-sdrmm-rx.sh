#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PKG="$ROOT/package/aryaos/dragonegg-sdrmm-rx"
PKGROOT="$PKG/pkgroot"
DIST="$ROOT/dist"
OUT="$DIST/dragonegg-sdrmm-rx_0.1.0-3_arm64.deb"
MANIFEST="$DIST/dragonegg-sdrmm-rx_0.1.0-3_SHA256SUMS"
BUILDINFO="$DIST/dragonegg-sdrmm-rx_0.1.0-3_BUILDINFO.txt"
BUILD_EPOCH=1791763200
BUILD_STAMP=2026-10-12T00:00:00Z
export TZ=UTC

mkdir -p "$DIST"
STAGE=$(mktemp -d "$DIST/.dragonegg-sdrmm-rx-build.XXXXXX")
trap 'rm -rf "$STAGE"' EXIT
STAGE_ROOT="$STAGE/pkgroot"
STAGE_OUT="$STAGE/$(basename "$OUT")"
STAGE_MANIFEST="$STAGE/$(basename "$MANIFEST")"
STAGE_BUILDINFO="$STAGE/$(basename "$BUILDINFO")"
cp -a "$PKGROOT" "$STAGE_ROOT"

# Deterministic metadata for repository/release asset reproducibility.
find "$STAGE_ROOT" -type d -exec chmod 0755 {} +
find "$STAGE_ROOT" -type f -exec chmod 0644 {} +
chmod 0755 \
  "$STAGE_ROOT/DEBIAN/postinst" \
  "$STAGE_ROOT/DEBIAN/prerm" \
  "$STAGE_ROOT/DEBIAN/postrm" \
  "$STAGE_ROOT/usr/bin/dragonegg-sdrmm-health" \
  "$STAGE_ROOT/usr/libexec/dragonegg-sdrmm/dragonegg-fault-hold" \
  "$STAGE_ROOT/usr/libexec/dragonegg-sdrmm/dragonegg-health" \
  "$STAGE_ROOT/usr/libexec/dragonegg-sdrmm/dragonegg-lime-gate" \
  "$STAGE_ROOT/usr/libexec/dragonegg-sdrmm/dragonegg-shutdown-receipt" \
  "$STAGE_ROOT/usr/libexec/dragonegg-sdrmm/rx_only_rtltcp_bridge.py" \
  "$STAGE_ROOT/opt/dragonegg-sdrmm/bin/sdrmm"

find "$STAGE_ROOT" -print0 | sort -z | xargs -0 touch --date="@$BUILD_EPOCH"

SOURCE_DATE_EPOCH=$BUILD_EPOCH dpkg-deb --root-owner-group --uniform-compression -Zgzip -z9 --threads-max=1 --build "$STAGE_ROOT" "$STAGE_OUT"

{
  echo "Package: dist/$(basename "$OUT")"
  echo "Built: $BUILD_STAMP"
  echo "Source fork: https://github.com/snstac/sdrmm"
  echo "Upstream: https://github.com/Newspicel/sdrminusminus"
  echo "Debian control:"
  dpkg-deb --info "$STAGE_OUT"
  echo
  echo "Contents:"
  dpkg-deb --contents "$STAGE_OUT"
  echo
  echo "Dynamic dependencies:"
  readelf -d "$STAGE_ROOT/opt/dragonegg-sdrmm/bin/sdrmm" | grep -E 'NEEDED|RPATH|RUNPATH' || true
} > "$STAGE_BUILDINFO"

cp "$STAGE_OUT" "$DIST/$(basename "$OUT").tmp"
cp "$STAGE_BUILDINFO" "$DIST/$(basename "$BUILDINFO").tmp"
mv -f "$DIST/$(basename "$OUT").tmp" "$OUT"
mv -f "$DIST/$(basename "$BUILDINFO").tmp" "$BUILDINFO"

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
    > "$STAGE_MANIFEST"
)
cp "$STAGE_MANIFEST" "$DIST/$(basename "$MANIFEST").tmp"
mv -f "$DIST/$(basename "$MANIFEST").tmp" "$MANIFEST"

echo "$OUT"
echo "$MANIFEST"
