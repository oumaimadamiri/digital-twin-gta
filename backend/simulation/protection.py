"""
simulation/protection.py — Couche de protections automatiques du GTA

Architecture industrielle : 3 niveaux d'action
  TRIP       → fermeture instantanée V1 + mode MANUAL (défaut critique machine)
  DISCONNECT → découplage réseau GRID_CONNECTED→ROLLING (défaut électrique/synchro)
  ALARM      → alerte visible, aucune action automatique sur les actionneurs

Anti-rebond : chaque protection a un délai configurable (delay_s).
  La protection ne se déclenche que si la condition est vraie en continu pendant delay_s.
  Après déclenchement, _already_acted empêche un re-déclenchement immédiat.

Singleton protection_system, appelé dans fake_api._generate_dual()
après la création de params_sim et avant le return.
"""

import time
import logging
from dataclasses import dataclass, field

from core.config import (
    NOMINAL,
    PROT_OVERSPEED_1_RPM, PROT_OVERSPEED_2_RPM,
    PROT_LUBE_OIL_PRESS_BAR, PROT_VIB_TRIP_MMS, PROT_AXIAL_DISP_MM,
    PROT_BEARING_TEMP_TRIP_C, PROT_PRESSURE_HP_MAX_BAR, PROT_TEMP_HP_MAX_C,
    PROT_VOLTAGE_MAX_KV, PROT_CURRENT_MAX_A, PROT_REVERSE_POWER_MW,
    PROT_SYNC_LOSS_RPM, PROT_FREQ_DEVIATION_HZ, PROT_EXCITATION_MIN_PU,
    PROT_VIB_ALARM_MMS, PROT_BEARING_TEMP_ALARM_C,
    PROT_OIL_LEVEL_MIN_PCT, PROT_OIL_FILTER_DP_BAR, PROT_VOLTAGE_MIN_KV,
)

logger = logging.getLogger("gta.protection")

NOMINAL_SPEED = NOMINAL["turbine_speed"]
NOMINAL_FREQ  = 50.0


# ─────────────────────────────────────────────────────────────────────────────
# Modèle de protection
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Protection:
    name:        str
    description: str
    action:      str          # TRIP | DISCONNECT | ALARM
    delay_s:     float = 0.0  # délai anti-rebond (s)
    inhibited:   bool  = False


# ─────────────────────────────────────────────────────────────────────────────
# Système de protections
# ─────────────────────────────────────────────────────────────────────────────

class ProtectionSystem:
    """Couche de protections automatiques — singleton."""

    def __init__(self):
        # Catalogue des protections (nom → Protection)
        self._protections: dict[str, Protection] = {p.name: p for p in [
            # ── Tier 1 : TRIP ─────────────────────────────────────────────
            Protection("OVERSPEED_1",     "Survitesse 110% (7080 RPM)",            "TRIP",       delay_s=0.0),
            Protection("OVERSPEED_2",     "Survitesse 115% (7400 RPM)",            "TRIP",       delay_s=0.0),
            Protection("LUBE_OIL_LOW",    "Pression huile basse (< 0.8 bar)",      "TRIP",       delay_s=2.0),
            Protection("OIL_PUMP_OFF",    "Pompe huile arrêtée",                   "TRIP",       delay_s=1.0),
            Protection("VIB_TRIP",        "Vibrations excessives zone D (ISO 10816)", "TRIP",    delay_s=3.0),
            Protection("AXIAL_DISP",      "Déplacement axial rotor (> 0.8 mm)",    "TRIP",       delay_s=0.0),
            Protection("BEARING_TEMP",    "Température palier critique (> 110°C)", "TRIP",       delay_s=5.0),
            Protection("HP_OVERPRESSURE", "Surpression HP (> 70 bar)",             "TRIP",       delay_s=0.0),
            Protection("HP_OVERTEMP",     "Surchauffe HP (> 510°C)",               "TRIP",       delay_s=5.0),
            Protection("OVERVOLTAGE",     "Surtension alternateur (> 110%)",       "TRIP",       delay_s=2.0),
            Protection("OVERCURRENT",     "Surintensité ligne (> 3500 A)",         "TRIP",       delay_s=3.0),
            Protection("REVERSE_POWER",   "Puissance inverse (motorisation)",      "TRIP",       delay_s=5.0),
            # ── Tier 2 : DISCONNECT ───────────────────────────────────────
            Protection("LOSS_OF_SYNC",    "Perte de synchronisme (écart > 200 RPM)", "DISCONNECT", delay_s=0.0),
            Protection("FREQ_DEVIATION",  "Fréquence réseau hors plage (±1 Hz)",   "DISCONNECT", delay_s=1.0),
            Protection("LOSS_OF_EXCIT",   "Perte d'excitation (E_fd < 0.5 p.u.)",  "DISCONNECT", delay_s=3.0),
            # ── Tier 3 : ALARM ────────────────────────────────────────────
            Protection("VIB_ALARM",       "Vibrations zone C (> 4.5 mm/s)",        "ALARM",      delay_s=0.0),
            Protection("BEARING_ALARM",   "Température palier alarme (> 95°C)",    "ALARM",      delay_s=0.0),
            Protection("OIL_LEVEL_LOW",   "Niveau huile bas (< 30%)",              "ALARM",      delay_s=0.0),
            Protection("OIL_FILTER_DP",   "ΔP filtre huile élevé (> 0.8 bar)",     "ALARM",      delay_s=0.0),
            Protection("UNDERVOLTAGE",    "Sous-tension alternateur (< 95%)",      "ALARM",      delay_s=0.0),
        ]}

        # Timestamp de première détection (anti-rebond)
        self._triggered_at:  dict[str, float] = {}
        # Protections déjà actionnées (évite re-déclenchement en boucle)
        self._already_acted: set[str]         = set()
        # Historique des déclenchements (50 derniers)
        self._history: list[dict] = []

    # ──────────────────────────────────────────────────────────────────────
    # TICK PRINCIPAL — appelé depuis fake_api._generate_dual()
    # ──────────────────────────────────────────────────────────────────────

    def check_all(self, params, controller, avr_controller) -> list[dict]:
        """
        Évalue toutes les protections sur le snapshot courant.
        Retourne la liste des protections déclenchées ce tick.
        params : GTAParameters (snapshot simulé)
        """
        now       = time.time()
        triggered = []

        conditions = self._build_conditions(params, avr_controller)

        for name, is_fault in conditions.items():
            prot = self._protections.get(name)
            if prot is None or prot.inhibited:
                continue

            if is_fault:
                if name not in self._triggered_at:
                    self._triggered_at[name] = now

                elapsed = now - self._triggered_at[name]
                if elapsed >= prot.delay_s and name not in self._already_acted:
                    self._fire(name, prot, params, controller, avr_controller, elapsed)
                    triggered.append({"name": name, "action": prot.action,
                                      "description": prot.description})
            else:
                # Condition revenue à la normale → réarmer l'anti-rebond
                self._triggered_at.pop(name, None)
                # Réarmer aussi _already_acted pour les ALARM (pas pour TRIP/DISC)
                if prot.action == "ALARM":
                    self._already_acted.discard(name)

        return triggered

    # ──────────────────────────────────────────────────────────────────────
    # CONDITIONS DE DÉCLENCHEMENT
    # ──────────────────────────────────────────────────────────────────────

    def _build_conditions(self, params, avr_controller) -> dict[str, bool]:
        """Évalue chaque condition et retourne un dict name → bool."""
        spd  = params.turbine_speed
        freq = params.grid_frequency
        vib  = max(params.vib_bearing_fwd, params.vib_bearing_aft)
        t_b  = max(params.temp_bearing_fwd, params.temp_bearing_aft)
        e_fd = avr_controller.e_fd_pu if avr_controller else 1.0

        grid_connected = getattr(params, "machine_state", "GRID_CONNECTED") == "GRID_CONNECTED"

        return {
            # Tier 1 — TRIP
            "OVERSPEED_1":     spd  > PROT_OVERSPEED_1_RPM,
            "OVERSPEED_2":     spd  > PROT_OVERSPEED_2_RPM,
            "LUBE_OIL_LOW":    params.lube_oil_press  < PROT_LUBE_OIL_PRESS_BAR,
            "OIL_PUMP_OFF":    params.lube_oil_pump   == "OFF",
            "VIB_TRIP":        vib  > PROT_VIB_TRIP_MMS,
            "AXIAL_DISP":      abs(params.axial_displacement) > PROT_AXIAL_DISP_MM,
            "BEARING_TEMP":    t_b  > PROT_BEARING_TEMP_TRIP_C,
            "HP_OVERPRESSURE": params.pressure_hp     > PROT_PRESSURE_HP_MAX_BAR,
            "HP_OVERTEMP":     params.temperature_hp  > PROT_TEMP_HP_MAX_C,
            "OVERVOLTAGE":     params.voltage          > PROT_VOLTAGE_MAX_KV,
            "OVERCURRENT":     params.current_a        > PROT_CURRENT_MAX_A,
            "REVERSE_POWER":   params.active_power     < PROT_REVERSE_POWER_MW,
            # Tier 2 — DISCONNECT (seulement si couplé réseau)
            "LOSS_OF_SYNC":   grid_connected and abs(spd  - NOMINAL_SPEED) > PROT_SYNC_LOSS_RPM,
            "FREQ_DEVIATION": grid_connected and abs(freq - NOMINAL_FREQ)  > PROT_FREQ_DEVIATION_HZ,
            "LOSS_OF_EXCIT":  grid_connected and e_fd < PROT_EXCITATION_MIN_PU,
            # Tier 3 — ALARM
            "VIB_ALARM":      vib  > PROT_VIB_ALARM_MMS,
            "BEARING_ALARM":  t_b  > PROT_BEARING_TEMP_ALARM_C,
            "OIL_LEVEL_LOW":  params.lube_oil_tank_level < PROT_OIL_LEVEL_MIN_PCT,
            "OIL_FILTER_DP":  params.lube_oil_filter_dp  > PROT_OIL_FILTER_DP_BAR,
            "UNDERVOLTAGE":   params.voltage             < PROT_VOLTAGE_MIN_KV,
        }

    # ──────────────────────────────────────────────────────────────────────
    # EXÉCUTION D'UNE PROTECTION
    # ──────────────────────────────────────────────────────────────────────

    def _fire(self, name: str, prot: Protection, params, controller, avr_controller, elapsed: float):
        self._already_acted.add(name)

        log_entry = {
            "time":        time.time(),
            "name":        name,
            "action":      prot.action,
            "description": prot.description,
            "elapsed_s":   round(elapsed, 2),
        }
        self._history.append(log_entry)
        if len(self._history) > 50:
            self._history.pop(0)

        if prot.action == "TRIP":
            logger.critical("[Protection] TRIP → %s (délai=%.1f s)", name, elapsed)
            if not controller.tripped:
                controller.emergency_trip(operator=f"PROTECTION:{name}")

        elif prot.action == "DISCONNECT":
            logger.warning("[Protection] DISCONNECT → %s (délai=%.1f s)", name, elapsed)
            if controller.machine_state == "GRID_CONNECTED":
                controller.disconnect_from_grid(operator=f"PROTECTION:{name}")

        elif prot.action == "ALARM":
            logger.warning("[Protection] ALARM → %s", name)
            try:
                from services.alert_manager import alert_manager
                from models.alert import Alert, AlertType, SeverityLevel, AlertSource
                from datetime import datetime, timedelta
                from core.config import TIMEZONE_OFFSET
                alert = Alert(
                    timestamp  = datetime.utcnow() + timedelta(hours=TIMEZONE_OFFSET),
                    alert_type = AlertType.THRESHOLD_EXCEEDED,
                    parameter  = name,
                    value      = 0.0,
                    threshold  = 0.0,
                    severity   = SeverityLevel.WARNING,
                    source     = AlertSource.THRESHOLD,
                    message    = f"[Protection] {prot.description}",
                )
                alert_manager._active_alerts.append(alert)
            except Exception as exc:
                logger.debug("Impossible de pousser l'alerte vers alert_manager : %s", exc)

    # ──────────────────────────────────────────────────────────────────────
    # RÉARMEMENT + API
    # ──────────────────────────────────────────────────────────────────────

    def reset(self):
        """Réarme toutes les protections après un reset_trip opérateur."""
        self._triggered_at.clear()
        self._already_acted.clear()
        logger.info("[Protection] Protections réarmées (reset_trip)")

    def inhibit(self, name: str, inhibited: bool) -> dict:
        """Inhibe ou réarme une protection par nom (pour tests)."""
        prot = self._protections.get(name)
        if prot is None:
            return {"accepted": False, "message": f"Protection inconnue : {name}"}
        prot.inhibited = inhibited
        logger.warning("[Protection] %s → inhibited=%s", name, inhibited)
        return {"accepted": True, "name": name, "inhibited": inhibited}

    def get_status(self) -> list[dict]:
        """État courant de toutes les protections (pour GET /control/protections)."""
        now = time.time()
        result = []
        for name, prot in self._protections.items():
            t_first = self._triggered_at.get(name)
            result.append({
                "name":        name,
                "description": prot.description,
                "action":      prot.action,
                "delay_s":     prot.delay_s,
                "inhibited":   prot.inhibited,
                "triggered":   name in self._triggered_at,
                "acted":       name in self._already_acted,
                "pending_s":   round(now - t_first, 1) if t_first else None,
            })
        return result

    def get_history(self) -> list[dict]:
        return list(reversed(self._history))


protection_system = ProtectionSystem()
