/**
 * assets/synoptic_patch.js  [FIX-5b]
 *
 * Patch ciblé du SVG synoptique GTA à chaque push WebSocket.
 * Appelé par le clientside_callback dans cb_dashboard.py.
 *
 * Principe :
 *   - Le SVG est rendu statiquement une seule fois (create_gta_synoptic_static).
 *   - Ici, seuls les nœuds <text id="syn-*"> sont mis à jour via
 *     getElementById + textContent / setAttribute fill.
 *   - Zéro aller-retour réseau Python, zéro sérialisation JSON→DOM.
 *   - Coût CPU : O(nb_champs) = O(20) au lieu de O(nb_lignes_SVG) = O(500).
 */

/* ── Helpers ──────────────────────────────────────────────────────────── */
function _setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

function _setFill(id, color) {
    const el = document.getElementById(id);
    if (el) el.setAttribute("fill", color);
}

function _setAttr(id, attr, value) {
    const el = document.getElementById(id);
    if (el) el.setAttribute(attr, value);
}

function _alarm(val, lo, hi) {
    return val < lo || val > hi;
}

/* ── Patch principal ──────────────────────────────────────────────────── */
window.patchGtaSynoptic = function(data) {
    if (!data) return;

    /* ── Extraction des valeurs ── */
    const p_hp    = data.pressure_hp          ?? 60.0;
    const t_hp    = data.temperature_hp       ?? 486.0;
    const q_hp    = data.steam_flow_hp        ?? 120.0;
    const p_bp_in = data.pressure_bp_in       ?? 4.5;
    const t_bp    = data.temperature_bp       ?? 226.0;
    const p_bar   = data.pressure_bp_barillet ?? 3.0;
    const q_cond  = data.steam_flow_condenser ?? 74.0;
    const p_cond  = data.pressure_condenser   ?? 0.0064;
    const speed   = data.turbine_speed        ?? 6435.0;
    const eff     = data.efficiency           ?? 92.0;
    const power   = data.active_power         ?? 24.0;
    const pf      = data.power_factor         ?? 0.85;
    const q_mvar  = data.reactive_power       ?? 21.4;
    const s_mva   = data.apparent_power       ?? 41.0;
    const voltage = data.voltage              ?? 10.5;
    const i_a     = data.current_a            ?? 2254.0;
    const status  = data.status               ?? "NORMAL";

    /* ── Couleurs statut ── */
    const STATUS_COL = { NORMAL: "#10b981", DEGRADED: "#f59e0b", CRITICAL: "#ef4444" };
    const sc = STATUS_COL[status] || "#10b981";

    /* ── Alarmes ── */
    const alm_php  = _alarm(p_hp,  55, 65);
    const alm_thp  = _alarm(t_hp, 420, 500);
    const alm_qhp  = _alarm(q_hp, 100, 130);
    const alm_spd  = _alarm(speed, 6300, 6550);
    const alm_pow  = power > 30.0;
    const alm_pf   = _alarm(pf, 0.82, 0.86);
    const alm_eff  = eff < 85.0;
    const alm_pbar = p_bar > 3.5;
    const alm_ia   = i_a > 3000;

    const alt_col  = alm_pow ? "#ef4444" : (power > 24 ? "#f59e0b" : "#10b981");
    const bar_col  = alm_pbar ? "#ef4444" : "#a78bfa";

    /* ── Statut global ── */
    _setText("syn-status", status);
    _setFill("syn-status", sc);

    /* ── Tags source HP ── */
    // Tag pression HP  (syn-php-val contient "valeur <tspan>unité</tspan>")
    const phpValEl = document.getElementById("syn-php-val");
    if (phpValEl) {
        const tspan = phpValEl.querySelector("tspan");
        phpValEl.childNodes[0].textContent = p_hp.toFixed(1) + " ";
        if (tspan) tspan.textContent = "bar";
        phpValEl.setAttribute("fill", alm_php ? "#ef4444" : "#e2e8f0");
    }
    // Rect alarme
    const phpRect = document.getElementById("syn-php-rect");
    if (phpRect) {
        phpRect.setAttribute("fill",   alm_php ? "rgba(239,68,68,0.12)" : "rgba(15,23,42,0.75)");
        phpRect.setAttribute("stroke", alm_php ? "#ef4444" : "#1e3a5f");
    }

    // Tag température HP
    const thpValEl = document.getElementById("syn-thp-val");
    if (thpValEl) {
        const tspan = thpValEl.querySelector("tspan");
        thpValEl.childNodes[0].textContent = t_hp.toFixed(0) + " ";
        if (tspan) tspan.textContent = "°C";
        thpValEl.setAttribute("fill", alm_thp ? "#ef4444" : "#e2e8f0");
    }
    const thpRect = document.getElementById("syn-thp-rect");
    if (thpRect) {
        thpRect.setAttribute("fill",   alm_thp ? "rgba(239,68,68,0.12)" : "rgba(15,23,42,0.75)");
        thpRect.setAttribute("stroke", alm_thp ? "#ef4444" : "#1e3a5f");
    }

    // Tag débit HP
    const qhpValEl = document.getElementById("syn-qhp-val");
    if (qhpValEl) {
        const tspan = qhpValEl.querySelector("tspan");
        qhpValEl.childNodes[0].textContent = q_hp.toFixed(0) + " ";
        if (tspan) tspan.textContent = "T/h";
        qhpValEl.setAttribute("fill", alm_qhp ? "#ef4444" : "#e2e8f0");
    }
    const qhpRect = document.getElementById("syn-qhp-rect");
    if (qhpRect) {
        qhpRect.setAttribute("fill",   alm_qhp ? "rgba(239,68,68,0.12)" : "rgba(15,23,42,0.75)");
        qhpRect.setAttribute("stroke", alm_qhp ? "#ef4444" : "#1e3a5f");
    }

    /* ── Flamme HP ── */
    const flameEl = document.getElementById("syn-hp-flame");
    if (flameEl) {
        flameEl.setAttribute("fill", alm_thp ? "#ef4444" : "#f97316");
        flameEl.textContent = alm_thp ? "⚠" : "🔥";
        flameEl.style.animationPlayState = alm_thp ? "running" : "paused";
    }

    /* ── Étapes turbine ── */
    _setText("syn-hp-stages", `${p_hp.toFixed(0)}→${p_bp_in.toFixed(1)} bar`);
    _setText("syn-bp-label",  `${p_bp_in.toFixed(1)} bar · ${t_bp.toFixed(0)}°C`);

    /* ── Footer turbine ── */
    _setText("syn-speed-val", speed.toFixed(0));
    _setFill("syn-speed-val", alm_spd ? "#ef4444" : "#60a5fa");

    _setText("syn-eff-val", eff.toFixed(1));
    _setFill("syn-eff-val", alm_eff ? "#ef4444" : "#10b981");

    _setText("syn-pbp-val",   p_bp_in.toFixed(2));
    _setText("syn-qcond-val", q_cond.toFixed(0));

    /* ── Tag vitesse arbre ── */
    const spdTagEl = document.getElementById("syn-spd-val");
    if (spdTagEl) {
        const tspan = spdTagEl.querySelector("tspan");
        spdTagEl.childNodes[0].textContent = speed.toFixed(0) + " ";
        if (tspan) tspan.textContent = "RPM";
        spdTagEl.setAttribute("fill", alm_spd ? "#ef4444" : "#e2e8f0");
    }
    const spdRect = document.getElementById("syn-spd-rect");
    if (spdRect) {
        spdRect.setAttribute("fill",   alm_spd ? "rgba(239,68,68,0.12)" : "rgba(15,23,42,0.75)");
        spdRect.setAttribute("stroke", alm_spd ? "#ef4444" : "#1e3a5f");
    }

    /* ── Barillet MP ── */
    _setText("syn-pbar-val",  `${p_bar.toFixed(2)} `);
    _setFill("syn-pbar-val",  bar_col);
    const barilletRect = document.getElementById("syn-barillet-rect");
    if (barilletRect) barilletRect.setAttribute("stroke", bar_col);

    /* ── Condenseur ── */
    _setText("syn-pcond-val",  p_cond.toFixed(4));
    _setText("syn-tbp-val",    t_bp.toFixed(0));
    _setText("syn-qcond2-val", q_cond.toFixed(0));

    /* ── Alternateur ── */
    const altRect = document.getElementById("syn-alt-rect");
    if (altRect) {
        altRect.setAttribute("stroke", alt_col);
        altRect.setAttribute("filter", `url(#${alm_pow ? "gr" : "gg"})`);
    }
    _setFill("syn-alt-tilde", alt_col);

    /* ── Valeurs alternateur ── */
    _setText("syn-power-val", power.toFixed(1));
    _setFill("syn-power-val", alm_pow ? "#ef4444" : alt_col);

    _setText("syn-qmvar-val", q_mvar.toFixed(1));
    _setText("syn-smva-val",  s_mva.toFixed(1));

    _setText("syn-pf-val", pf.toFixed(3));
    _setFill("syn-pf-val", alm_pf ? "#ef4444" : "#fbbf24");

    _setText("syn-ia-val", i_a.toFixed(0));
    _setFill("syn-ia-val", alm_ia ? "#ef4444" : "#10b981");

    _setText("syn-volt-val", voltage.toFixed(1));

    /* ── Tag U sortie ── */
    const uoutEl = document.getElementById("syn-uout-val");
    if (uoutEl) {
        const tspan = uoutEl.querySelector("tspan");
        uoutEl.childNodes[0].textContent = voltage.toFixed(1) + " ";
        if (tspan) tspan.textContent = "kV";
    }

    /* ── Réseau MT : excédent ── */
    _setText("syn-excess-val", Math.max(0, power - 14).toFixed(1));

    /* ── Source BP ── */
    const bpSrcEl = document.getElementById("syn-bp-src-p");
    if (bpSrcEl) {
        const tspan = bpSrcEl.querySelector("tspan");
        bpSrcEl.childNodes[0].textContent = p_bp_in.toFixed(1) + " ";
        if (tspan) tspan.textContent = "bar";
    }
};
