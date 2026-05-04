"""
components/sidebar.py — Navigation latérale et topbar
"""
from dash import html, dcc


def create_sidebar(active_path="/"):
    def get_class(path):
        return "nav-item active" if active_path == path else "nav-item"
        
    return html.Div([
        # SECTION GAUCHE : Logo
        html.Div([
            html.Div(html.Span("⚙", className="nav-icon"), className="logo-icon-wrap"),
            html.Div([
                html.Div("GTA Platform", className="logo-title"),
                html.Div("CONTRÔLE INDUSTRIEL", className="logo-sub"),
            ], className="logo-text-wrap"),
        ], className="sidebar-logo"),
        
        # SECTION CENTRE : Liens de navigation
        html.Div([
            dcc.Link([html.Span("⬡", className="nav-icon"), html.Span("Dashboard")],
                     href="/", className=get_class("/"), id="nav-dashboard"),
            dcc.Link([html.Span("⚙", className="nav-icon"), html.Span("Simulation")],
                     href="/simulation", className=get_class("/simulation"), id="nav-simulation"),
            dcc.Link([html.Span("🎛", className="nav-icon"), html.Span("Ctrl Commande")],
                     href="/control", className=get_class("/control"), id="nav-control"),
            dcc.Link([html.Span("📈", className="nav-icon"), html.Span("Analyse")],
                     href="/analysis", className=get_class("/analysis"), id="nav-analysis"),
            dcc.Link([html.Span("🤖", className="nav-icon"), html.Span("Module IA")],
                     href="/ai", className=get_class("/ai"), id="nav-ai"),
            dcc.Link([html.Span("📋", className="nav-icon"), html.Span("Journal")],
                     href="/journal", className=get_class("/journal"), id="nav-journal"),
            dcc.Link([html.Span("⚴", className="nav-icon"), html.Span("Paramètres")],
                     href="/settings", className=get_class("/settings"), id="nav-settings"),
        ], style={"display": "flex", "alignItems": "center"}),
                 
        # SECTION DROITE : Utilisateur
        html.Div([
            html.Div([
                html.Div("Ex exploitation", style={"color": "var(--text)", "fontSize": "12px", "fontWeight": "600", "textAlign": "right"}),
                html.Div("ID: 4829", style={"color": "var(--text3)", "fontSize": "10px", "textAlign": "right"}),
            ], className="footer-text"),
            html.Div("IE", className="avatar"),
        ], className="sidebar-footer"),
    ], className="sidebar")


# def create_topbar(page_title, subtitle=""):
#     return html.Div([
#         html.Div([
#             html.Span(page_title, className="topbar-title"),
#             html.Span(f" / {subtitle}", className="topbar-title-sub") if subtitle else None
#         ]),
#         html.Div([
#             html.Div([
#                 html.Span("Dernière mise à jour", style={"color": "var(--text3)", "fontSize": "10px", "marginBottom": "2px"}),
#                 html.Div(id="topbar-time", className="time-val")
#             ], className="topbar-time"),
#             html.Div("● CONNECTÉ", className="status-button online", id="topbar-status-pill"),
#         ], className="topbar-right"),
#     ], className="topbar")