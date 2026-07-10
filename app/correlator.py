"""
Marrow — Correlator

Joins billing data and security findings by resource_id.
Pure Python — no AI, no Flask, no database.
"""

import json
from pathlib import Path
from collections import defaultdict

# ── Risk scoring weights (tune these as needed) ──────────────────────────
SEVERITY_SCORES: dict[str, int] = {
    "CRITICAL": 40,
    "HIGH": 25,
    "MEDIUM": 10,
    "LOW": 5,
}


def load_billing(path: str | Path) -> list[dict]:
    """Load billing data from a JSON file.

    Args:
        path: Path to the billing JSON file.

    Returns:
        List of billing resource dicts.
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


def load_findings(path: str | Path) -> list[dict]:
    """Load security findings from a JSON file.

    Args:
        path: Path to the findings JSON file.

    Returns:
        List of finding dicts (flat array, not grouped).
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


def correlate(
    billing: list[dict],
    findings: list[dict],
) -> list[dict]:
    """Join billing resources with their security findings by resource_id.

    For each billing resource, attaches:
        - findings: list of matching finding dicts
        - finding_count: number of findings
        - total_risk_score: sum of severity scores across all findings

    Args:
        billing: List of billing resource dicts (each must have 'resource_id').
        findings: Flat list of finding dicts (each must have 'resource_id' and 'severity').

    Returns:
        List of enriched resource dicts, sorted by total_risk_score descending.
    """
    # Group findings by resource_id for O(1) lookup
    findings_map: dict[str, list[dict]] = defaultdict(list)
    for finding in findings:
        findings_map[finding["resource_id"]].append(finding)

    correlated: list[dict] = []

    for resource in billing:
        rid = resource["resource_id"]
        matched_findings = findings_map.get(rid, [])

        # Calculate total risk score from severity weights
        total_risk_score = sum(
            SEVERITY_SCORES.get(f["severity"], 0) for f in matched_findings
        )

        enriched = {
            **resource,
            "findings": matched_findings,
            "finding_count": len(matched_findings),
            "total_risk_score": total_risk_score,
        }
        correlated.append(enriched)

    # Sort by risk score descending — riskiest resources first
    correlated.sort(key=lambda r: r["total_risk_score"], reverse=True)

    return correlated


# ── Standalone execution: run on sample data and print Rich table ────────
if __name__ == "__main__":
    from rich.console import Console
    from rich.table import Table
    from app.config import Config

    console = Console()

    console.print("\n[bold cyan]Marrow -- Correlator (Phase 1)[/bold cyan]\n")

    # Load data
    billing = load_billing(Config.BILLING_DATA_PATH)
    findings = load_findings(Config.FINDINGS_DATA_PATH)

    console.print(
        f"  Loaded [green]{len(billing)}[/green] billing resources, "
        f"[yellow]{len(findings)}[/yellow] security findings\n"
    )

    # Correlate
    results = correlate(billing, findings)

    # Build Rich table
    table = Table(
        title="Correlated Resources",
        title_style="bold white",
        show_lines=True,
        header_style="bold magenta",
    )
    table.add_column("Resource ID", style="cyan", max_width=28)
    table.add_column("Service", style="white")
    table.add_column("Monthly Cost", justify="right", style="green")
    table.add_column("Utilization %", justify="right", style="yellow")
    table.add_column("Findings", justify="center", style="white")
    table.add_column("Risk Score", justify="center", style="white")

    for r in results:
        # Color-code risk score
        score = r["total_risk_score"]
        if score >= 50:
            risk_style = "[bold red]"
        elif score >= 20:
            risk_style = "[bold yellow]"
        elif score > 0:
            risk_style = "[dim white]"
        else:
            risk_style = "[green]"

        # Color-code findings count
        fc = r["finding_count"]
        if fc >= 3:
            fc_style = "[bold red]"
        elif fc >= 1:
            fc_style = "[yellow]"
        else:
            fc_style = "[green]"

        table.add_row(
            r["resource_id"],
            r["service"],
            f"${r['monthly_cost_usd']:.2f}",
            f"{r['utilization_pct']:.1f}%",
            f"{fc_style}{fc}[/]",
            f"{risk_style}{score}[/]",
        )

    console.print(table)

    # Summary stats
    total_cost = sum(r["monthly_cost_usd"] for r in results)
    total_findings = sum(r["finding_count"] for r in results)
    high_risk = sum(1 for r in results if r["total_risk_score"] >= 50)

    console.print(f"\n  [bold]Total monthly spend:[/bold] [green]${total_cost:,.2f}[/green]")
    console.print(f"  [bold]Total findings:[/bold] [yellow]{total_findings}[/yellow]")
    console.print(f"  [bold]High-risk resources (score >= 50):[/bold] [red]{high_risk}[/red]\n")
