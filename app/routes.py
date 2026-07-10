"""
Marrow — Flask Routes (API & Dashboard Layer)

Blueprint exposing all web endpoints for the Marrow platform.

Endpoints:
    GET  /                     – Main dashboard with latest scan results
    GET  /health               – Healthcheck for uptime monitoring
    GET  /history              – Historical scan listing
    POST /scan                 – Trigger a new correlation + reasoning run
    GET  /api/recommendations  – JSON API for programmatic access
    GET  /report/<scan_id>     – Download PDF report for a specific scan
    GET  /report/latest        – Download PDF report for the most recent scan
"""
import json
import logging
from flask import Blueprint, render_template, jsonify, flash, redirect, url_for, send_file
from app import models
from app.config import Config
from app.correlator import correlate
from app.reasoner import generate_recommendations

bp = Blueprint("main", __name__)

@bp.route("/health")
def health():
    """Healthcheck endpoint for Render uptime monitoring and load balancer probes."""
    return {"status": "ok"}

@bp.route("/")
def dashboard():
    """Render the main command center dashboard.

    Loads the latest scan, its recommendations, and re-correlates
    the raw data to compute live attack-vector metrics for display.
    """
    with models.get_connection() as db:
        latest_scan = db.execute("SELECT * FROM scans ORDER BY timestamp DESC LIMIT 1").fetchone()
        
        if latest_scan:
            recs = db.execute(
                "SELECT * FROM recommendations WHERE scan_id = ? ORDER BY priority_score DESC", 
                (latest_scan["id"],)
            ).fetchall()
            
            try:
                with open(Config.BILLING_DATA_PATH) as f:
                    billing = json.load(f)
                with open(Config.FINDINGS_DATA_PATH) as f:
                    findings = json.load(f)
            except (IOError, json.JSONDecodeError):
                billing, findings = [], []
                
            resources = correlate(billing, findings)
            
            # Calculate actual attack vectors removed based on acted-upon resources
            vectors_removed = 0
            for r in resources:
                rec = next((x for x in recs if x["resource_id"] == r["resource_id"]), None)
                if rec and rec["action"] in ["terminate", "patch", "restrict-access"]:
                    vectors_removed += r["finding_count"]
                    
            # Fetch history for the trend chart (oldest first for chronological graphing)
            history = db.execute("SELECT * FROM scans ORDER BY timestamp ASC LIMIT 10").fetchall()
            
            return render_template(
                "index.html", 
                resources=resources, 
                recommendations=recs, 
                latest_scan=latest_scan,
                history=history,
                vectors_removed=vectors_removed
            )
            
    return render_template("index.html", resources=[], recommendations=[], latest_scan=None, history=[], vectors_removed=0)

@bp.route("/history")
def history():
    with models.get_connection() as db:
        scans = db.execute("SELECT * FROM scans ORDER BY timestamp DESC").fetchall()
    return render_template("history.html", scans=scans)

@bp.route("/scan", methods=["POST"])
def scan():
    """Trigger the full Marrow pipeline: ingest → correlate → reason → persist.

    This is the core action endpoint. It runs the complete three-phase
    pipeline (correlator, LLM reasoner, persistence) and redirects
    back to the dashboard with flash feedback.
    """
    try:
        with open(Config.BILLING_DATA_PATH) as f:
            billing = json.load(f)
        with open(Config.FINDINGS_DATA_PATH) as f:
            findings = json.load(f)
            
        correlated = correlate(billing, findings)
        recommendations = generate_recommendations(correlated)
        
        scan_id = models.save_scan(correlated)
        models.save_recommendations(scan_id, recommendations)
        
        from app.reasoner import generate_executive_summary
        summary = generate_executive_summary(recommendations)
        models.update_scan_summary(scan_id, summary)
        
        flash(f"Scan #{scan_id} completed successfully. Found {len(recommendations)} recommendations.")
        
    except Exception:
        logging.exception("Error during scan")
        flash("An internal error occurred during the scan. Please check the server logs.")
        
    return redirect(url_for("main.dashboard"))

@bp.route("/api/recommendations")
def api_recommendations():
    """JSON API endpoint for programmatic access to the latest recommendations.

    Returns the full recommendation set from the most recent scan,
    suitable for integration with external dashboards or CI/CD pipelines.
    """
    with models.get_connection() as db:
        latest_scan = db.execute("SELECT * FROM scans ORDER BY timestamp DESC LIMIT 1").fetchone()
        if not latest_scan:
            return jsonify({"error": "No scans found"}), 404
            
        recs = db.execute("SELECT * FROM recommendations WHERE scan_id = ?", (latest_scan["id"],)).fetchall()
        return jsonify({
            "scan_id": latest_scan["id"],
            "timestamp": latest_scan["timestamp"],
            "recommendations": [dict(r) for r in recs]
        })

@bp.route("/report/<int:scan_id>")
@bp.route("/report/latest")
def download_report(scan_id=None):
    """Generate and serve a PDF report for stakeholder handoff.

    Supports both specific scan IDs and a convenience '/report/latest'
    shortcut for quick access to the most recent analysis.
    """
    from app.report import generate_report
    try:
        buffer = generate_report(scan_id)
        filename = f"marrow_report_{scan_id if scan_id else 'latest'}.pdf"
        return send_file(
            buffer,
            as_attachment=True,
            download_name=filename,
            mimetype='application/pdf'
        )
    except ValueError as e:
        flash(str(e))
        return redirect(url_for("main.dashboard"))
    except Exception as e:
        logging.error(f"Failed to generate report: {e}")
        flash("Failed to generate report.")
        return redirect(url_for("main.dashboard"))
