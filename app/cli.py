"""
Marrow -- CLI (Click)

Commands: marrow scan, marrow history, marrow report
Run via: python -m app.cli <command>
"""

import json
import click
from rich.console import Console
from rich.table import Table

from app.correlator import correlate
from app.config import Config
from app import models

console = Console()


@click.group()
def cli():
    """Marrow -- Cloud Cost + Security Optimizer"""
    models.init_db()


@cli.command()
def scan():
    """Run a cost-security scan on the loaded data."""
    console.print("\n[bold cyan]Marrow -- Running Scan[/bold cyan]\n")

    # Load + correlate
    with open(Config.BILLING_DATA_PATH) as f:
        billing = json.load(f)
    with open(Config.FINDINGS_DATA_PATH) as f:
        findings = json.load(f)
    correlated = correlate(billing, findings)

    console.print("  [cyan]Querying Fireworks AI for recommendations...[/cyan]")
    from app.reasoner import generate_recommendations
    recs = generate_recommendations(correlated)
    
    # Save to DB
    scan_id = models.save_scan(correlated)
    models.save_recommendations(scan_id, recs)
    
    console.print("  [cyan]Generating Executive Summary...[/cyan]")
    from app.reasoner import generate_executive_summary
    summary = generate_executive_summary(recs)
    models.update_scan_summary(scan_id, summary)

    # Summary
    total_cost = sum(r["monthly_cost_usd"] for r in correlated)
    total_findings = sum(r["finding_count"] for r in correlated)
    high_risk = sum(1 for r in correlated if r["total_risk_score"] >= 50)
    total_savings = sum(r.get("monthly_savings_usd", 0) for r in recs)

    console.print(f"  [green]Scan #{scan_id} saved.[/green]")
    console.print(f"  Resources scanned: {len(correlated)}")
    console.print(f"  Total monthly cost: [green]${total_cost:,.2f}[/green]")
    console.print(f"  Security findings:  [yellow]{total_findings}[/yellow]")
    console.print(f"  High-risk resources: [red]{high_risk}[/red]")
    console.print(f"  Identified Savings: [bold green]${total_savings:,.2f}/mo[/bold green]\n")


@cli.command()
def history():
    """Show past scan history."""
    with models.get_connection() as db:
        scans = db.execute("SELECT * FROM scans ORDER BY timestamp DESC").fetchall()

    if not scans:
        console.print("\n  [dim]No scans yet. Run [bold]python -m app.cli scan[/bold] first.[/dim]\n")
        return

    console.print("\n[bold cyan]Marrow -- Scan History[/bold cyan]\n")

    table = Table(show_lines=True, header_style="bold magenta")
    table.add_column("Scan ID", justify="center", style="cyan")
    table.add_column("Timestamp", style="white")
    table.add_column("Resources", justify="center", style="white")
    table.add_column("Monthly Cost", justify="right", style="green")
    table.add_column("Total Risk", justify="center", style="red")

    for s in scans:
        from datetime import datetime
        ts = s["timestamp"]
        try:
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass

        table.add_row(
            str(s["id"]),
            ts,
            str(s["resource_count"]),
            f"${s['total_monthly_cost']:,.2f}",
            str(s["total_risk_score"]),
        )

    console.print(table)
    console.print()


@cli.command()
@click.option("--scan-id", type=int, default=None, help="ID of the scan to generate a report for. Defaults to latest.")
def report(scan_id):
    """Generate a PDF report for a given scan."""
    from app.report import generate_report
    
    try:
        buffer = generate_report(scan_id)
        
        # Determine actual scan ID for filename if latest was used
        if scan_id is None:
            with models.get_connection() as db:
                scan = db.execute("SELECT id FROM scans ORDER BY timestamp DESC LIMIT 1").fetchone()
                if not scan:
                    console.print("\n  [bold red]Error:[/bold red] No scans found in the database. Run scan first.\n")
                    return
                actual_id = scan["id"]
        else:
            actual_id = scan_id
            
        filename = f"marrow_report_{actual_id}.pdf"
        from app.config import PROJECT_ROOT
        reports_dir = PROJECT_ROOT / "reports"
        reports_dir.mkdir(exist_ok=True)
        filepath = reports_dir / filename
        
        with open(filepath, "wb") as f:
            f.write(buffer.getvalue())
            
        console.print(f"\n  [bold green]Report generated successfully:[/bold green] {filepath}\n")
    except ValueError as e:
        console.print(f"\n  [bold red]Error:[/bold red] {e}\n")
    except Exception as e:
        console.print(f"\n  [bold red]Failed to generate report:[/bold red] {e}\n")


if __name__ == "__main__":
    cli()
