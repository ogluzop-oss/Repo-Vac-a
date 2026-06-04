"""
Scale Service — Smart Manager AI TPV Enterprise
Abstracts physical scale communication (serial/USB) with a clean interface.
Falls back to manual entry mode when no scale is detected.

Supported protocols:
  - Generic serial scale via COM port (configurable baud rate)
  - Simulated scale for testing / environments without hardware

To add a real scale: implement ScaleDriver for the specific protocol
(Toledo, Ohaus, Mettler, etc.) and register it in detect_scale().
"""
from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

logger = logging.getLogger("tpv.scale")


# ─── Abstract base ─────────────────────────────────────────────────────────────

class ScaleDriver:
    """Abstract scale interface. Override read_weight() for real hardware."""

    def connect(self) -> bool:
        return False

    def disconnect(self):
        pass

    def read_weight(self) -> float | None:
        """Returns weight in kg, or None if not ready / stable."""
        return None

    def tare(self) -> bool:
        """Send tare command. Returns True if acknowledged."""
        return False

    @property
    def connected(self) -> bool:
        return False

    @property
    def mode(self) -> str:
        return "disconnected"


# ─── Serial scale driver ───────────────────────────────────────────────────────

class SerialScaleDriver(ScaleDriver):
    """
    Generic RS-232 / USB-serial scale.
    Most scales output a continuous stream of ASCII weight readings.
    Format example (Toledo/Mettler):  ST,GS,+  1.234 kg
    """

    def __init__(self, port: str = "COM1", baud: int = 9600,
                 timeout: float = 0.5):
        self._port    = port
        self._baud    = baud
        self._timeout = timeout
        self._serial  = None
        self._weight  = None
        self._lock    = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None

    def connect(self) -> bool:
        try:
            import serial
            self._serial = serial.Serial(
                self._port, self._baud, timeout=self._timeout
            )
            self._running = True
            self._thread = threading.Thread(
                target=self._read_loop, daemon=True, name="ScaleReader"
            )
            self._thread.start()
            logger.info(f"Scale connected on {self._port} @ {self._baud} baud.")
            return True
        except Exception as e:
            logger.warning(f"Scale connect failed: {e}")
            return False

    def disconnect(self):
        self._running = False
        if self._serial:
            try:
                self._serial.close()
            except Exception:
                pass
            self._serial = None

    def _read_loop(self):
        while self._running and self._serial:
            try:
                line = self._serial.readline().decode("ascii", errors="ignore").strip()
                weight = self._parse_line(line)
                with self._lock:
                    self._weight = weight
            except Exception:
                time.sleep(0.1)

    @staticmethod
    def _parse_line(line: str) -> float | None:
        """
        Parse generic scale output. Tries to extract the last float in the line.
        Works for most "ST,GS,±  x.xxx kg" formats.
        """
        import re
        m = re.search(r"[-+]?\s*(\d+[.,]\d+)", line)
        if m:
            try:
                return float(m.group(1).replace(",", "."))
            except ValueError:
                pass
        return None

    def read_weight(self) -> float | None:
        with self._lock:
            return self._weight

    def tare(self) -> bool:
        if not self._serial:
            return False
        try:
            self._serial.write(b"T\r\n")  # Standard tare command
            return True
        except Exception:
            return False

    @property
    def connected(self) -> bool:
        return self._serial is not None and self._serial.is_open

    @property
    def mode(self) -> str:
        return "serial"


# ─── Simulated scale (development / no hardware) ──────────────────────────────

class SimulatedScaleDriver(ScaleDriver):
    """
    Simulated scale for testing and environments without hardware.
    Returns None — forces the UI to use manual weight entry.
    """

    @property
    def connected(self) -> bool:
        return True   # always "available" in simulated mode

    @property
    def mode(self) -> str:
        return "manual"

    def read_weight(self) -> float | None:
        return None   # no auto-reading; operator enters weight manually

    def tare(self) -> bool:
        return True


# ─── Scale manager (singleton-per-session) ────────────────────────────────────

class ScaleManager:
    """
    Manages scale lifecycle.
    Attempts to find a real serial scale; falls back to simulated.
    """

    def __init__(self):
        self._driver: ScaleDriver = SimulatedScaleDriver()
        self._callbacks: list[Callable[[float | None], None]] = []
        self._poll_thread: threading.Thread | None = None
        self._polling = False

    def detect_and_connect(self, port: str = "COM1", baud: int = 9600) -> str:
        """
        Try to connect to a real scale on <port>.
        Returns mode string: 'serial' | 'manual'
        """
        driver = SerialScaleDriver(port, baud)
        if driver.connect():
            self._driver = driver
            logger.info(f"Hardware scale detected: {driver.mode}")
        else:
            self._driver = SimulatedScaleDriver()
            logger.info("No hardware scale found — using manual entry mode.")
        return self._driver.mode

    def read_weight(self) -> float | None:
        return self._driver.read_weight()

    def tare(self) -> bool:
        return self._driver.tare()

    @property
    def mode(self) -> str:
        return self._driver.mode

    @property
    def has_hardware(self) -> bool:
        return self._driver.mode == "serial"

    def disconnect(self):
        self._polling = False
        self._driver.disconnect()

    def start_polling(self, callback: Callable[[float | None], None],
                      interval_ms: int = 300):
        """
        Start a background thread that calls callback(weight) every interval_ms.
        Used to update the scale UI in real time.
        """
        self._callbacks.append(callback)
        if not self._polling:
            self._polling = True
            self._poll_thread = threading.Thread(
                target=self._poll_loop,
                args=(interval_ms / 1000,),
                daemon=True,
                name="ScalePoll",
            )
            self._poll_thread.start()

    def _poll_loop(self, interval: float):
        while self._polling:
            w = self._driver.read_weight()
            for cb in self._callbacks:
                try:
                    cb(w)
                except Exception:
                    pass
            time.sleep(interval)

    def stop_polling(self):
        self._polling = False
        self._callbacks.clear()


# ─── Module-level singleton ───────────────────────────────────────────────────
_scale_manager: ScaleManager | None = None


def get_scale_manager() -> ScaleManager:
    global _scale_manager
    if _scale_manager is None:
        _scale_manager = ScaleManager()
    return _scale_manager
