"""
test_dynamics_quick.py — Vérification rapide des nouvelles fonctionnalités
Sans Redis, sans FastAPI, sans Docker.
Exécution : python test_dynamics_quick.py  (depuis /backend)
"""
import sys, os, math
sys.path.insert(0, os.path.dirname(__file__))

# ─── Importer uniquement ce qui ne dépend pas de Redis ───────────────────────
from simulation.dynamics import rotor_dynamics, OMEGA_NOMINAL, TAU
from simulation.pid import PID
from core.config import NOMINAL, PID_SPEED_KP, PID_SPEED_KI, PID_SPEED_KD

NOMINAL_RPM = NOMINAL["turbine_speed"]   # 6435 RPM

# ─────────────────────────────────────────────────────────────────────────────
# TEST 1 — RotorDynamics : inertie (réponse 1er ordre)
# Scénario : machine à l'arrêt, target = 6435 RPM → vitesse doit monter avec τ ≈ 12.5 s
# ─────────────────────────────────────────────────────────────────────────────
print("=" * 60)
print("TEST 1 — Inertie rotor (dynamique 1er ordre)")
print(f"  tau = J/D = {TAU:.1f} s   ->  63% atteint en {TAU:.1f} s, 95% en {3*TAU:.1f} s")
print("=" * 60)

rotor_dynamics.reset_to_stop()      # vitesse = 0, libre
rotor_dynamics.unlock_from_grid()

dt   = 0.5   # tick 500 ms comme la vraie boucle
t    = 0.0
rows = []

for _ in range(200):    # 100 secondes simulées
    rotor_dynamics.update(dt, target_speed_rpm=NOMINAL_RPM)
    rows.append((round(t, 1), rotor_dynamics.speed_rpm, rotor_dynamics.frequency_hz))
    t += dt

# Afficher quelques jalons clés
print(f"{'Temps (s)':>10}  {'Vitesse (RPM)':>14}  {'Fréquence (Hz)':>15}  {'% nominal':>10}")
milestones = {TAU, 2*TAU, 3*TAU, 4*TAU, 100}
for t_val, spd, freq in rows:
    if any(abs(t_val - m) < dt/2 for m in milestones):
        print(f"{t_val:>10.1f}  {spd:>14.1f}  {freq:>15.3f}  {spd/NOMINAL_RPM*100:>9.1f}%")

tau_speed = next(spd for t_val, spd, _ in rows if abs(t_val - TAU) < dt/2)
ok = abs(tau_speed / NOMINAL_RPM - 0.632) < 0.05
print(f"\n  → À t=τ : {tau_speed:.0f} RPM   attendu ≈ 63.2% = {0.632*NOMINAL_RPM:.0f} RPM   {'✓ OK' if ok else '✗ ÉCHEC'}")

# ─────────────────────────────────────────────────────────────────────────────
# TEST 2 — Grid lock/unlock
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=" * 60)
print("TEST 2 — Verrouillage réseau")
print("=" * 60)

rotor_dynamics.lock_to_grid()
spd_before = rotor_dynamics.speed_rpm
rotor_dynamics.update(dt=0.5, target_speed_rpm=0)   # réseau résiste → vitesse reste proche de nominal
spd_locked = rotor_dynamics.speed_rpm
# Avec raideur réseau (TAU_GRID=3s), target=0 → cible effective = 90% nominal
# Après 0.5 s : alpha = exp(-0.5/3) ≈ 0.846 → vitesse reste > 80% nominal
ok_locked = spd_locked > NOMINAL_RPM * 0.80
print(f"  Grid locked, target=0 RPM → vitesse = {spd_locked:.0f} RPM (réseau résiste)   {'✓ OK' if ok_locked else '✗ ECHEC'}")

rotor_dynamics.unlock_from_grid()
spd_before_free = rotor_dynamics.speed_rpm
rotor_dynamics.update(dt=0.5, target_speed_rpm=0)
spd_free = rotor_dynamics.speed_rpm
print(f"  Grid free,   target=0 RPM → vitesse = {spd_free:.0f} RPM (décroît librement)   {'✓ OK (décroît)' if spd_free < spd_before_free else '✗ devrait décroître'}")

# ─────────────────────────────────────────────────────────────────────────────
# TEST 3 — PID Vitesse (governor)
# Scénario : vitesse à 0, consigne 6435 RPM, simuler 60 ticks
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=" * 60)
print("TEST 3 — PID Vitesse (governor)")
print("=" * 60)

pid_speed = PID(kp=PID_SPEED_KP, ki=PID_SPEED_KI, kd=PID_SPEED_KD,
                out_min=0.0, out_max=100.0)
rotor_dynamics.reset_to_stop()
rotor_dynamics.unlock_from_grid()

speed = 0.0
dt    = 0.5
print(f"{'Tick':>5}  {'V1 (%)':>8}  {'Vitesse (RPM)':>14}")
for i in range(80):
    v1 = pid_speed.compute(NOMINAL_RPM, speed, dt)
    rotor_dynamics.update(dt, target_speed_rpm=NOMINAL_RPM * (v1 / 100.0))
    speed = rotor_dynamics.speed_rpm
    if i % 10 == 0:
        print(f"{i:>5}  {v1:>8.1f}  {speed:>14.1f}")

print(f"\n  → Vitesse finale (40 s) : {speed:.0f} RPM   {'✓ en montée' if speed > 0 else '✗ immobile'}")

# ─────────────────────────────────────────────────────────────────────────────
# TEST 4 — Inertie couplée réseau (raideur réseau, TAU_GRID = 3 s)
# Scénario : machine à 6157 RPM (fin test 3), couplage réseau
#   → vitesse doit converger vers 6435 RPM en ~3×TAU_GRID = 9 s
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=" * 60)
print("TEST 4 — Raideur réseau (GRID_CONNECTED, TAU_GRID = 3 s)")
print("=" * 60)

from core.config import TAU_GRID
rotor_dynamics.lock_to_grid()   # active la raideur réseau (pas de saut instantané)

print(f"{'Temps (s)':>10}  {'Vitesse (RPM)':>14}  {'Freq (Hz)':>10}")
t = 0.0
for _ in range(50):
    rotor_dynamics.update(dt=0.5, target_speed_rpm=NOMINAL_RPM)  # réseau impose nominal
    t += 0.5
    if t in (1.5, 3.0, 6.0, 9.0, 15.0, 25.0):
        print(f"{t:>10.1f}  {rotor_dynamics.speed_rpm:>14.1f}  {rotor_dynamics.frequency_hz:>10.3f}")

ok = abs(rotor_dynamics.speed_rpm - NOMINAL_RPM) < 100
print(f"\n  → Vitesse a bien convergé vers {NOMINAL_RPM:.0f} RPM : {'✓ OK' if ok else '✗ ECHEC'}")

# Sous-test : -2% vitesse (glissement léger)
rotor_dynamics.unlock_from_grid()
rotor_dynamics.omega_rad_s = OMEGA_NOMINAL * 0.98
print(f"  -2% vitesse → freq = {rotor_dynamics.frequency_hz} Hz   {'✓ ~49 Hz' if abs(rotor_dynamics.frequency_hz - 49.0) < 0.1 else '✗'}")

# ─────────────────────────────────────────────────────────────────────────────
# TEST 5 — Protection perte de synchronisme (LOSS_OF_SYNC)
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=" * 60)
print("TEST 5 — Protection perte de synchronisme")
print("=" * 60)

from simulation.protection import protection_system, NOMINAL_SPEED, PROT_SYNC_LOSS_RPM

# Simuler une vitesse hors seuil
rotor_dynamics.lock_to_grid()
rotor_dynamics.omega_rad_s = (NOMINAL_RPM - 300) * 2 * math.pi / 60  # -300 RPM

deviation = rotor_dynamics.speed_deviation_rpm
ok_detect = deviation > PROT_SYNC_LOSS_RPM
print(f"  Déviation simulée : {deviation:.0f} RPM  (seuil = {PROT_SYNC_LOSS_RPM:.0f} RPM)")
print(f"  Condition LOSS_OF_SYNC détectée : {'✓ OUI' if ok_detect else '✗ NON'}")

# Vitesse dans la plage
rotor_dynamics.omega_rad_s = OMEGA_NOMINAL
ok_no_detect = rotor_dynamics.speed_deviation_rpm <= PROT_SYNC_LOSS_RPM
print(f"  Vitesse nominale : déviation = {rotor_dynamics.speed_deviation_rpm:.1f} RPM → protection inactive : {'✓ OK' if ok_no_detect else '✗'}")

print()
print("=" * 60)
print("TESTS 1-5 TERMINÉS")
print("=" * 60)

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 0 — initialisation SQLite (requis pour tests 7, 8, 9)
# ─────────────────────────────────────────────────────────────────────────────
try:
    from core.database import init_db
    init_db()
    _db_ok = True
except Exception as _e:
    print(f"\n[WARN] init_db() échec : {_e} — tests SQLite peuvent échouer")
    _db_ok = False

# ─────────────────────────────────────────────────────────────────────────────
# TEST 6 — A.2 : Saturation tanh sur Q réactive
# Vérifie que |delta_q_sat| <= Q_TANH_SCALE_MVAR pour tout E_fd, et que
# le régime linéaire est conservé autour de E_fd=1.0
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=" * 60)
print("TEST 6 — A.2 : Saturation tanh sur Q réactive")
print("=" * 60)

from core.config import AVR_Q_SENSITIVITY, Q_TANH_SCALE_MVAR

def _q_tanh_formula(active_power: float, e_fd: float, cosphi_set: float = 0.85) -> float:
    cosphi_set = max(0.70, min(0.99, cosphi_set))
    q_base     = active_power * math.tan(math.acos(cosphi_set))
    delta_raw  = AVR_Q_SENSITIVITY * (e_fd - 1.0)
    delta_sat  = Q_TANH_SCALE_MVAR * math.tanh(delta_raw / Q_TANH_SCALE_MVAR)
    return round(q_base + delta_sat, 3)

# 1) Grande excursion E_fd = 1.30 (cas plan) → saturation respectée
P_TEST = 24.0
e_fd_high = 1.30
q_high = _q_tanh_formula(P_TEST, e_fd_high)
q_base_ref = P_TEST * math.tan(math.acos(0.85))
delta_q = q_high - q_base_ref
ok_sat = abs(delta_q) <= Q_TANH_SCALE_MVAR + 0.5
print(f"  E_fd=1.30, P=24 MW : q_mvar={q_high:.2f}, delta_q={delta_q:.2f} MVAR (seuil={Q_TANH_SCALE_MVAR})")
print(f"  → Saturation respectée : {'✓ OK' if ok_sat else '✗ ÉCHEC'}")

# 2) E_fd = 2.5 (max) → saturation stricte
e_fd_max = 2.5
q_max_test = _q_tanh_formula(P_TEST, e_fd_max)
delta_max = q_max_test - q_base_ref
ok_sat_max = abs(delta_max) <= Q_TANH_SCALE_MVAR + 0.01
print(f"  E_fd=2.5 (max) : q_mvar={q_max_test:.2f}, delta_q={delta_max:.2f} MVAR (seuil={Q_TANH_SCALE_MVAR})")
print(f"  → Saturation stricte à E_fd max : {'✓ OK' if ok_sat_max else '✗ ÉCHEC'}")

# 3) Régime linéaire autour de E_fd=1.0 : tanh(x)≈x pour x<<1
e_fd_near = 1.05
q_near = _q_tanh_formula(P_TEST, e_fd_near)
delta_near = q_near - q_base_ref
delta_linear = AVR_Q_SENSITIVITY * (e_fd_near - 1.0)
linear_ok = abs(delta_near - delta_linear) < 0.1
print(f"  E_fd=1.05 : delta_q={delta_near:.3f} ≈ linéaire={delta_linear:.3f} MVAR")
print(f"  → Régime linéaire conservé : {'✓ OK' if linear_ok else '✗ ÉCHEC'}")

# 4) cos φ dynamique (vs hardcode 0.85)
q_85 = _q_tanh_formula(P_TEST, 1.0, cosphi_set=0.85)
q_70 = _q_tanh_formula(P_TEST, 1.0, cosphi_set=0.70)
dynamic_ok = q_70 > q_85   # cos φ plus bas → tan plus grand → q_base plus grande
print(f"  cos φ=0.85 : q_mvar={q_85:.2f}  |  cos φ=0.70 : q_mvar={q_70:.2f}")
print(f"  → cos φ dynamique affecte q_base : {'✓ OK' if dynamic_ok else '✗ ÉCHEC'}")

# ─────────────────────────────────────────────────────────────────────────────
# TEST 7 — A.4 : Dégradation Weibull (mathématiques + persistance)
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=" * 60)
print("TEST 7 — A.4 : Dégradation Weibull")
print("=" * 60)

import time as _time
from core.config import (
    DEGRADATION_SHAPE, DEGRADATION_SCALE_H,
    DEGRADATION_MAX_EFF_DRIFT_PCT, DEGRADATION_MAX_VIB_DRIFT_MMS,
)

def _weibull_cdf(grid_hours: float) -> float:
    if grid_hours <= 0:
        return 0.0
    return 1.0 - math.exp(-(grid_hours / DEGRADATION_SCALE_H) ** DEGRADATION_SHAPE)

# 1) CDF à 0 h = 0
ok_zero = abs(_weibull_cdf(0)) < 1e-9
print(f"  CDF à 0 h = {_weibull_cdf(0):.6f}   → {'✓ OK' if ok_zero else '✗ ÉCHEC'}")

# 2) CDF à SCALE_H > 0.5 (par définition Weibull : ~63% à λ=SCALE, mais k>1 → plus)
cdf_scale = _weibull_cdf(DEGRADATION_SCALE_H)
ok_scale = cdf_scale > 0.5
print(f"  CDF à {DEGRADATION_SCALE_H:.0f} h = {cdf_scale:.4f}   → {'✓ >0.5' if ok_scale else '✗ ÉCHEC'}")

# 3) CDF monotone croissante
cdf_prev = 0.0
monotone = True
for h in range(0, 10001, 100):
    c = _weibull_cdf(h)
    if c < cdf_prev:
        monotone = False
        break
    cdf_prev = c
print(f"  CDF monotone croissante sur [0, 10000 h] : {'✓ OK' if monotone else '✗ ÉCHEC'}")

# 4) Dérive rendement négative et bornée
eff_drift_8000 = DEGRADATION_MAX_EFF_DRIFT_PCT * _weibull_cdf(8000)
ok_eff = eff_drift_8000 < 0 and eff_drift_8000 >= DEGRADATION_MAX_EFF_DRIFT_PCT
print(f"  Dérive eff à 8000 h = {eff_drift_8000:.3f} %   → {'✓ OK (négatif, borné)' if ok_eff else '✗ ÉCHEC'}")

# 5) Test du module DegradationModel directement
try:
    from simulation.degradation import DegradationModel
    dmod = DegradationModel.__new__(DegradationModel)
    dmod.grid_hours = 0.0
    dmod._t_last_persist = _time.time() + 1e9  # désactiver la persistance pendant le test

    results_drift = []
    dt_test = 3600.0  # avancer heure par heure
    for _ in range(100):
        d = dmod.update(dt_test, is_grid_connected=True)
        results_drift.append(d["eff_drift_pct"])

    ok_hours = abs(dmod.grid_hours - 100.0) < 0.01
    ok_drift_neg = all(x <= 0 for x in results_drift)
    ok_drift_mono = all(results_drift[i] >= results_drift[i+1] for i in range(len(results_drift)-1))
    print(f"  100 h simulées → grid_hours={dmod.grid_hours:.1f} h : {'✓' if ok_hours else '✗'}")
    print(f"  Dérive eff toujours ≤ 0 : {'✓' if ok_drift_neg else '✗'}")
    print(f"  Dérive eff monotone décroissante : {'✓' if ok_drift_mono else '✗'}")

    # Test is_grid_connected=False n'avance pas le compteur
    h_before = dmod.grid_hours
    dmod.update(3600.0, is_grid_connected=False)
    ok_no_count = abs(dmod.grid_hours - h_before) < 1e-6
    print(f"  Hors GRID → compteur figé : {'✓' if ok_no_count else '✗'}")
except Exception as _e:
    print(f"  ✗ Exception : {_e}")

# ─────────────────────────────────────────────────────────────────────────────
# TEST 8 — A.1 : PID pression — blocage si état != GRID_CONNECTED
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=" * 60)
print("TEST 8 — A.1 : Blocage regulation PRESSURE hors GRID_CONNECTED")
print("=" * 60)

try:
    from simulation.controller import Controller
    ctrl_test = Controller()

    # Tester blocage en ROLLING
    ctrl_test.machine_state = "ROLLING"
    result_rolling = ctrl_test.set_regulation_target("PRESSURE", "test")
    ok_blocked_rolling = not result_rolling.get("accepted", True)
    print(f"  ROLLING → PRESSURE refusé : {'✓ OK' if ok_blocked_rolling else '✗ ÉCHEC'}")
    print(f"    Raison : {result_rolling.get('message', '')}")

    # Tester blocage en STOPPED
    ctrl_test.machine_state = "STOPPED"
    result_stopped = ctrl_test.set_regulation_target("PRESSURE", "test")
    ok_blocked_stopped = not result_stopped.get("accepted", True)
    print(f"  STOPPED → PRESSURE refusé : {'✓ OK' if ok_blocked_stopped else '✗ ÉCHEC'}")

    # Tester accepté en GRID_CONNECTED
    ctrl_test.machine_state = "GRID_CONNECTED"
    ctrl_test.mode = "AUTO"
    result_grid = ctrl_test.set_regulation_target("PRESSURE", "test")
    ok_accepted = result_grid.get("accepted", False)
    print(f"  GRID_CONNECTED → PRESSURE accepté : {'✓ OK' if ok_accepted else '✗ ÉCHEC'}")
    print(f"    regulation_target = {ctrl_test._regulation_target}")

    # Tester retour à POWER
    result_power = ctrl_test.set_regulation_target("POWER", "test")
    ok_power_back = result_power.get("accepted", False) and ctrl_test._regulation_target == "POWER"
    print(f"  Retour POWER → accepté : {'✓ OK' if ok_power_back else '✗ ÉCHEC'}")

    # Tester reset en MANUAL (depuis AUTO)
    ctrl_test.mode = "AUTO"  # forcer AUTO pour que set_mode(MANUAL) exécute le reset
    ctrl_test._regulation_target = "PRESSURE"
    ctrl_test.set_mode("MANUAL", "test")
    ok_reset_manual = ctrl_test._regulation_target == "POWER"
    print(f"  set_mode(MANUAL depuis AUTO) -> regulation_target reset POWER : {'✓ OK' if ok_reset_manual else '✗ ECHEC'}")

except Exception as _e:
    print(f"  ✗ Exception : {_e}")
    import traceback
    traceback.print_exc()

# ─────────────────────────────────────────────────────────────────────────────
# TEST 9 — A.1 : PID pression — sens de régulation correct
# V1↑ → pression↓ dans la formule inversée
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=" * 60)
print("TEST 9 — A.1 : Sens PID pression (V1↑ → pression↓)")
print("=" * 60)

from simulation.pid import PID
from core.config import (
    PID_PRESSURE_KP, PID_PRESSURE_KI, PID_PRESSURE_KD,
    PRESSURE_HP_SETPOINT_BAR,
)

pid_p = PID(kp=PID_PRESSURE_KP, ki=PID_PRESSURE_KI, kd=PID_PRESSURE_KD,
            out_min=0.0, out_max=100.0)

# Convention inversée : compute(setpoint=current, measurement=sp)
# error = current - sp > 0 si pression trop haute → output > 0 → V1 monte → admission ↑ → pression ↓

sp = PRESSURE_HP_SETPOINT_BAR  # 60 bar
dt = 0.5

# 1) Direction correcte : pression haute → V1 croît sur 80 ticks (40s)
for _ in range(80):
    pid_p.compute(65.0, sp, dt)
v1_after_80ticks = pid_p.compute(65.0, sp, dt)
ok_high = v1_after_80ticks > 50.0
print(f"  Pression 65 bar (haute), 81 ticks : V1 = {v1_after_80ticks:.1f} % (attendu >50) : {'OK' if ok_high else 'ECHEC'}")

# 2) Direction : pression basse → V1 reste à minimum (clamped 0)
pid_p2 = PID(kp=PID_PRESSURE_KP, ki=PID_PRESSURE_KI, kd=PID_PRESSURE_KD,
             out_min=0.0, out_max=100.0)
v1_low_1tick = pid_p2.compute(55.0, sp, dt)
ok_low = v1_low_1tick == 0.0  # error=-5 → output négatif → clamped à 0
print(f"  Pression 55 bar (basse) : V1 = {v1_low_1tick:.3f} % (clamped 0) : {'OK' if ok_low else 'ECHEC'}")

# 3) Direction globale : V1 haute > V1 basse (signe correct)
ok_direction = v1_after_80ticks > v1_low_1tick
print(f"  Direction : V1_haute({v1_after_80ticks:.1f}) > V1_basse({v1_low_1tick:.1f}) : {'OK' if ok_direction else 'ECHEC'}")

# 4) Pression au setpoint : PID en régime etabli, intégrale nulle → V1 ≈ 0
pid_p3 = PID(kp=PID_PRESSURE_KP, ki=PID_PRESSURE_KI, kd=PID_PRESSURE_KD,
             out_min=0.0, out_max=100.0)
v1_eq = pid_p3.compute(sp, sp, dt)
ok_eq = abs(v1_eq) < 1.0
print(f"  Pression = setpoint (60 bar) : V1 = {v1_eq:.3f} % (attendu ~0) : {'OK' if ok_eq else 'ECHEC'}")

print()
print("=" * 60)
print("TOUS LES TESTS PHASE 0 TERMINÉS")
print("=" * 60)

# =============================================================================
# TESTS PHASE 1
# =============================================================================

from simulation.controller import Controller, DROOP_FREQ_REF_HZ
from simulation.avr_controller import AVRController
from simulation.attemperator import Attemperator
from simulation.condenser import Condenser
from core.config import (
    DROOP_R, DROOP_MAX_DELTA_MW, DROOP_DEADBAND_HZ,
    NOMINAL, PID_PRESSURE_KP, PID_PRESSURE_KI, PID_PRESSURE_KD, PRESSURE_HP_SETPOINT_BAR,
    AVR_OEL_THRESHOLD_PU, AVR_OEL_TIMER_S,
    AVR_UEL_MIN_Q_RATIO, AVR_UEL_E_FD_FLOOR_PU,
    AVR_SCL_THRESHOLD_A, AVR_SCL_TIMER_S,
    ATTEMP_T_HP_SETPOINT_C,
    COND_LEVEL_SETPOINT_PCT, COND_VACUUM_SETPOINT_MBAR,
)

# ─────────────────────────────────────────────────────────────────────────────
# TEST 10 — Droop primaire : calcul offset ΔP pour une déviation de fréquence
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=" * 60)
print("TEST 10 — Droop primaire 4 %")
print("=" * 60)

ctrl_droop = Controller()
ctrl_droop.machine_state = "GRID_CONNECTED"
ctrl_droop.mode = "AUTO"

# 1) Nominal : freq = 50 Hz → offset = 0
offset_nominal = ctrl_droop._compute_droop_offset(50.00)
ok_nominal = offset_nominal == 0.0
print(f"  50.00 Hz : droop_offset = {offset_nominal:.3f} MW (attendu 0.0) : {'OK' if ok_nominal else 'ECHEC'}")

# 2) Bande morte : 49.99 Hz (Δf = -0.01 < deadband 0.02) → offset = 0
offset_deadband = ctrl_droop._compute_droop_offset(49.99)
ok_deadband = offset_deadband == 0.0
print(f"  49.99 Hz : droop_offset = {offset_deadband:.3f} MW (bande morte, attendu 0.0) : {'OK' if ok_deadband else 'ECHEC'}")

# 3) 49.7 Hz : Δf = -0.3, Δf_eff = -0.28 → ΔP = -(24/0.04) * (-0.28/50) ≈ +3.36 MW
offset_drop = ctrl_droop._compute_droop_offset(49.7)
expected_49_7 = -(NOMINAL["active_power"] / DROOP_R) * ((49.7 - 50.0 + DROOP_DEADBAND_HZ) / 50.0)
ok_drop = abs(offset_drop - expected_49_7) < 0.1
print(f"  49.7 Hz  : droop_offset = {offset_drop:.3f} MW (attendu ≈ {expected_49_7:.2f}) : {'OK' if ok_drop else 'ECHEC'}")

# 4) Saturation : 49.0 Hz → clamped à DROOP_MAX_DELTA_MW
offset_sat = ctrl_droop._compute_droop_offset(49.0)
ok_sat = abs(offset_sat - DROOP_MAX_DELTA_MW) < 0.01
print(f"  49.0 Hz  : droop_offset = {offset_sat:.3f} MW (sat. attendu +{DROOP_MAX_DELTA_MW}) : {'OK' if ok_sat else 'ECHEC'}")

# 5) Surcharg réseau (freq > 50) : doit réduire la puissance
offset_over = ctrl_droop._compute_droop_offset(50.3)
ok_over = offset_over < 0.0
print(f"  50.3 Hz  : droop_offset = {offset_over:.3f} MW (attendu < 0) : {'OK' if ok_over else 'ECHEC'}")

# 6) Hors GRID_CONNECTED → offset = 0
ctrl_droop.machine_state = "ROLLING"
offset_rolling = ctrl_droop._compute_droop_offset(49.7)
ok_rolling = offset_rolling == 0.0
print(f"  ROLLING  : droop_offset = {offset_rolling:.3f} MW (attendu 0, non GRID) : {'OK' if ok_rolling else 'ECHEC'}")

# ─────────────────────────────────────────────────────────────────────────────
# TEST 11 — Limiteurs AVR : OEL / UEL / SCL
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=" * 60)
print("TEST 11 — Limiteurs AVR (OEL / UEL / SCL)")
print("=" * 60)

avr_test = AVRController()
dt = 0.5

# ── OEL : forcer E_fd = 2.4 (> seuil 2.2) pendant 12.5 s > 10 s → oel_active
avr_test.mode = "MANUAL"
avr_test.e_fd_manual = 2.4

n_ticks_oel = int(AVR_OEL_TIMER_S / dt) + 5   # 25 ticks
for _ in range(n_ticks_oel):
    avr_test.update(dt=dt, v_term_kv=10.5, cosphi=0.85)

ok_oel_active = avr_test.oel_active
ok_oel_clamped = avr_test.e_fd_pu <= AVR_OEL_THRESHOLD_PU + 0.001
print(f"  OEL actif après {n_ticks_oel * dt:.1f} s (E_fd=2.4) : oel_active={avr_test.oel_active} e_fd={avr_test.e_fd_pu:.3f} : {'OK' if ok_oel_active and ok_oel_clamped else 'ECHEC'}")

# OEL reset : revenir à E_fd normal
avr_test.e_fd_manual = 1.0
for _ in range(n_ticks_oel):
    avr_test.update(dt=dt, v_term_kv=10.5, cosphi=0.85)
ok_oel_reset = not avr_test.oel_active
print(f"  OEL reset après {n_ticks_oel * dt:.1f} s (E_fd=1.0) : oel_active={avr_test.oel_active} : {'OK' if ok_oel_reset else 'ECHEC'}")

# ── UEL : Q/S_max très négatif → uel_active
avr_test2 = AVRController()
avr_test2.mode = "VOLTAGE"
# q_ratio = -15/41 ≈ -0.366 < seuil -0.30
avr_test2.update(dt=0.5, v_term_kv=10.5, cosphi=0.85, q_mvar=-15.0, s_max_mva=41.0)
ok_uel_active = avr_test2.uel_active
ok_uel_floor = avr_test2.e_fd_pu >= AVR_UEL_E_FD_FLOOR_PU - 0.001
print(f"  UEL actif (Q=-15 MVAR, S_max=41) : uel_active={avr_test2.uel_active} e_fd={avr_test2.e_fd_pu:.3f} : {'OK' if ok_uel_active and ok_uel_floor else 'ECHEC'}")

# UEL inactif si Q normal
avr_test2.update(dt=0.5, v_term_kv=10.5, cosphi=0.85, q_mvar=10.0, s_max_mva=41.0)
ok_uel_off = not avr_test2.uel_active
print(f"  UEL inactif (Q=+10 MVAR) : uel_active={avr_test2.uel_active} : {'OK' if ok_uel_off else 'ECHEC'}")

# ── SCL : I_stator > seuil pendant 35 ticks (17.5 s > 15 s) → scl_active
avr_test3 = AVRController()
avr_test3.mode = "VOLTAGE"
n_ticks_scl = int(AVR_SCL_TIMER_S / dt) + 5   # 65 ticks
for _ in range(n_ticks_scl):
    avr_test3.update(dt=dt, v_term_kv=10.5, cosphi=0.85, i_stator_a=3400.0)

ok_scl_active = avr_test3.scl_active
ok_scl_reduced = avr_test3.e_fd_pu < 1.0
print(f"  SCL actif après {n_ticks_scl * dt:.1f} s (I=3400 A) : scl_active={avr_test3.scl_active} e_fd={avr_test3.e_fd_pu:.3f} (<1.0) : {'OK' if ok_scl_active and ok_scl_reduced else 'ECHEC'}")

# ─────────────────────────────────────────────────────────────────────────────
# TEST 12 — Désurchauffeur : convergence et bypass
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=" * 60)
print("TEST 12 — Désurchauffeur (Attemperator)")
print("=" * 60)

attemp_test = Attemperator()
dt = 0.5

# 1) T haute → injection monte, T sort réduite
t_in = 470.0
for _ in range(200):
    t_out, inj = attemp_test.step(t_in, dt)
ok_inj = inj > 20.0
ok_cool = t_out < t_in
print(f"  T_in=470°C, 200 ticks : injection={inj:.1f}% (>20%), T_out={t_out:.1f}°C (<470) : {'OK' if ok_inj and ok_cool else 'ECHEC'}")

# 2) T égale setpoint → injection nulle (pas d'erreur)
attemp_eq = Attemperator()
t_out_eq, inj_eq = attemp_eq.step(ATTEMP_T_HP_SETPOINT_C, dt)
ok_eq_inj = inj_eq < 1.0
ok_eq_t = abs(t_out_eq - ATTEMP_T_HP_SETPOINT_C) < 0.5
print(f"  T_in=setpoint (440°C) : injection={inj_eq:.3f}% (<1%), T_out={t_out_eq:.1f}°C : {'OK' if ok_eq_inj and ok_eq_t else 'ECHEC'}")

# 3) Bypass (disabled) → T_out = T_in, injection = 0
attemp_dis = Attemperator()
attemp_dis.set_enabled(False)
t_out_dis, inj_dis = attemp_dis.step(470.0, dt)
ok_bypass = (t_out_dis == 470.0) and (inj_dis == 0.0)
print(f"  Bypass désactivé : T_out={t_out_dis:.1f}°C=T_in, injection={inj_dis:.1f}% : {'OK' if ok_bypass else 'ECHEC'}")

# 4) Clamp sécurité : T_in très basse + setpoint encore plus bas → plancher 380°C
attemp_clamp = Attemperator()
attemp_clamp.setpoint_c = 200.0   # artificiel, bien sous 380
for _ in range(300):
    t_out_cl, _ = attemp_clamp.step(500.0, dt)
ok_clamp = t_out_cl >= 380.0
print(f"  Clamp sécurité (SP=200°C) : T_out={t_out_cl:.1f}°C (plancher >=380°C) : {'OK' if ok_clamp else 'ECHEC'}")

# ─────────────────────────────────────────────────────────────────────────────
# TEST 13 — Condenseur : régime stable + perturbation
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=" * 60)
print("TEST 13 — Condenseur (hotwell + vide)")
print("=" * 60)

cond_test = Condenser()
dt = 0.5

# 1) 600 ticks avec débit nominal → niveau et vide doivent converger
for _ in range(600):
    state = cond_test.step(dt, steam_flow_condenser_th=74.0)

ok_level = abs(cond_test.level_pct - COND_LEVEL_SETPOINT_PCT) < 10.0
ok_vacuum = abs(cond_test.vacuum_mbar - COND_VACUUM_SETPOINT_MBAR) < 15.0
print(f"  600 ticks @ 74 T/h : level={cond_test.level_pct:.1f}% (sp={COND_LEVEL_SETPOINT_PCT}±10) : {'OK' if ok_level else 'ECHEC'}")
print(f"  600 ticks @ 74 T/h : vacuum={cond_test.vacuum_mbar:.1f} mbar (sp={COND_VACUUM_SETPOINT_MBAR}±15) : {'OK' if ok_vacuum else 'ECHEC'}")

# 2) Perturbation : débit x1.4 → niveau et vide se dégradent puis reviennent
level_before = cond_test.level_pct
vac_before   = cond_test.vacuum_mbar
for _ in range(120):
    cond_test.step(dt, steam_flow_condenser_th=104.0)
level_perturb = cond_test.level_pct
vac_perturb   = cond_test.vacuum_mbar
# Le régulateur doit réagir : pompe et éjecteur ouvrent davantage
ok_pump   = cond_test.pump_pct > 60.0
ok_ejector = cond_test.ejector_pct > 60.0
print(f"  Perturbation 104 T/h 60s : pump={cond_test.pump_pct:.1f}% (>60) ejector={cond_test.ejector_pct:.1f}% (>60) : {'OK' if ok_pump and ok_ejector else 'ECHEC'}")

# 3) Bypass désactivé → snapshot retourné sans intégration
cond_test.enabled = False
snap_off = cond_test.step(dt, steam_flow_condenser_th=74.0)
ok_enabled_field = snap_off["condenser_enabled"] == False
print(f"  Condenseur désactivé : snapshot retourné, enabled={snap_off['condenser_enabled']} : {'OK' if ok_enabled_field else 'ECHEC'}")

print()
print("=" * 60)
print("TOUS LES TESTS PHASE 1 TERMINÉS")
print("=" * 60)
