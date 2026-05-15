"""
scripts/measure_q_range.py — Mesure de la plage Q après saturation tanh (Phase 0 — A.2)

Exécution :
    cd backend && python scripts/measure_q_range.py

But : vérifier que la formule tanh ne génère pas de Q qui déclencherait les protections
OVERVOLTAGE ou REVERSE_POWER sur le spectre nominal de fonctionnement de l'AVR.

Sortie JSON :
  {
    "q_min_mvar":  ...,  "q_max_mvar":  ...,
    "v_min_kv":    ...,  "v_max_kv":    ...,
    "p_min_mw":    ...,  "p_max_mw":    ...,
    "prot_voltage_max_kv_recommendation": ...,
    "prot_reverse_power_mw_recommendation": ...
  }
"""
import sys, os, math, json
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.config import (
    AVR_Q_SENSITIVITY, Q_TANH_SCALE_MVAR,
    NOMINAL, AVR_E_FD_MIN, AVR_E_FD_MAX,
    PROT_VOLTAGE_MAX_KV, PROT_REVERSE_POWER_MW,
)

VOLTAGE_KV = 10.5  # tension nominale alternateur

def q_formula(active_power_mw: float, e_fd: float, cosphi_set: float) -> tuple[float, float]:
    """Retourne (q_mvar, v_term_kv) selon la formule Phase 0 — A.2."""
    cosphi_set = max(0.70, min(0.99, cosphi_set))
    q_base     = active_power_mw * math.tan(math.acos(cosphi_set))
    delta_raw  = AVR_Q_SENSITIVITY * (e_fd - 1.0)
    delta_sat  = Q_TANH_SCALE_MVAR * math.tanh(delta_raw / Q_TANH_SCALE_MVAR)
    q_mvar     = round(q_base + delta_sat, 3)
    v_term_kv  = round(max(9.0, min(12.0, VOLTAGE_KV * (0.95 + 0.05 * e_fd))), 3)
    return q_mvar, v_term_kv

print("Balayage : P ∈ [0, 30 MW], E_fd ∈ [0.5, 2.5], cos φ ∈ [0.70, 0.99]")
print("=" * 60)

results = []
P_range      = [p for p in range(0, 31, 2)]           # 0..30 MW par pas de 2
e_fd_range   = [round(0.5 + i * 0.1, 1) for i in range(21)]  # 0.5..2.5
cosphi_range = [round(0.70 + i * 0.05, 2) for i in range(7)] # 0.70..1.00

for p in P_range:
    for e_fd in e_fd_range:
        for cosphi in cosphi_range:
            q, v = q_formula(p, e_fd, cosphi)
            s = math.sqrt(p**2 + q**2) if (p > 0 or q != 0) else 0.0
            results.append({"p": p, "e_fd": e_fd, "cosphi": cosphi, "q": q, "v": v, "s": s})

q_values = [r["q"] for r in results]
v_values = [r["v"] for r in results]
p_values = [r["p"] for r in results]  # entrée, pas calculé

q_min = min(q_values)
q_max = max(q_values)
v_min = min(v_values)
v_max = max(v_values)

# P min "effectif" = active_power peut descendre en négatif si Q est trop grande?
# Non — P est l'entrée physique de la turbine. Le "REVERSE_POWER" vient de la
# puissance active réseau, ici on vérifie juste que Q ne perturbe pas la mesure cos φ.

report = {
    "q_min_mvar": q_min,
    "q_max_mvar": q_max,
    "v_min_kv":   v_min,
    "v_max_kv":   v_max,
    "p_range_mw": [min(p_values), max(p_values)],
    "current_PROT_VOLTAGE_MAX_KV":  PROT_VOLTAGE_MAX_KV,
    "current_PROT_REVERSE_POWER_MW": PROT_REVERSE_POWER_MW,
    "prot_voltage_max_kv_recommendation":  max(PROT_VOLTAGE_MAX_KV, round(v_max + 0.05, 2)),
    "prot_reverse_power_mw_recommendation": PROT_REVERSE_POWER_MW,  # P n'est pas affecté par Q dans ce modèle
    "Q_TANH_SCALE_MVAR_used": Q_TANH_SCALE_MVAR,
    "note": (
        "Saturation tanh garantit |delta_q| <= Q_TANH_SCALE_MVAR pour tout E_fd. "
        "Seul v_max peut changer (E_fd haute → V_term haute)."
    )
}

print(json.dumps(report, indent=2))

print("\nConclusion :")
if v_max <= PROT_VOLTAGE_MAX_KV:
    print(f"  ✓ v_max={v_max} kV <= PROT_VOLTAGE_MAX_KV={PROT_VOLTAGE_MAX_KV} → aucun retuning nécessaire")
else:
    print(f"  ! v_max={v_max} kV > PROT_VOLTAGE_MAX_KV={PROT_VOLTAGE_MAX_KV}")
    print(f"    → Mettre PROT_VOLTAGE_MAX_KV = {report['prot_voltage_max_kv_recommendation']} dans config.py")
