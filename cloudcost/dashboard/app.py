"""
CloudCost Dashboard — interactive Plotly Dash web UI for multi-cloud cost visualization.
"""

from __future__ import annotations

try:
    import dash
    from dash import dcc, html
    import plotly.express as px
    import plotly.graph_objects as go
    import pandas as pd
    HAS_DASH = True
except ImportError:
    HAS_DASH = False


def create_app():
    """Create and configure the Dash application."""
    if not HAS_DASH:
        raise ImportError(
            "Dashboard dependencies not installed. Run: pip install cloudcost[dashboard]"
        )

    app = dash.Dash(__name__, title="CloudCost — Multi-Cloud FinOps")

    app.layout = html.Div([
        # Header
        html.Div([
            html.H1("💰 CloudCost Dashboard", style={"margin": "0", "color": "#212529"}),
            html.P("Multi-cloud FinOps — AWS & Alibaba Cloud Cost Optimization",
                   style={"margin": "5px 0 0", "color": "#6c757d"}),
        ], style={
            "padding": "20px 30px",
            "background": "white",
            "borderBottom": "3px solid #0d6efd",
            "marginBottom": "20px",
        }),

        # Summary cards
        html.Div([
            html.Div([
                html.H3("Monthly Savings", style={"margin": "0", "fontSize": "14px", "opacity": "0.9"}),
                html.Div("$0.00", id="monthly-savings", style={"fontSize": "32px", "fontWeight": "bold"}),
            ], className="card", style={
                "flex": "1", "padding": "20px", "borderRadius": "8px", "color": "white",
                "background": "linear-gradient(135deg, #28a745, #20c997)",
            }),
            html.Div([
                html.H3("Annual Projection", style={"margin": "0", "fontSize": "14px", "opacity": "0.9"}),
                html.Div("$0.00", id="annual-savings", style={"fontSize": "32px", "fontWeight": "bold"}),
            ], className="card", style={
                "flex": "1", "padding": "20px", "borderRadius": "8px", "color": "white",
                "background": "linear-gradient(135deg, #0d6efd, #6610f2)",
            }),
            html.Div([
                html.H3("Findings", style={"margin": "0", "fontSize": "14px", "opacity": "0.9"}),
                html.Div("0", id="total-findings", style={"fontSize": "32px", "fontWeight": "bold"}),
            ], className="card", style={
                "flex": "1", "padding": "20px", "borderRadius": "8px", "color": "white",
                "background": "linear-gradient(135deg, #fd7e14, #e8590c)",
            }),
        ], style={"display": "flex", "gap": "20px", "margin": "0 30px 20px"}),

        # Charts row
        html.Div([
            # Savings by service
            html.Div([
                html.H3("Savings by Service", style={"marginTop": "0"}),
                dcc.Graph(id="by-service-chart", config={"displayModeBar": False}),
            ], style={"flex": "1", "background": "white", "padding": "20px", "borderRadius": "8px"}),

            # Savings by cloud
            html.Div([
                html.H3("By Cloud Provider", style={"marginTop": "0"}),
                dcc.Graph(id="by-cloud-chart", config={"displayModeBar": False}),
            ], style={"flex": "1", "background": "white", "padding": "20px", "borderRadius": "8px"}),
        ], style={"display": "flex", "gap": "20px", "margin": "0 30px 20px"}),

        # Findings table
        html.Div([
            html.H3("All Findings", style={"marginTop": "0"}),
            html.Div(id="findings-table"),
        ], style={"margin": "0 30px", "background": "white", "padding": "20px", "borderRadius": "8px"}),

        # Refresh button
        html.Div([
            html.Button("🔄 Refresh", id="refresh-btn", style={
                "padding": "10px 20px", "background": "#0d6efd", "color": "white",
                "border": "none", "borderRadius": "6px", "cursor": "pointer", "fontSize": "14px",
            }),
        ], style={"textAlign": "center", "margin": "20px"}),

        # Footer
        html.Div([
            html.P("CloudCost v0.1.0 — open source multi-cloud FinOps", style={"color": "#6c757d", "fontSize": "12px"}),
        ], style={"textAlign": "center", "padding": "20px"}),
    ], style={"fontFamily": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
               "background": "#f8f9fa", "minHeight": "100vh"})

    # Callbacks for live data
    @app.callback(
        [
            dash.Output("monthly-savings", "children"),
            dash.Output("annual-savings", "children"),
            dash.Output("total-findings", "children"),
            dash.Output("by-service-chart", "figure"),
            dash.Output("by-cloud-chart", "figure"),
            dash.Output("findings-table", "children"),
        ],
        [dash.Input("refresh-btn", "n_clicks")],
    )
    def update_dashboard(n_clicks):
        """Refresh dashboard data."""
        findings = _gather_findings()

        total = sum(f.get("estimated_monthly_savings_usd", 0) for f in findings)
        monthly = f"${total:,.2f}"
        annual = f"${total * 12:,.2f}"
        count = str(len(findings))

        # By service chart
        df = pd.DataFrame(findings) if findings else pd.DataFrame(columns=["service", "estimated_monthly_savings_usd"])
        if not df.empty and "service" in df.columns and "estimated_monthly_savings_usd" in df.columns:
            by_service = df.groupby("service")["estimated_monthly_savings_usd"].sum().reset_index()
            svc_fig = px.bar(by_service, x="service", y="estimated_monthly_savings_usd",
                            title="", color="service",
                            labels={"estimated_monthly_savings_usd": "Monthly Savings ($)"})
            svc_fig.update_layout(showlegend=False, margin=dict(l=10, r=10, t=10, b=10))
        else:
            svc_fig = go.Figure()
            svc_fig.add_annotation(text="No data — connect cloud APIs to populate",
                                   xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)

        # By cloud chart
        if not df.empty:
            df["cloud"] = df["service"].apply(lambda s: "AWS" if s in ("ec2", "rds", "s3", "ebs", "eip", "nat", "elb", "lambda", "elasticache") else "Alibaba")
            by_cloud = df.groupby("cloud")["estimated_monthly_savings_usd"].sum().reset_index()
            cloud_fig = px.pie(by_cloud, values="estimated_monthly_savings_usd", names="cloud",
                              title="", hole=0.4)
            cloud_fig.update_layout(margin=dict(l=10, r=10, t=10, b=10))
        else:
            cloud_fig = go.Figure()
            cloud_fig.add_annotation(text="No data yet", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)

        # Table
        if findings:
            table_rows = []
            for f in findings[:20]:
                sev = f.get("severity", "low")
                color = {"high": "#dc3545", "medium": "#fd7e14", "low": "#ffc107"}.get(sev, "#6c757d")
                table_rows.append(html.Tr([
                    html.Td(html.Span(sev.upper(), style={
                        "background": color, "color": "white", "padding": "2px 8px",
                        "borderRadius": "4px", "fontSize": "11px", "fontWeight": "bold",
                    })),
                    html.Td(f.get("service", "")),
                    html.Td(f.get("region", "")),
                    html.Td(f.get("resource_id", "")[:30]),
                    html.Td(f.get("detail", "")[:80]),
                    html.Td(f"${f.get('estimated_monthly_savings_usd', 0):,.2f}",
                           style={"textAlign": "right"}),
                ]))

            table = html.Table(
                [html.Thead(html.Tr([
                    html.Th("Severity"), html.Th("Service"), html.Th("Region"),
                    html.Th("Resource"), html.Th("Detail"), html.Th("Savings/mo"),
                ]))] + [html.Tbody(table_rows)],
                style={"width": "100%", "borderCollapse": "collapse"},
            )
        else:
            table = html.P("No findings yet. Run 'cloudcost aws scan' or 'cloudcost aliyun scan' to populate data.",
                          style={"color": "#6c757d"})

        return monthly, annual, count, svc_fig, cloud_fig, table

    return app


def _gather_findings() -> list[dict]:
    """Gather findings from both clouds."""
    findings = []
    try:
        from cloudcost.aws.scanner import AWSScanner
        findings.extend(AWSScanner().scan())
    except Exception:
        pass
    try:
        from cloudcost.aliyun.scanner import AliyunScanner
        findings.extend(AliyunScanner().scan())
    except Exception:
        pass
    return findings
