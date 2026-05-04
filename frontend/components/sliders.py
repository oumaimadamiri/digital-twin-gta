"""
components/sliders.py — Composant slider réutilisable pour le contrôle de vannes.
Partagé par layouts/simulation.py et layouts/control.py.
"""
from dash import html, dcc


def slider_row(valve_id, label, default, color, description):
    """
    Retourne une rangée label + valeur + slider pour une vanne.

    Args:
        valve_id:    identifiant court (ex: "v1")
        label:       libellé affiché (ex: "V1 — Admission HP")
        default:     position initiale (%)
        color:       couleur CSS du libellé
        description: texte descriptif sous le label
    """
    return html.Div([
        html.Div([
            html.Span(label, className="slider-label-text", style={"color": color}),
            html.Div([
                html.Span(id=f"val-{valve_id}", className="slider-val-num"),
                html.Span("%", className="slider-val-unit"),
            ]),
        ], className="slider-label-row"),
        html.Div(description,
                 style={"fontSize": "9.5px", "color": "#334155",
                        "fontFamily": "Share Tech Mono", "marginBottom": "4px"}),
        dcc.Slider(
            id=f"slider-{valve_id}",
            min=0, max=100, step=1, value=default,
            marks={0: "0", 25: "25", 50: "50", 75: "75", 100: "100"},
            className="custom-slider",
            tooltip={"placement": "bottom", "always_visible": False},
        ),
    ], className="slider-container")
