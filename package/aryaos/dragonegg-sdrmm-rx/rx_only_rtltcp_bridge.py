#!/usr/bin/env python3
"""RX-only rtl_tcp-compatible source for SDR-- network-client evaluation.

The network protocol implemented here is the rtl_tcp TCP protocol that SDR--
accepts in its Network radio tab: 12-byte greeting `RTL0` + tuner code + gain
step count, followed by interleaved unsigned 8-bit I/Q bytes. Client commands
are five-byte frames: one command byte plus a big-endian uint32 parameter.

Safety boundary: this adapter exposes one RX stream and no TX or bias-control
capability. The default bind address is loopback. The default synthetic source
lets tests and SDR-- handshakes run offline without opening any radio.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import math
import signal
import socket
import struct
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

GMRS_INITIAL_FREQUENCY_HZ = 462_562_500
GMRS_MIN_FREQUENCY_HZ = 462_000_000
GMRS_MAX_FREQUENCY_HZ = 468_000_000
GMRS_SAMPLE_RATE_HZ = 250_000
GMRS_MIN_GAIN_TENTHS_DB = 0
GMRS_MAX_GAIN_TENTHS_DB = 496
GMRS_DEFAULT_GAIN_TENTHS_DB = GMRS_MIN_GAIN_TENTHS_DB
LIME_SERIAL = "1DBB426135F6EC"
LIME_SELECTOR = f"driver=lime,serial={LIME_SERIAL}"
LIME_RX_CHANNEL = 0
LIME_SUPPORTED_RX_ANTENNAS = ["LNAH", "LNAW"]
# Bounded readback tolerance for observed Lime/Soapy synthesizer quantization.
# Field requests 462476703 Hz and 462377580 Hz read back 1.26355 Hz and
# 3.1719971 Hz lower, respectively. Ten Hz is below one-thousandth of a
# 12.5 kHz channel while rejecting materially wrong tune readbacks; it does
# not widen the GMRS command window enforced by ControlPolicy/RuntimeConfig.
LIME_FREQUENCY_READBACK_TOLERANCE_HZ = 10.0
NON_LOOPBACK_ADMISSION_TOKEN = f"gmrs-rx-on-unit-{LIME_SERIAL}"
DISALLOWED_BROAD_BINDS = {"", "0.0.0.0", "::"}
APPROVED_NON_LOOPBACK_BINDS: tuple[str, ...] = ()
LIMESUITE_STARTUP_CAVEAT = (
    "LimeSuite initialization may enable or calibrate TX circuitry even when an "
    "application requests RX only; this bridge never requests a TX channel, TX stream, or bias control."
)

RTL_TCP_MAGIC = b"RTL0"
RTL_TCP_GREETING_LEN = 12
COMMAND_LEN = 5
TUNER_R820T = 5
R820T_GAIN_TABLE_TENTHS_DB = [
    0, 9, 14, 27, 37, 77, 87, 125, 144, 157, 166, 197, 207, 229, 254,
    280, 297, 328, 338, 364, 372, 386, 402, 421, 434, 439, 445, 480, 496,
]

CMD_CENTER_FREQ = 0x01
CMD_SAMPLE_RATE = 0x02
CMD_GAIN_MODE = 0x03
CMD_GAIN = 0x04
CMD_FREQ_CORRECTION = 0x05
CMD_RTL_AGC = 0x08
CMD_BIAS_TEE = 0x0E

SUPPORTED_COMMANDS = {
    CMD_CENTER_FREQ: "center_frequency_hz",
    CMD_SAMPLE_RATE: "sample_rate_hz",
    CMD_GAIN_MODE: "gain_mode",
    CMD_GAIN: "gain_tenths_db",
    CMD_FREQ_CORRECTION: "ppm",
    CMD_RTL_AGC: "rtl_agc",
    CMD_BIAS_TEE: "bias_tee",
}


@dataclass
class RuntimeConfig:
    bind: str = "127.0.0.1"
    port: int = 1234
    source: str = "synthetic"
    selector: str = LIME_SELECTOR
    channel: int = LIME_RX_CHANNEL
    antenna: str = "LNAH"
    min_frequency_hz: int = GMRS_MIN_FREQUENCY_HZ
    max_frequency_hz: int = GMRS_MAX_FREQUENCY_HZ
    default_frequency_hz: int = GMRS_INITIAL_FREQUENCY_HZ
    min_sample_rate_hz: int = GMRS_SAMPLE_RATE_HZ
    default_sample_rate_hz: int = GMRS_SAMPLE_RATE_HZ
    max_sample_rate_hz: int = GMRS_SAMPLE_RATE_HZ
    min_gain_tenths_db: int = GMRS_MIN_GAIN_TENTHS_DB
    max_gain_tenths_db: int = GMRS_MAX_GAIN_TENTHS_DB
    gain_tenths_db: int = GMRS_DEFAULT_GAIN_TENTHS_DB
    ppm: int = 0
    chunk_samples: int = 1024
    send_timeout_s: float = 1.0
    metrics_path: str = "rtltcp-bridge-metrics.json"
    duration_s: float = 0.0
    allow_non_loopback: bool = False
    admission_token: str = ""

    def __post_init__(self) -> None:
        if self.selector != LIME_SELECTOR:
            raise SystemExit(f"selector must be exact {LIME_SELECTOR!r}")
        if int(self.channel) != LIME_RX_CHANNEL:
            raise SystemExit("only Lime RX channel 0 is admitted")
        if self.antenna not in LIME_SUPPORTED_RX_ANTENNAS:
            raise SystemExit(f"antenna must be one of {LIME_SUPPORTED_RX_ANTENNAS}")
        expected = {
            "min_frequency_hz": GMRS_MIN_FREQUENCY_HZ,
            "max_frequency_hz": GMRS_MAX_FREQUENCY_HZ,
            "default_frequency_hz": GMRS_INITIAL_FREQUENCY_HZ,
            "min_sample_rate_hz": GMRS_SAMPLE_RATE_HZ,
            "default_sample_rate_hz": GMRS_SAMPLE_RATE_HZ,
            "max_sample_rate_hz": GMRS_SAMPLE_RATE_HZ,
            "min_gain_tenths_db": GMRS_MIN_GAIN_TENTHS_DB,
            "max_gain_tenths_db": GMRS_MAX_GAIN_TENTHS_DB,
            "gain_tenths_db": GMRS_DEFAULT_GAIN_TENTHS_DB,
        }
        for field_name, expected_value in expected.items():
            actual_value = int(getattr(self, field_name))
            if actual_value != expected_value:
                raise SystemExit(
                    f"{field_name} must remain {expected_value}; unsafe GMRS RX admission override {actual_value} rejected"
                )
        if self.bind in DISALLOWED_BROAD_BINDS:
            raise SystemExit("wildcard or empty bind is not admitted for GMRS RX bridge")
        if not is_loopback_bind(self.bind):
            if not self.allow_non_loopback or self.admission_token != NON_LOOPBACK_ADMISSION_TOKEN:
                raise SystemExit("non-loopback bind requires exact narrow on-unit admission token")
            if self.bind not in APPROVED_NON_LOOPBACK_BINDS:
                raise SystemExit("non-loopback bind is not in the approved on-unit allowlist")


@dataclass
class DeviceState:
    center_frequency_hz: int = GMRS_INITIAL_FREQUENCY_HZ
    sample_rate_hz: int = GMRS_SAMPLE_RATE_HZ
    gain_tenths_db: int = 0
    gain_mode_manual: bool = True
    ppm: int = 0
    rtl_agc: bool = False
    bias_tee: bool = False


def is_loopback_bind(bind: str) -> bool:
    if bind == "localhost":
        return True
    try:
        return ipaddress.ip_address(bind).is_loopback
    except ValueError:
        return False


@dataclass
class CommandResult:
    command: str
    value: int
    status: str
    message: str = ""


@dataclass
class Metrics:
    protocol: str = "rtl_tcp"
    sample_encoding: str = "cu8_iq_interleaved"
    rx_streams: int = 1
    tx_streams: int = 0
    bind: str = "127.0.0.1"
    port: int = 0
    started_utc: str = ""
    ended_utc: str = ""
    connections_accepted: int = 0
    bytes_streamed: int = 0
    samples_streamed: int = 0
    command_results: list[dict[str, object]] = field(default_factory=list)
    disconnect_reasons: list[str] = field(default_factory=list)
    bias_tee_enabled: bool = False
    complete: bool = False
    stop_reason: str = "running"


class ControlPolicy:
    """Accept only RX-safe rtl_tcp controls and keep them within bounds."""

    def __init__(
        self,
        *,
        max_sample_rate_hz: int = GMRS_SAMPLE_RATE_HZ,
        min_sample_rate_hz: int = GMRS_SAMPLE_RATE_HZ,
        min_frequency_hz: int = GMRS_MIN_FREQUENCY_HZ,
        max_frequency_hz: int = GMRS_MAX_FREQUENCY_HZ,
        min_gain_tenths_db: int = GMRS_MIN_GAIN_TENTHS_DB,
        max_gain_tenths_db: int = GMRS_MAX_GAIN_TENTHS_DB,
        max_abs_ppm: int = 200,
    ) -> None:
        self.max_sample_rate_hz = int(max_sample_rate_hz)
        self.min_sample_rate_hz = int(min_sample_rate_hz)
        self.min_frequency_hz = int(min_frequency_hz)
        self.max_frequency_hz = int(max_frequency_hz)
        self.min_gain_tenths_db = int(min_gain_tenths_db)
        self.max_gain_tenths_db = int(max_gain_tenths_db)
        self.max_abs_ppm = int(max_abs_ppm)

    def apply_frame(self, frame: bytes, state: DeviceState) -> CommandResult:
        if len(frame) != COMMAND_LEN:
            return CommandResult("short_frame", 0, "ignored", f"bad length {len(frame)}")
        cmd = frame[0]
        value = int.from_bytes(frame[1:5], "big", signed=False)
        name = SUPPORTED_COMMANDS.get(cmd, f"unknown_0x{cmd:02x}")

        if cmd == CMD_SAMPLE_RATE:
            if self.min_sample_rate_hz <= value <= self.max_sample_rate_hz:
                state.sample_rate_hz = value
                return CommandResult(name, value, "accepted")
            return CommandResult(
                name, value, "rejected",
                f"sample_rate_hz must be {self.min_sample_rate_hz}..{self.max_sample_rate_hz}",
            )
        if cmd == CMD_CENTER_FREQ:
            if self.min_frequency_hz <= value <= self.max_frequency_hz:
                state.center_frequency_hz = value
                return CommandResult(name, value, "accepted")
            return CommandResult(
                name, value, "rejected",
                f"center_frequency_hz must be {self.min_frequency_hz}..{self.max_frequency_hz}",
            )
        if cmd == CMD_GAIN_MODE:
            state.gain_mode_manual = bool(value)
            return CommandResult(name, value, "accepted")
        if cmd == CMD_GAIN:
            clamped = min(max(value, self.min_gain_tenths_db), self.max_gain_tenths_db)
            state.gain_tenths_db = int(clamped)
            return CommandResult(name, value, "accepted" if clamped == value else "clamped")
        if cmd == CMD_FREQ_CORRECTION:
            signed = struct.unpack("!i", frame[1:5])[0]
            if -self.max_abs_ppm <= signed <= self.max_abs_ppm:
                state.ppm = signed
                return CommandResult(name, signed, "accepted")
            return CommandResult(name, signed, "rejected", f"ppm must be +/-{self.max_abs_ppm}")
        if cmd == CMD_RTL_AGC:
            state.rtl_agc = bool(value)
            return CommandResult(name, value, "accepted")
        if cmd == CMD_BIAS_TEE:
            if value == 0:
                state.bias_tee = False
                return CommandResult(name, value, "accepted")
            state.bias_tee = False
            return CommandResult(name, value, "rejected", "bias tee is forced off")
        return CommandResult(name, value, "ignored", "unsupported rtl_tcp command")


def rtl_tcp_greeting(tuner_code: int = TUNER_R820T, gain_steps: int = len(R820T_GAIN_TABLE_TENTHS_DB)) -> bytes:
    return RTL_TCP_MAGIC + int(tuner_code).to_bytes(4, "big") + int(gain_steps).to_bytes(4, "big")


def capabilities(cfg: RuntimeConfig) -> dict[str, object]:
    return {
        "schema": "rx-only-rtltcp-bridge-capabilities-v1",
        "protocol": "rtl_tcp",
        "sdrmm_network_radio": True,
        "sample_encoding": "cu8_iq_interleaved",
        "framing": "12-byte RTL0 greeting, then raw unsigned 8-bit I/Q; client controls are 5-byte rtl_tcp command frames",
        "rx_streams": 1,
        "tx_streams": 0,
        "bias_tee_enabled": False,
        "bias_tee_policy": "client bias-tee on requests are rejected and never forwarded",
        "default_bind": "127.0.0.1",
        "bind": cfg.bind,
        "max_sample_rate_hz": cfg.max_sample_rate_hz,
        "min_sample_rate_hz": cfg.min_sample_rate_hz,
        "default_sample_rate_hz": cfg.default_sample_rate_hz,
        "frequency_range_hz": [cfg.min_frequency_hz, cfg.max_frequency_hz],
        "default_frequency_hz": cfg.default_frequency_hz,
        "frequency_readback_tolerance_hz": LIME_FREQUENCY_READBACK_TOLERANCE_HZ,
        "frequency_readback_tolerance_basis": "bounded 10 Hz maximum for observed Lime/Soapy quantization; 462476703 -> 462476701.7364502 Hz and 462377580 -> 462377576.8280029 Hz; GMRS command window unchanged",
        "gain_range_tenths_db": [cfg.min_gain_tenths_db, cfg.max_gain_tenths_db],
        "default_gain_tenths_db": cfg.gain_tenths_db,
        "selector": cfg.selector,
        "channel": cfg.channel,
        "antenna": cfg.antenna,
        "lime_supported_rx_antennas": LIME_SUPPORTED_RX_ANTENNAS,
        "limesuite_startup_caveat": LIMESUITE_STARTUP_CAVEAT,
        "source": cfg.source,
    }


def cs16_iq_to_cu8(values: Sequence[int]) -> bytes:
    out = bytearray()
    for value in values:
        clipped = min(32767, max(-32768, int(value)))
        out.append(int(round((clipped + 32768) * 255 / 65535)))
    return bytes(out)


class SyntheticSource:
    def __init__(self) -> None:
        self.phase = 0.0

    def configure(self, _state: DeviceState) -> None:
        return

    def read_cu8(self, samples: int, state: DeviceState) -> bytes:
        # Low-amplitude deterministic tone. Byte samples are I,Q pairs centered at 128.
        out = bytearray(samples * 2)
        step = 2.0 * math.pi * 1000.0 / max(state.sample_rate_hz, 1)
        for idx in range(samples):
            i = 128 + int(48 * math.sin(self.phase))
            q = 128 + int(48 * math.cos(self.phase))
            out[2 * idx] = i & 0xFF
            out[2 * idx + 1] = q & 0xFF
            self.phase = (self.phase + step) % (2.0 * math.pi)
        return bytes(out)

    def close(self) -> None:
        return


class SoapyRxSource:
    """Optional DragonEgg RX path; constructed only when explicitly requested."""

    def __init__(self, cfg: RuntimeConfig, state: DeviceState, soapy=None) -> None:
        if soapy is None:
            try:
                import SoapySDR  # type: ignore
            except Exception as exc:  # pragma: no cover - target dependent
                raise SystemExit(f"SoapySDR import failed: {exc}") from exc
            soapy = SoapySDR
        self.soapy = soapy
        self.dev = None
        self.stream = None
        self.activated = False
        self.actual: dict[str, int | str] = {}
        try:
            self.dev = soapy.Device(cfg.selector)
            self.rx_dir = soapy.SOAPY_SDR_RX
            self.chan = int(cfg.channel)
            antennas = list(self.dev.listAntennas(self.rx_dir, self.chan)) if hasattr(self.dev, "listAntennas") else LIME_SUPPORTED_RX_ANTENNAS
            if cfg.antenna not in antennas:
                raise SystemExit(f"requested antenna {cfg.antenna!r} not supported by device: {antennas!r}")
            self.dev.setAntenna(self.rx_dir, self.chan, cfg.antenna)
            actual_antenna = self.dev.getAntenna(self.rx_dir, self.chan) if hasattr(self.dev, "getAntenna") else cfg.antenna
            if actual_antenna != cfg.antenna:
                raise SystemExit(f"antenna readback mismatch: requested {cfg.antenna!r}, actual {actual_antenna!r}")
            self.configure(state)
            self.stream = self.dev.setupStream(self.rx_dir, soapy.SOAPY_SDR_CS16, [self.chan])
            self.dev.activateStream(self.stream)
            self.activated = True
        except BaseException:
            self._cleanup_partial()
            raise

    def _cleanup_partial(self) -> None:
        if self.dev is None:
            return
        if self.stream is not None:
            try:
                if self.activated:
                    self.dev.deactivateStream(self.stream)
            finally:
                self.dev.closeStream(self.stream)
        elif hasattr(self.dev, "close"):
            self.dev.close()

    def _check_float(self, name: str, requested: float, actual: float, tolerance: float) -> None:
        if abs(float(actual) - float(requested)) > tolerance:
            raise SystemExit(f"{name} readback mismatch: requested {requested}, actual {actual}")

    def configure(self, state: DeviceState) -> None:
        assert self.dev is not None
        self.dev.setSampleRate(self.rx_dir, self.chan, float(state.sample_rate_hz))
        actual_rate = float(self.dev.getSampleRate(self.rx_dir, self.chan)) if hasattr(self.dev, "getSampleRate") else float(state.sample_rate_hz)
        self._check_float("sample_rate_hz", float(state.sample_rate_hz), actual_rate, 1.0)

        self.dev.setFrequency(self.rx_dir, self.chan, float(state.center_frequency_hz))
        actual_freq = float(self.dev.getFrequency(self.rx_dir, self.chan)) if hasattr(self.dev, "getFrequency") else float(state.center_frequency_hz)
        self._check_float("center_frequency_hz", float(state.center_frequency_hz), actual_freq, LIME_FREQUENCY_READBACK_TOLERANCE_HZ)

        requested_gain = float(state.gain_tenths_db) / 10.0
        self.dev.setGain(self.rx_dir, self.chan, requested_gain)
        actual_gain = float(self.dev.getGain(self.rx_dir, self.chan)) if hasattr(self.dev, "getGain") else requested_gain
        self._check_float("gain_db", requested_gain, actual_gain, 0.1)
        self.actual = {
            "antenna": self.dev.getAntenna(self.rx_dir, self.chan) if hasattr(self.dev, "getAntenna") else "",
            "frequency_hz": int(round(actual_freq)),
            "sample_rate_hz": int(round(actual_rate)),
            "gain_tenths_db": int(round(actual_gain * 10.0)),
        }

    def read_cu8(self, samples: int, _state: DeviceState) -> bytes:
        try:
            import numpy as np  # type: ignore
        except Exception as exc:  # pragma: no cover - target dependent
            raise SystemExit(f"numpy import failed: {exc}") from exc
        buff = np.empty(samples * 2, dtype=np.int16)
        sr = self.dev.readStream(self.stream, [buff], samples, timeoutUs=250_000)
        ret = int(getattr(sr, "ret", sr[0] if isinstance(sr, tuple) else sr))
        if ret <= 0:
            return b""
        return cs16_iq_to_cu8([int(x) for x in buff[: ret * 2]])

    def close(self) -> None:
        if self.dev is None or self.stream is None:
            return
        try:
            if self.activated:
                self.dev.deactivateStream(self.stream)
        finally:
            self.dev.closeStream(self.stream)
            self.activated = False


class RtlTcpBridge:
    def __init__(self, cfg: RuntimeConfig) -> None:
        self.cfg = cfg
        self.policy = ControlPolicy(
            max_sample_rate_hz=cfg.max_sample_rate_hz,
            min_sample_rate_hz=cfg.min_sample_rate_hz,
            min_frequency_hz=cfg.min_frequency_hz,
            max_frequency_hz=cfg.max_frequency_hz,
            min_gain_tenths_db=cfg.min_gain_tenths_db,
            max_gain_tenths_db=cfg.max_gain_tenths_db,
        )
        self.state = DeviceState(
            center_frequency_hz=cfg.default_frequency_hz,
            sample_rate_hz=cfg.default_sample_rate_hz,
            gain_tenths_db=cfg.gain_tenths_db,
            ppm=cfg.ppm,
        )
        self.metrics = Metrics(bind=cfg.bind, port=cfg.port, started_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        self._stop = threading.Event()
        self.ready = threading.Event()
        self.bound_port = cfg.port
        self._server_sock: socket.socket | None = None
        self._active_conns: set[socket.socket] = set()

    def _make_source(self):
        if self.cfg.source == "synthetic":
            return SyntheticSource()
        if self.cfg.source == "soapy-rx":
            return SoapyRxSource(self.cfg, self.state)
        raise SystemExit(f"unknown source {self.cfg.source!r}")

    def stop(self, reason: str = "stopped") -> None:
        if self.metrics.stop_reason == "running":
            self.metrics.stop_reason = reason
        self._stop.set()
        if self._server_sock is not None:
            try:
                self._server_sock.close()
            except OSError:
                pass
        for conn in list(self._active_conns):
            try:
                conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                conn.close()
            except OSError:
                pass

    def serve_forever(self) -> None:
        deadline = time.monotonic() + self.cfg.duration_s if self.cfg.duration_s > 0 else None
        Path(self.cfg.metrics_path).parent.mkdir(parents=True, exist_ok=True)
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
                self._server_sock = srv
                srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                srv.bind((self.cfg.bind, self.cfg.port))
                srv.listen(1)
                srv.settimeout(0.2)
                self.bound_port = int(srv.getsockname()[1])
                self.metrics.port = self.bound_port
                self.ready.set()
                while not self._stop.is_set():
                    if deadline is not None and time.monotonic() >= deadline:
                        self.metrics.stop_reason = "duration_elapsed"
                        break
                    try:
                        conn, addr = srv.accept()
                    except socket.timeout:
                        continue
                    except OSError:
                        break
                    self.metrics.connections_accepted += 1
                    self._handle_client(conn, addr, deadline=deadline)
        finally:
            self._server_sock = None
            if self.metrics.stop_reason == "running":
                self.metrics.stop_reason = "stopped" if self._stop.is_set() else "listener_closed"
            self.metrics.complete = self.metrics.stop_reason == "duration_elapsed"
            self.metrics.ended_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            self._write_metrics()

    def _write_metrics(self) -> None:
        data = asdict(self.metrics)
        data.update(asdict(self.state))
        Path(self.cfg.metrics_path).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _handle_client(self, conn: socket.socket, _addr: tuple[str, int], *, deadline: float | None = None) -> None:
        self._active_conns.add(conn)
        source = self._make_source()
        try:
            conn.settimeout(self.cfg.send_timeout_s)
            conn.sendall(rtl_tcp_greeting())
            reader = conn.makefile("rb", buffering=0)
            last_pace = time.monotonic()
            while not self._stop.is_set():
                if deadline is not None and time.monotonic() >= deadline:
                    self.metrics.stop_reason = "duration_elapsed"
                    self.metrics.disconnect_reasons.append("duration_elapsed")
                    break
                # Non-blocking-ish command drain; streaming continues when no command is pending.
                conn.settimeout(0.0)
                try:
                    frame = reader.read(COMMAND_LEN)
                except (BlockingIOError, socket.timeout):
                    frame = None
                except (ConnectionResetError, OSError) as exc:
                    self.metrics.disconnect_reasons.append(f"command_read_failed:{exc.__class__.__name__}")
                    break
                finally:
                    conn.settimeout(self.cfg.send_timeout_s)
                if frame:
                    if len(frame) == COMMAND_LEN:
                        result = self.policy.apply_frame(frame, self.state)
                        self.metrics.command_results.append(asdict(result))
                        if result.status in {"accepted", "clamped"}:
                            source.configure(self.state)
                    else:
                        self.metrics.disconnect_reasons.append("short_command_frame")
                        break
                data = source.read_cu8(self.cfg.chunk_samples, self.state)
                if not data:
                    continue
                try:
                    conn.sendall(data)
                except (socket.timeout, OSError) as exc:
                    self.metrics.disconnect_reasons.append(f"send_failed:{exc.__class__.__name__}")
                    break
                self.metrics.bytes_streamed += len(data)
                self.metrics.samples_streamed += len(data) // 2
                # Pace synthetic mode to the configured sample rate and avoid busy-looping.
                if self.cfg.source == "synthetic":
                    expected = self.cfg.chunk_samples / max(self.state.sample_rate_hz, 1)
                    now = time.monotonic()
                    sleep_for = expected - (now - last_pace)
                    if sleep_for > 0:
                        time.sleep(min(sleep_for, 0.05))
                    last_pace = time.monotonic()
        finally:
            self.metrics.bias_tee_enabled = self.state.bias_tee
            source.close()
            try:
                conn.close()
            except OSError:
                pass
            self._active_conns.discard(conn)
            self._write_metrics()


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="RX-only rtl_tcp-compatible source for SDR--")
    p.add_argument("--bind", default="127.0.0.1")
    p.add_argument("--port", type=int, default=1234)
    p.add_argument("--source", choices=("synthetic", "soapy-rx"), default="synthetic")
    p.add_argument("--selector", default=LIME_SELECTOR)
    p.add_argument("--channel", type=int, default=LIME_RX_CHANNEL)
    p.add_argument("--antenna", default="LNAH")
    p.add_argument("--frequency-hz", type=int, default=GMRS_INITIAL_FREQUENCY_HZ)
    p.add_argument("--min-frequency-hz", type=int, default=GMRS_MIN_FREQUENCY_HZ)
    p.add_argument("--max-frequency-hz", type=int, default=GMRS_MAX_FREQUENCY_HZ)
    p.add_argument("--sample-rate-hz", type=int, default=GMRS_SAMPLE_RATE_HZ)
    p.add_argument("--min-sample-rate-hz", type=int, default=GMRS_SAMPLE_RATE_HZ)
    p.add_argument("--max-sample-rate-hz", type=int, default=GMRS_SAMPLE_RATE_HZ)
    p.add_argument("--gain-tenths-db", type=int, default=0)
    p.add_argument("--min-gain-tenths-db", type=int, default=0)
    p.add_argument("--max-gain-tenths-db", type=int, default=496)
    p.add_argument("--allow-non-loopback", action="store_true")
    p.add_argument("--admission-token", default="")
    p.add_argument("--duration-s", type=float, default=0.0)
    p.add_argument("--metrics-path", default="rtltcp-bridge-metrics.json")
    p.add_argument("--capabilities", action="store_true")
    return p.parse_args(list(argv))


def main(argv: Iterable[str] = sys.argv[1:]) -> int:
    ns = parse_args(argv)
    cfg = RuntimeConfig(
        bind=ns.bind,
        port=ns.port,
        source=ns.source,
        selector=ns.selector,
        channel=ns.channel,
        antenna=ns.antenna,
        min_frequency_hz=ns.min_frequency_hz,
        max_frequency_hz=ns.max_frequency_hz,
        default_frequency_hz=ns.frequency_hz,
        min_sample_rate_hz=ns.min_sample_rate_hz,
        default_sample_rate_hz=ns.sample_rate_hz,
        max_sample_rate_hz=ns.max_sample_rate_hz,
        min_gain_tenths_db=ns.min_gain_tenths_db,
        max_gain_tenths_db=ns.max_gain_tenths_db,
        gain_tenths_db=ns.gain_tenths_db,
        duration_s=ns.duration_s,
        metrics_path=ns.metrics_path,
        allow_non_loopback=ns.allow_non_loopback,
        admission_token=ns.admission_token,
    )
    if ns.capabilities:
        print(json.dumps(capabilities(cfg), indent=2, sort_keys=True))
        return 0
    bridge = RtlTcpBridge(cfg)
    previous_handlers = {}

    def _request_stop(signum, _frame):
        signame = signal.Signals(signum).name
        bridge.stop(f"signal:{signame}")

    for sig in (signal.SIGTERM, signal.SIGINT):
        previous_handlers[sig] = signal.getsignal(sig)
        signal.signal(sig, _request_stop)
    try:
        bridge.serve_forever()
    finally:
        for sig, handler in previous_handlers.items():
            signal.signal(sig, handler)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
