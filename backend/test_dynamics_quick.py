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
print("TESTS TERMINÉS")
print("=" * 60)
