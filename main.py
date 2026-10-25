from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Dict, Any
import uvicorn

app = FastAPI()

# In-memory store for simplicity
incident_store: Dict[str, Dict[str, Any]] = {}


class IncidentRequest(BaseModel):
    incident_id: str
    service: str
    symptoms: List[str]
    telemetry: Dict[str, Any]
    requested_action: str


class IncidentResponse(BaseModel):
    incident_id: str
    diagnosis: str
    action_taken: str
    evidence: Dict[str, Any]
    saved: bool


def diagnose(incident: IncidentRequest) -> str:
    t = incident.telemetry
    reasons = []

    if "latency_ms" in t and t["latency_ms"] > 1000:
        reasons.append(f"High latency ({t['latency_ms']} ms)")
    if "cpu" in t and t["cpu"] > 85:
        reasons.append(f"CPU saturation ({t['cpu']}%)")
    if "errors_per_min" in t and t["errors_per_min"] > 50:
        reasons.append(f"High error rate ({t['errors_per_min']} errors/min)")

    if not reasons:
        return "No clear incident cause found; service appears within normal telemetry bounds."

    return "; ".join(reasons)


def choose_action(incident: IncidentRequest, diagnosis: str) -> str:
    t = incident.telemetry
    requested = incident.requested_action.lower()

    # Replay-safe: if already processed
    if incident.incident_id in incident_store:
        return incident_store[incident.incident_id]["action_taken"]

    # Scaling safety rule
    scale = t.get("scale")
    scale_limit = t.get("scale_limit")
    if requested == "scale" and scale is not None and scale_limit is not None:
        if scale >= scale_limit:
            return "page_owner"

    # If strong diagnosis exists
    if "CPU saturation" in diagnosis or "High latency" in diagnosis:
        if requested == "restart":
            return "restart"
        if requested == "scale" and (scale is None or scale < scale_limit):
            return "scale"

    # If no clear diagnosis
    if diagnosis.startswith("No clear incident cause"):
        return "noop"

    # Respect safe requested actions
    if requested in ["restart", "scale", "page_owner", "noop"]:
        return requested

    return "noop"


@app.post("/incident", response_model=IncidentResponse)
def handle_incident(incident: IncidentRequest):
    diagnosis = diagnose(incident)
    action = choose_action(incident, diagnosis)

    evidence = {
        "service": incident.service,
        "symptoms": incident.symptoms,
        "telemetry": incident.telemetry,
        "requested_action": incident.requested_action,
        "diagnosis": diagnosis,
        "final_action": action,
    }

    incident_store[incident.incident_id] = {
        "diagnosis": diagnosis,
        "action_taken": action,
        "evidence": evidence,
    }

    return IncidentResponse(
        incident_id=incident.incident_id,
        diagnosis=diagnosis,
        action_taken=action,
        evidence=evidence,
        saved=True,
    )


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
@app.post("/v2/incidents", response_model=IncidentResponse)
def handle_v2_incident(incident: IncidentRequest):
    return handle_incident(incident)
