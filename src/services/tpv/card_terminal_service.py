"""
Card Terminal Service — Smart Manager AI TPV Enterprise
Abstracts the payment dataphone (datáfono) for charges and refunds.

Real integrations (Redsys, Stripe Terminal, Ingenico, Verifone) would
implement CardTerminalDriver. Until hardware is wired, SimulatedTerminal
returns successful confirmations so the UX flow can be fully exercised.
"""
from __future__ import annotations

import logging
import time

logger = logging.getLogger("tpv.terminal")


class CardTerminalResult:
    """Result of a terminal operation."""
    def __init__(self, ok: bool, mensaje: str,
                 ultimos_digitos: str = "", referencia: str = ""):
        self.ok = ok
        self.mensaje = mensaje
        self.ultimos_digitos = ultimos_digitos   # last 4 digits of the card
        self.referencia = referencia             # bank authorization code


class CardTerminalDriver:
    """Abstract dataphone interface."""

    def cobrar(self, importe: float) -> CardTerminalResult:
        raise NotImplementedError

    def devolver(self, importe: float,
                 ultimos_digitos: str = "") -> CardTerminalResult:
        raise NotImplementedError

    @property
    def conectado(self) -> bool:
        return False


class SimulatedTerminal(CardTerminalDriver):
    """
    Simulated dataphone. Always confirms after a short delay.
    Generates a fake authorization code and card tail for traceability.
    """

    @property
    def conectado(self) -> bool:
        return True

    def cobrar(self, importe: float) -> CardTerminalResult:
        if importe <= 0:
            return CardTerminalResult(False, "Importe inválido.")
        time.sleep(0.4)  # simulate card processing
        import random
        tail = f"{random.randint(0, 9999):04d}"
        ref  = f"AUT{random.randint(100000, 999999)}"
        logger.info(f"[SIM] Cobro tarjeta {importe:.2f}€ OK ref={ref} ****{tail}")
        return CardTerminalResult(
            True, f"Pago aprobado: {importe:.2f} €", tail, ref
        )

    def devolver(self, importe: float,
                 ultimos_digitos: str = "") -> CardTerminalResult:
        if importe <= 0:
            return CardTerminalResult(False, "Importe inválido.")
        time.sleep(0.4)
        import random
        tail = ultimos_digitos or f"{random.randint(0, 9999):04d}"
        ref  = f"DEV{random.randint(100000, 999999)}"
        logger.info(f"[SIM] Devolución tarjeta {importe:.2f}€ OK ref={ref} ****{tail}")
        return CardTerminalResult(
            True, f"Devolución aprobada: {importe:.2f} €", tail, ref
        )


# ─── Manager (singleton) ───────────────────────────────────────────────────────

class TerminalManager:
    def __init__(self):
        self._driver: CardTerminalDriver = SimulatedTerminal()

    @property
    def conectado(self) -> bool:
        return self._driver.conectado

    def cobrar(self, importe: float) -> CardTerminalResult:
        return self._driver.cobrar(importe)

    def devolver(self, importe: float,
                 ultimos_digitos: str = "") -> CardTerminalResult:
        """Send a negative amount to the dataphone (refund flow)."""
        return self._driver.devolver(importe, ultimos_digitos)


_terminal: TerminalManager | None = None


def get_terminal() -> TerminalManager:
    global _terminal
    if _terminal is None:
        _terminal = TerminalManager()
    return _terminal
