import os
import pathlib
import platform
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PKG = ROOT / "package" / "aryaos" / "dragonegg-sdrmm-rx"
DIST = ROOT / "dist"
DEB = DIST / "dragonegg-sdrmm-rx_0.1.0-3_arm64.deb"


def read(path):
    return path.read_text(encoding="utf-8")


def arm64_runtime_command(binary, machine=None):
    arch = machine or platform.machine()
    if arch in {"aarch64", "arm64"}:
        return [str(binary), "--help"]
    return ["qemu-aarch64", "-L", "/usr/aarch64-linux-gnu", str(binary), "--help"]


class AryaOSPackageTests(unittest.TestCase):
    def test_build_script_and_release_workflow_exist(self):
        script = ROOT / "scripts" / "build-aryaos-dragonegg-sdrmm-rx.sh"
        workflow = ROOT / ".github" / "workflows" / "aryaos-dragonegg-sdrmm-rx.yml"
        self.assertTrue(script.exists())
        self.assertIn("dpkg-deb --root-owner-group", read(script))
        self.assertIn("--build", read(script))
        self.assertIn("--uniform-compression -Zgzip -z9 --threads-max=1", read(script))
        self.assertIn("sha256sum", read(script))
        self.assertIn("mktemp -d", read(script))
        self.assertIn("mv -f", read(script))
        self.assertTrue(workflow.exists())
        self.assertIn("build-aryaos-dragonegg-sdrmm-rx.sh", read(workflow))
        self.assertIn("actions/upload-artifact", read(workflow))

    def test_release_workflow_publishes_tagged_deb_assets(self):
        workflow = read(ROOT / ".github" / "workflows" / "aryaos-dragonegg-sdrmm-rx.yml")
        self.assertIn("'aryaos-rx-v*'", workflow)
        self.assertIn("release-package:", workflow)
        self.assertIn("contents: write", workflow)
        self.assertIn("startsWith(github.ref, 'refs/tags/aryaos-rx-v')", workflow)
        self.assertIn("actions/download-artifact", workflow)
        self.assertIn("gh release create", workflow)
        self.assertIn("dist/dragonegg-sdrmm-rx_0.1.0-3_arm64.deb", workflow)
        self.assertIn("dist/dragonegg-sdrmm-rx_0.1.0-3_SHA256SUMS", workflow)
        self.assertIn("dist/dragonegg-sdrmm-rx_0.1.0-3_BUILDINFO.txt", workflow)

    def test_arm64_runtime_command_selects_native_on_arm64(self):
        command = arm64_runtime_command("/pkg/opt/dragonegg-sdrmm/bin/sdrmm", "aarch64")
        self.assertEqual(command, ["/pkg/opt/dragonegg-sdrmm/bin/sdrmm", "--help"])

    def test_arm64_runtime_command_selects_qemu_on_x86_64(self):
        command = arm64_runtime_command("/pkg/opt/dragonegg-sdrmm/bin/sdrmm", "x86_64")
        self.assertEqual(command, ["qemu-aarch64", "-L", "/usr/aarch64-linux-gnu", "/pkg/opt/dragonegg-sdrmm/bin/sdrmm", "--help"])

    def test_source_license_and_provenance_are_declared(self):
        self.assertTrue((ROOT / "LICENSE").exists())
        runbook = read(PKG / "pkgroot" / "usr" / "share" / "doc" / "dragonegg-sdrmm-rx" / "RUNBOOK.md")
        self.assertIn("AGPL-3.0", runbook)
        self.assertIn("Newspicel/sdrminusminus", runbook)
        self.assertIn("snstac/sdrmm", runbook)
        self.assertIn("No live RF qualification", runbook)
        self.assertIn("network-client interim", runbook)

    def test_control_package_identity_and_arm64(self):
        control = read(PKG / "pkgroot" / "DEBIAN" / "control")
        self.assertIn("Package: dragonegg-sdrmm-rx", control)
        self.assertIn("Version: 0.1.0-3", control)
        self.assertIn("Architecture: arm64", control)
        self.assertNotIn("Package: sdrmm", control)

    def test_services_disabled_loopback_no_token_exact_lime_serial(self):
        cfg = read(PKG / "pkgroot" / "etc" / "dragonegg-sdrmm" / "dragonegg-sdrmm.conf")
        self.assertIn("RTL_TCP_BIND=127.0.0.1", cfg)
        self.assertIn("SDRMM_BIND=127.0.0.1", cfg)
        self.assertIn("TAILNET_EXPOSURE=disabled", cfg)
        self.assertNotRegex(cfg, r"(?i)token\s*=")

        ui = read(PKG / "pkgroot" / "usr" / "lib" / "systemd" / "system" / "dragonegg-sdrmm-ui.service")
        bridge = read(PKG / "pkgroot" / "usr" / "lib" / "systemd" / "system" / "dragonegg-rtltcp-bridge.service")
        self.assertIn("IPAddressAllow=localhost", ui)
        self.assertIn("IPAddressDeny=any", ui)
        self.assertIn("ExecStartPre=/usr/libexec/dragonegg-sdrmm/dragonegg-lime-gate --serial ${LIME_SERIAL}", bridge)
        self.assertIn("DeviceAllow=/dev/dragonegg-lime-rx rw", bridge)
        postinst = read(PKG / "pkgroot" / "DEBIAN" / "postinst")
        self.assertNotIn("systemctl enable", postinst)
        self.assertNotIn("systemctl start", postinst)
        rules = read(PKG / "pkgroot" / "etc" / "udev" / "rules.d" / "70-dragonegg-lime-rx.rules")
        self.assertIn('ATTRS{serial}=="1DBB426135F6EC"', rules)
        self.assertIn('SYMLINK+="dragonegg-lime-rx"', rules)

    def test_no_tx_or_generic_remote_paths_in_package_policy(self):
        policy_files = [
            PKG / "pkgroot" / "etc" / "dragonegg-sdrmm" / "dragonegg-sdrmm.conf",
            PKG / "pkgroot" / "usr" / "share" / "doc" / "dragonegg-sdrmm-rx" / "RUNBOOK.md",
            PKG / "pkgroot" / "usr" / "lib" / "systemd" / "system" / "dragonegg-rtltcp-bridge.service",
        ]
        combined = "\n".join(read(p) for p in policy_files)
        self.assertNotIn("SOAPY_SDR_TX", combined)
        self.assertNotIn("setBias", combined)
        self.assertNotIn("bias_tee_enabled = true", combined)

    def test_deb_modes_and_no_packaged_token_env(self):
        if not DEB.exists():
            subprocess.run([str(ROOT / "scripts" / "build-aryaos-dragonegg-sdrmm-rx.sh")], cwd=ROOT, check=True)
        contents = subprocess.run(["dpkg-deb", "--contents", str(DEB)], cwd=ROOT, check=True, text=True, capture_output=True).stdout
        self.assertNotIn("token.env", contents)
        bad = []
        for line in contents.splitlines():
            mode = line.split()[0]
            if len(mode) >= 9 and (mode[5] == "w" or mode[8] == "w"):
                bad.append(line)
        self.assertEqual(bad, [])
        self.assertIn("-rwxr-xr-x root/root", contents)
        self.assertIn("./usr/libexec/dragonegg-sdrmm/rx_only_rtltcp_bridge.py", contents)

    def test_extract_upgrade_remove_rollback_simulation_by_inspection(self):
        if not DEB.exists():
            subprocess.run([str(ROOT / "scripts" / "build-aryaos-dragonegg-sdrmm-rx.sh")], cwd=ROOT, check=True)
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td) / "root"
            ctrl = pathlib.Path(td) / "ctrl"
            subprocess.run(["dpkg-deb", "-x", str(DEB), str(root)], check=True)
            subprocess.run(["dpkg-deb", "-e", str(DEB), str(ctrl)], check=True)
            self.assertTrue((root / "opt" / "dragonegg-sdrmm" / "bin" / "sdrmm").exists())
            postinst = read(ctrl / "postinst")
            prerm = read(ctrl / "prerm")
            postrm = read(ctrl / "postrm")
            health = read(root / "usr" / "libexec" / "dragonegg-sdrmm" / "dragonegg-health")
            self.assertIn("if [ ! -f /etc/dragonegg-sdrmm/token.env ]", postinst)
            self.assertNotIn("systemctl start", postinst)
            self.assertNotIn("systemctl enable", postinst)
            self.assertIn("systemctl stop", prerm)
            self.assertIn("purge", postrm)
            self.assertIn("rollback", health)
            self.assertIn("disable --now", health)

    def test_bridge_fails_closed_for_nonloopback_without_admission(self):
        bridge = PKG / "rx_only_rtltcp_bridge.py"
        bad = subprocess.run([os.environ.get("PYTHON", "python3"), str(bridge), "--capabilities", "--bind", "0.0.0.0"], text=True, capture_output=True)
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn("wildcard", bad.stderr + bad.stdout)

    def test_deb_build_is_reproducible(self):
        subprocess.run([str(ROOT / "scripts" / "build-aryaos-dragonegg-sdrmm-rx.sh")], cwd=ROOT, check=True)
        first = subprocess.run(["sha256sum", str(DEB)], cwd=ROOT, check=True, text=True, capture_output=True).stdout.split()[0]
        subprocess.run([str(ROOT / "scripts" / "build-aryaos-dragonegg-sdrmm-rx.sh")], cwd=ROOT, check=True)
        second = subprocess.run(["sha256sum", str(DEB)], cwd=ROOT, check=True, text=True, capture_output=True).stdout.split()[0]
        self.assertEqual(first, second)
        subprocess.run(["sha256sum", "-c", str(DIST / "dragonegg-sdrmm-rx_0.1.0-3_SHA256SUMS")], cwd=ROOT, check=True)

    def test_deb_builds_and_arm64_binary_runs(self):
        subprocess.run([str(ROOT / "scripts" / "build-aryaos-dragonegg-sdrmm-rx.sh")], cwd=ROOT, check=True)
        self.assertTrue(DEB.exists())
        info = subprocess.run(["dpkg-deb", "--field", str(DEB), "Package", "Version", "Architecture"], cwd=ROOT, check=True, text=True, capture_output=True).stdout
        self.assertIn("dragonegg-sdrmm-rx", info)
        self.assertIn("0.1.0-3", info)
        self.assertIn("arm64", info)
        with tempfile.TemporaryDirectory() as td:
            extract = pathlib.Path(td) / "extract"
            subprocess.run(["dpkg-deb", "-x", str(DEB), str(extract)], check=True)
            binary = extract / "opt" / "dragonegg-sdrmm" / "bin" / "sdrmm"
            libdir = extract / "opt" / "dragonegg-sdrmm" / "lib"
            env = os.environ.copy()
            env["LD_LIBRARY_PATH"] = str(libdir)
            command = arm64_runtime_command(binary)
            if command[0] == "qemu-aarch64" and shutil.which("qemu-aarch64") is None:
                self.fail("qemu-aarch64 is required for x86_64 arm64 runtime proof")
            run = subprocess.run(command, text=True, capture_output=True, env=env)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn("Usage: sdrmm", run.stdout)


if __name__ == "__main__":
    unittest.main()
