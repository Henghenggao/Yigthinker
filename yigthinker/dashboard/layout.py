from __future__ import annotations
from dash import Dash, dcc, html


def create_dash_app(server=True) -> Dash:
    """Create the Plotly Dash app. Pass a Flask instance for integration, or True to auto-create."""
    app = Dash(
        __name__,
        server=server,
        url_base_pathname="/dashboard/",
        suppress_callback_exceptions=True,
    )

    app.layout = html.Div([
        html.Div([
            html.H2("Yigthinker", style={"color": "#3b82f6", "margin": "0"}),
            html.Div([
                html.A("Live Analysis", href="#"),
                html.A("Chart Library", href="#"),
                html.A("Reports", href="#"),
            ], style={"display": "flex", "gap": "20px"}),
        ], style={
            "display": "flex", "justifyContent": "space-between", "alignItems": "center",
            "padding": "12px 24px", "background": "#0f172a", "color": "white",
        }),
        html.Div(id="kpi-cards", children=[], style={
            "display": "flex", "gap": "16px", "padding": "16px 24px",
        }),
        html.Div(id="chart-grid", children=[
            html.P("No charts yet. Run analysis in Yigthinker CLI to populate.",
                   style={"color": "#64748b", "padding": "24px"}),
        ], style={"padding": "0 24px"}),
        dcc.Interval(id="poll-interval", interval=2000, n_intervals=0),
        dcc.Store(id="dashboard-store", data=[]),
    ], style={"background": "#0f172a", "minHeight": "100vh", "fontFamily": "sans-serif"})

    return app
