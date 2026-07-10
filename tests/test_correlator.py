import sys
import os

# Ensure the root directory is in the python path for CI imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.correlator import correlate

def test_correlate_calculates_risk_score():
    """Verify that the correlator correctly joins billing data with security findings
    and accurately calculates the weighted risk score based on severities."""
    
    # Mock AWS Cost Explorer output
    billing = [
        {"resource_id": "i-12345", "monthly_cost_usd": 100},
        {"resource_id": "db-67890", "monthly_cost_usd": 500}
    ]
    
    # Mock AWS Security Hub findings
    findings = [
        {"resource_id": "i-12345", "severity": "CRITICAL"},
        {"resource_id": "i-12345", "severity": "HIGH"},
        {"resource_id": "db-67890", "severity": "LOW"}
    ]
    
    result = correlate(billing, findings)
    
    # Assert two resources were processed
    assert len(result) == 2
    
    # i-12345 should be first because it has the highest risk score
    # CRITICAL (40) + HIGH (25) = 65
    assert result[0]["resource_id"] == "i-12345"
    assert result[0]["total_risk_score"] == 65
    assert result[0]["finding_count"] == 2
    
    # db-67890 should be second
    # LOW (5) = 5
    assert result[1]["resource_id"] == "db-67890"
    assert result[1]["total_risk_score"] == 5
    assert result[1]["finding_count"] == 1
