/**
 * assets/synoptic_patch.js  [FIX-BP-LAYOUT]
 *
 * Patch ciblé du SVG synoptique GTA à chaque push WebSocket.
 * Appelé par le clientside_callback dans cb_dashboard.py.
 *
 * CHANGEMENTS BP LAYOUT :
 *   - BARILLET BP positionné en position principale (sous VBP)
 *   - CONDENSEUR à droite du BARILLET BP
 *   - 4 flux BP affichés :
 *       1. VP HP → Condenseur (74 T/h)
 *       2. VP BP 3 bar → Barillet
 *       3. VP BP Chauffage eau AS
 *       4. VP BP Surchauffeur AS
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
    const p_bar_mp = data.pressure_mp_barillet ?? 9.5;
    const p_bar_bp = data.pressure_bp_barillet ?? 3.0;
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
    const v_mp    = data.valve_mp             ?? 50.0;
    const v_v1    = data.valve_v1             ?? 100.0;
    const v_bp    = data.valve_bp             ?? 80.0;

    /* ── Distribution flux BP — calculée localement ── */
    const q_hp_eff      = q_hp * (v_v1 / 100.0);
    const q_extract_mp  = q_hp_eff * 0.20 * (v_mp / 100.0);
    const q_barillet    = q_extract_mp * 0.50;
    const q_chauffage   = q_extract_mp * 0.30;
    const q_surchauffeur = q_extract_mp * 0.20;

    /* ── Mécanique & Auxiliaires ── */
    const freq    = data.grid_frequency       ?? 50.0;
    const vib_fwd = data.vib_bearing_fwd      ?? 2.1;
    const vib_aft = data.vib_bearing_aft      ?? 1.8;
    const temp_fwd= data.temp_bearing_fwd     ?? 74.0;
    const temp_aft= data.temp_bearing_aft     ?? 76.0;
    const oil_p   = data.lube_oil_press       ?? 1.5;
    const oil_t   = data.lube_oil_temp        ?? 45.0;
    const axial   = data.axial_displacement   ?? 0.2;
    const casing  = data.casing_expansion     ?? 5.0;

    const v1_tgt  = data.valve_v1_target      ?? (data.valve_v1 ?? 100);
    const v2_tgt  = data.valve_v2_target      ?? (data.valve_v2 ?? 100);
    const v3_tgt  = data.valve_v3_target      ?? (data.valve_v3 ?? 100);
    const vmp_tgt = data.valve_mp_target      ?? (data.valve_mp ?? 50);
    const vbp_tgt = data.valve_bp_target      ?? (data.valve_bp ?? 80);

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
    const alm_pbar_mp = p_bar_mp < 8.0 || p_bar_mp > 11.0;
    const alm_pbar_bp = p_bar_bp > 3.5;
    const alm_ia   = i_a > 3000;

    const alt_col  = alm_pow ? "#ef4444" : (power > 24 ? "#f59e0b" : "#10b981");
    const bar_col  = alm_pbar_mp ? "#ef4444" : "#a78bfa";

    /* ── Statut global ── */
    _setText("syn-status", status);
    _setFill("syn-status", sc);

    /* ── Tags source HP ── */
    const phpValEl = document.getElementById("syn-php-val");
    if (phpValEl) {
        const tspan = phpValEl.querySelector("tspan");
        phpValEl.childNodes[0].textContent = p_hp.toFixed(1) + " ";
        if (tspan) tspan.textContent = "bar";
        phpValEl.setAttribute("fill", alm_php ? "#ef4444" : "#e2e8f0");
    }
    const phpRect = document.getElementById("syn-php-rect");
    if (phpRect) {
        phpRect.setAttribute("fill",   alm_php ? "rgba(239,68,68,0.12)" : "rgba(15,23,42,0.75)");
        phpRect.setAttribute("stroke", alm_php ? "#ef4444" : "#1e3a5f");
    }

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
    _setText("syn-pbar-mp-val", `${p_bar_mp.toFixed(2)} `);
    _setFill("syn-pbar-mp-val", bar_col);
    const mpRect = document.getElementById("syn-barillet-mp-rect");
    if (mpRect) mpRect.setAttribute("stroke", bar_col);

    /* ── Barillet BP ── */
    _setText("syn-pbar-bp-val", `${p_bar_bp.toFixed(2)} `);
    const bpBarRect = document.getElementById("syn-barillet-bp-rect");
    if (bpBarRect) {
        const col = alm_pbar_bp ? "#ef4444" : "#38bdf8";
        bpBarRect.setAttribute("stroke", col);
        bpBarRect.setAttribute("filter", alm_pbar_bp ? "url(#gr)" : "url(#gb)");
    }
    /* Blink alarme barillet BP */
    const bpBlink = document.getElementById("syn-barillet-bp-blink");
    if (bpBlink) bpBlink.setAttribute("display", alm_pbar_bp ? "block" : "none");

    /* ── 4 Flux BP distribution ── */
    _setText("syn-q-barillet",     q_barillet.toFixed(1));
    _setText("syn-q-chauffage",    q_chauffage.toFixed(1));
    _setText("syn-q-surchauffeur", q_surchauffeur.toFixed(1));

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

    _setText("syn-power-val", power.toFixed(1));
    _setFill("syn-power-val", alm_pow ? "#ef4444" : alt_col);
    _setText("syn-qmvar-val", q_mvar.toFixed(1));
    _setText("syn-smva-val",  s_mva.toFixed(1));
    _setText("syn-pf-val", pf.toFixed(3));
    _setFill("syn-pf-val", alm_pf ? "#ef4444" : "#fbbf24");
    _setText("syn-ia-val", i_a.toFixed(0));
    _setFill("syn-ia-val", alm_ia ? "#ef4444" : "#10b981");
    _setText("syn-volt-val", voltage.toFixed(1));

    /* ── Tag P sortie ── */
    const poutValEl = document.getElementById("syn-pout-val");
    if (poutValEl) {
        const tspan = poutValEl.querySelector("tspan");
        poutValEl.childNodes[0].textContent = power.toFixed(1) + " ";
        if (tspan) tspan.textContent = "MW";
        poutValEl.setAttribute("fill", alm_pow ? "#ef4444" : "#e2e8f0");
    }
    const poutRect = document.getElementById("syn-pout-rect");
    if (poutRect) {
        poutRect.setAttribute("fill",   alm_pow ? "rgba(239,68,68,0.12)" : "rgba(15,23,42,0.75)");
        poutRect.setAttribute("stroke", alm_pow ? "#ef4444" : "#1e3a5f");
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

    /* ── Auxiliaires mécaniques ── */
    const freqEl = document.getElementById("syn-freq-val");
    if (freqEl) {
        const tspan = freqEl.querySelector("tspan");
        freqEl.childNodes[0].textContent = freq.toFixed(2) + " ";
        if(tspan) tspan.textContent = "Hz · 2 pôles";
    }

    _setText("syn-vibfwd-val", vib_fwd.toFixed(1));
    _setFill("syn-vibfwd-val", vib_fwd > 4.5 ? "#ef4444" : "#fbbf24");
    _setText("syn-vibaft-val", vib_aft.toFixed(1));
    _setFill("syn-vibaft-val", vib_aft > 4.5 ? "#ef4444" : "#fbbf24");
    _setText("syn-tempfwd-val", temp_fwd.toFixed(0));
    _setText("syn-tempaft-val", temp_aft.toFixed(0));
    _setText("syn-oilp-val", oil_p.toFixed(2));
    _setText("syn-oilt-val", oil_t.toFixed(1));
    _setText("syn-axial-val", "+" + axial.toFixed(2));
    _setText("syn-casing-val", casing.toFixed(1));

    /* ── Vannes ── */
    _setText("syn-v1-tgt", "Cible:" + v1_tgt.toFixed(0) + "%");
    _setText("syn-v2-tgt", "Cible:" + v2_tgt.toFixed(0) + "%");
    _setText("syn-v3-tgt", "Cible:" + v3_tgt.toFixed(0) + "%");
    _setText("syn-vmp-tgt", "Cible:" + vmp_tgt.toFixed(0) + "%");
    _setText("syn-vbp-tgt", "Cible:" + vbp_tgt.toFixed(0) + "%");
    _setText("syn-v1-pct",  (data.valve_v1 ?? 100).toFixed(0) + "%");
    _setText("syn-v2-pct",  (data.valve_v2 ?? 100).toFixed(0) + "%");
    _setText("syn-v3-pct",  (data.valve_v3 ?? 100).toFixed(0) + "%");
    _setText("syn-vmp-pct", (data.valve_mp ?? 50).toFixed(0) + "%");
    _setText("syn-vbp-pct", (data.valve_bp ?? 80).toFixed(0) + "%");

    // ── Animations dynamiques — turbine / réducteur / flux ────────────────────

    /* Condition d'arrêt : débit < 5 T/h OU vanne V1 < 5% OU vitesse < 100 RPM */
    const v1_pct   = data.valve_v1 ?? 100;
    const isTurning = q_hp > 5 && v1_pct > 5 && speed > 100;

    /* Durée de rotation : ralentit avec la vitesse, s'arrête si isTurning=false */
    const rpm_norm = Math.min(Math.max((speed - 5500) / 1500, 0), 1);
    const spinDur  = isTurning
        ? (Math.max(0.4, 2.0 - rpm_norm * 1.6)).toFixed(2) + 's'
        : '9999s';   // durée infinie = quasi-arrêt visuel

    document.querySelectorAll('.spin').forEach(el => {
        el.style.animationDuration  = spinDur;
        el.style.animationPlayState = isTurning ? 'running' : 'paused';
    });

    /* Flux vapeur HP / BP : lié au débit */
    const flowDur = (q_hp > 5 && v1_pct > 5)
        ? (Math.max(0.3, 120.0 / Math.max(1, q_hp))).toFixed(2) + 's'
        : '9999s';

    document.querySelectorAll('.flow-hp, .flow-bp').forEach(el => {
        el.style.animationDuration  = flowDur;
        el.style.animationPlayState = (q_hp > 5 && v1_pct > 5) ? 'running' : 'paused';
    });

    /* Flux électrique : lié à la puissance active */
    document.querySelectorAll('.flow-el').forEach(el => {
        el.style.animationPlayState = power > 0.5 ? 'running' : 'paused';
        el.style.animationDuration  = power > 0.5 ? '0.8s' : '9999s';
    });
};