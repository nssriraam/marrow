"""
Marrow — LLM Reasoner (Decision Engine)

The core intelligence layer of Marrow. Operates in two modes:

  1. LIVE MODE  — When a valid Fireworks API key is present, queries are
                  routed to DeepSeek V4 running on AMD Instinct MI300X
                  accelerators via the Fireworks inference API. Returns
                  nuanced, context-aware recommendations with chain-of-
                  thought justifications.

  2. DEMO MODE — When no API key is configured (e.g., public internet
                 traffic hitting the live demo), the system falls back
                 to a fully deterministic rule-based reasoner. This
                 protects API credits while still producing realistic,
                 consistent output for evaluation.

Both modes output the same JSON schema so the dashboard and PDF
export layer work identically regardless of which mode is active.
"""

import json
import logging
import requests
from app.config import Config

logger = logging.getLogger(__name__)

# Strict vocabulary for actions -- UI depends on these exact strings
VALID_ACTIONS = {"terminate", "rightsize", "patch", "restrict-access", "ignore"}

# Contract for the UI (can be imported by routes if needed, or just kept here as reference)
ACTION_STYLES = {
    "terminate": {"color": "#f85149", "icon": "trash", "label": "Terminate"},
    "rightsize": {"color": "#d29922", "icon": "arrow-down", "label": "Rightsize"},
    "patch": {"color": "#58a6ff", "icon": "shield-check", "label": "Patch"},
    "restrict-access": {"color": "#bc8cff", "icon": "lock", "label": "Restrict Access"},
    "ignore": {"color": "#8b949e", "icon": "check", "label": "Ignore"},
}

SYSTEM_PROMPT = """You are an expert Cloud FinOps and DevSecOps AI assistant.
Your job is to analyze cloud resource billing and security findings, and recommend the best action.
You must return a valid JSON list of objects, one for each resource analyzed.

For each resource, decide the best action based on its utilization and security posture.
You MUST choose EXACTLY one of these valid actions: ["terminate", "rightsize", "patch", "restrict-access", "ignore"]
Rate your confidence 0-100 based on how clear-cut this decision is given the data. High utilization + clear findings = high confidence either way. Low utilization + conflicting signals (e.g., a resource that looks idle but might be business-critical, or a finding with unclear severity) = lower confidence.

You are encouraged to think through the trade-offs step-by-step. Provide a thorough chain-of-thought analysis for each resource, but keep it focused and avoid repetitive loops.

Output JSON Format EXACTLY like this:
{
  "recommendations": [
    {
      "resource_id": "the-resource-id",
      "action": "terminate",
      "monthly_savings_usd": 100.0,
      "annual_savings_usd": 1200.0,
      "risk_reduction": "Resolved 2 HIGH findings",
      "priority_score": 85,
      "confidence": 95,
      "justification": "Resource is 0% utilized and has critical security vulnerabilities."
    }
  ]
}
"""

def _clamp_action(action: str) -> str:
    """Ensure action strictly belongs to VALID_ACTIONS. Fallback to 'ignore' if LLM hallucinates."""
    normalized = str(action).strip().lower().replace(" ", "-").replace("_", "-")
    
    # Handle some common LLM drift
    if "remediate" in normalized:
        return "patch"
    if "downsize" in normalized:
        return "rightsize"
    
    if normalized in VALID_ACTIONS:
        return normalized
    
    logger.warning(f"Clamped invalid action '{action}' to 'ignore'")
    return "ignore"

def generate_recommendations(correlated_data: list[dict]) -> list[dict]:
    """
    Call Fireworks AI to get recommendations for a batch of resources.
    Falls back to mock mode if FIREWORKS_API_KEY is not set.
    """
    api_key = Config.FIREWORKS_API_KEY.strip() if Config.FIREWORKS_API_KEY else ""
    if not api_key or api_key == "your_fireworks_api_key_here" or api_key.startswith("your_"):
        print("  [dim yellow]API key missing/default. Using mock reasoner...[/dim yellow]")
        return _mock_reasoner(correlated_data)

    headers = {
        "Authorization": f"Bearer {Config.FIREWORKS_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    resources_payload = []
    for r in correlated_data:
        resources_payload.append({
            "resource_id": r["resource_id"],
            "service": r["service"],
            "monthly_cost": r["monthly_cost_usd"],
            "utilization_pct": r["utilization_pct"],
            "findings_count": r["finding_count"],
            "total_risk_score": r["total_risk_score"],
            "findings": [{"type": f["finding_type"], "severity": f["severity"]} for f in r.get("findings", [])]
        })

    payload = {
        "model": Config.FIREWORKS_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Analyze these resources and provide JSON recommendations:\n{json.dumps(resources_payload, indent=2)}"}
        ],
        "temperature": 0.1, 
        "max_tokens": 8192,
        "response_format": {"type": "json_object"} 
    }

    try:
        response = requests.post(
            f"{Config.FIREWORKS_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
            timeout=300
        )
        response.raise_for_status()
        
        result_json = response.json()
        choices = result_json.get("choices", [])
        if not choices:
            raise ValueError("API response missing 'choices'")
        message = choices[0].get("message", {})
        content = message.get("content", "")
        if not content:
            raise ValueError("API response missing 'content'")
        
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        elif content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
            
        recommendations = json.loads(content)
        
        if isinstance(recommendations, dict):
            for key, val in recommendations.items():
                if isinstance(val, list):
                    recommendations = val
                    break
                    
        if not isinstance(recommendations, list):
            raise ValueError("LLM did not return a list of recommendations.")
            
        # Clamp actions
        for rec in recommendations:
            rec["action"] = _clamp_action(rec.get("action", "ignore"))
            
        return recommendations
        
    except Exception as e:
        logger.error(f"Fireworks API Error: {e}")
        print(f"  [bold red]API Error:[/bold red] {e}. Falling back to mock reasoner.")
        return _mock_reasoner(correlated_data)

def _mock_reasoner(correlated_data: list[dict]) -> list[dict]:
    """Mock fallback logic for testing without an API key."""
    recs = []
    for r in correlated_data:
        rid = r["resource_id"]
        cost = r["monthly_cost_usd"]
        util = r["utilization_pct"]
        risk = r["total_risk_score"]
        
        if util < 5.0 and risk > 30:
            action = "terminate"
            savings = cost
            reduction = f"Removed {r['finding_count']} findings"
            score = 95
            conf = 95
            just = f"Highly vulnerable (score {risk}) and idle ({util}% util). Kill it."
        elif util < 20.0:
            action = "rightsize"
            savings = cost * 0.4
            reduction = "None"
            score = 50
            conf = 80
            just = f"Underutilized ({util}%). Downsize to save money."
        elif risk >= 50:
            action = "patch"
            savings = 0.0
            reduction = f"Resolved {r['finding_count']} findings"
            score = 90
            conf = 90
            just = "Critical security issues found on active resource. Immediate action required."
        elif risk > 0:
            action = "restrict-access"
            savings = 0.0
            reduction = "Mitigated medium risk"
            score = 40
            conf = 60
            just = "Security posture needs tightening."
        else:
            action = "ignore"
            savings = 0.0
            reduction = "None"
            score = 0
            conf = 100
            just = "Resource is healthy and utilized."
            
        recs.append({
            "resource_id": rid,
            "action": action,
            "monthly_savings_usd": savings,
            "annual_savings_usd": savings * 12,
            "risk_reduction": reduction,
            "priority_score": score,
            "confidence": conf,
            "justification": just
        })
        
    return recs

def generate_executive_summary(recs: list[dict]) -> str:
    """Generate a 3-sentence executive summary covering savings, risk reduction, and top priority."""
    
    total_savings = sum(r.get("monthly_savings_usd", 0) for r in recs)
    annual_savings = total_savings * 12
    resource_count = len(recs)
    
    # Identify top priority
    top_rec = max(recs, key=lambda x: x.get("priority_score", 0)) if recs else None
    
    # Build a highly competent mock fallback
    if top_rec and top_rec.get("action") != "ignore":
        top_action = f"the immediate {top_rec['action']} of {top_rec['resource_id']}"
    else:
        top_action = "reviewing overall access policies"

    mock_summary = (
        f"Marrow identified ${total_savings:.2f} in immediate monthly savings (projecting to ${annual_savings:.2f} annually) by optimizing {resource_count} cloud resources. "
        "The recommended actions resolve multiple critical vulnerabilities, directly reducing the active attack surface. "
        f"The single highest-priority action is {top_action}, which mitigates severe risks while optimizing spend."
    )

    if not Config.FIREWORKS_API_KEY or Config.FIREWORKS_API_KEY == "your_fireworks_api_key_here":
        return mock_summary

    prompt = (
        "You are Marrow, an intelligent Cloud FinOps & SecOps assistant. Based on the following recommendations, "
        "provide a 3-sentence executive summary covering total monthly/annual savings, total risk reduction, and the single highest-priority action. "
        "Use a confident, professional product voice (e.g., 'Marrow identified...', 'We recommend...'). "
        "Respond ONLY with the 3 sentences. No introductory text."
    )
    
    # Trim the payload size a bit by dropping verbose justification since it can be long
    payload_recs = []
    for r in recs:
        payload_recs.append({
            "id": r["resource_id"],
            "action": r["action"],
            "savings": r.get("monthly_savings_usd", 0),
            "priority": r.get("priority_score", 0)
        })

    payload = {
        "model": Config.FIREWORKS_MODEL,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"NOTE: Total monthly savings is exactly ${total_savings:.2f}. Top priority is {top_rec['resource_id'] if top_rec else 'none'}. Recommendations:\n{json.dumps(payload_recs)}"}
        ],
        "temperature": 0.1,
        "max_tokens": 8192
    }

    try:
        headers = {
            "Authorization": f"Bearer {Config.FIREWORKS_API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        resp = requests.post(
            f"{Config.FIREWORKS_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
            timeout=300
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"].strip()
        
        # Simple cleanup if LLM includes thinking tags (unlikely with low token count but just in case)
        if "</think>" in content:
            content = content.split("</think>")[-1].strip()
            
        if not content:
            return mock_summary
        return content
    except Exception as e:
        logger.error(f"Executive Summary LLM Error: {e}")
        return mock_summary
