"""
scripts/measure_sync_flapping.py — Vérifie l'absence de flapping SYNC↔GRID (Phase 0 — A.3)

Exécution :
    cd backend && python scripts/measure_sync_flapping.py

But : confirmer que la structure de _check_auto_transitions() ne permet pas
de cycling entre SYNCHRONIZING et GRID_CONNECTED (structurellement impossible
car il n'existe pas de transition GRID → SYNC dans le code).

La mesure compte les transitions STATE_TRANSITION de/vers SYNCHRONIZING et GRID_CONNECTED
dans le journal operator_actions.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.database import init_db, get_db

init_db()

print("Analyse des transitions SYNC↔GRID dans operator_actions...")
print("(Requiert que le backend ait été démarré au moins une fois pour peupler le journal)")

with get_db() as conn:
    rows = conn.execute("""
        SELECT ts, value_before, value_after
        FROM operator_actions
        WHERE action_type = 'STATE_TRANSITION'
          AND (
              (value_before = 'SYNCHRONIZING' AND value_after = 'GRID_CONNECTED')
           OR (value_before = 'GRID_CONNECTED' AND value_after = 'SYNCHRONIZING')
          )
        ORDER BY ts ASC
    """).fetchall()

print(f"\nTransitions SYNC↔GRID trouvées : {len(rows)}")
for row in rows:
    print(f"  {row['ts']:30s}  {row['value_before']:20s} → {row['value_after']}")

# Compter le flapping (toute transition GRID → SYNC est anormale)
grid_to_sync = [r for r in rows if r['value_before'] == 'GRID_CONNECTED' and r['value_after'] == 'SYNCHRONIZING']
flapping_count = len(grid_to_sync)

print(f"\nFlapping (GRID→SYNC inattendu) : {flapping_count}")

if flapping_count == 0:
    print("""
Résultat : flapping_count = 0 (attendu).
→ Aucune hystérésis requise : la transition GRID→SYNC n'existe pas dans
  _check_auto_transitions (controller.py:373-393).
→ A.3 SKIP : documenter dans CLAUDE.md et passer à B.1.
""")
else:
    print(f"""
ATTENTION : {flapping_count} transitions GRID→SYNC détectées.
→ Implémentation d'un garde MIN_STATE_HOLD_S = 5.0 s requise dans
  controller._check_auto_transitions() sur _last_state_change_ts.
""")
