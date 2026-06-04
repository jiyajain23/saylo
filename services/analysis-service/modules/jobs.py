import urllib.parse
from typing import Any, Dict, List

def generate_job_recommendations(scenario: str, context: Dict[str, Any], confidence: float) -> List[Dict[str, Any]]:
    role = context.get("role", "")
    if not role or scenario != "INTERVIEW":
        return []
        
    # Calculate match percentage based on confidence
    match_base = min(98, max(60, int(confidence * 100) + 5))
    
    jobs = []
    
    # Primary Job
    primary_explanation = "Your communication style and structure match what employers look for in this role."
    if confidence >= 0.8:
        primary_explanation = "Your strong, structured responses make you highly competitive for this position."
    elif confidence < 0.65:
        primary_explanation = "With a bit more practice on framing your answers, you would be a solid fit."

    jobs.append({
        "role": role,
        "match": match_base,
        "explanation": primary_explanation,
        "url": f"https://www.linkedin.com/jobs/search/?keywords={urllib.parse.quote(role)}"
    })
    
    # Secondary Job 
    secondary_role = ""
    lower_role = role.lower()
    if "intern" in lower_role:
        secondary_role = lower_role.replace("intern", "associate").title()
    elif "junior" in lower_role:
        secondary_role = lower_role.replace("junior", "").strip().title()
    elif "senior" not in lower_role and "lead" not in lower_role:
        secondary_role = f"Senior {role}"
    else:
        secondary_role = f"Lead {role.replace('Senior', '').strip()}"
        
    jobs.append({
        "role": secondary_role,
        "match": max(45, match_base - 15),
        "explanation": "Based on the core skills you demonstrated, this is a great stretch role or alternative path.",
        "url": f"https://www.linkedin.com/jobs/search/?keywords={urllib.parse.quote(secondary_role)}"
    })

    return jobs
