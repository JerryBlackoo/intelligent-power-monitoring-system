WARNING_LABELS = {
    "red_indicator",
    "insulator_defect",
    "foreign_object",
    "bird_nest",
    "smoke",
    "water",
}

CRITICAL_LABELS = {
    "fire",
    "severe_damage",
}


def map_detection_status(label: str, confidence: float) -> str:
    if confidence < 0.35:
        return "pending_review"
    if label in CRITICAL_LABELS:
        return "critical"
    if label in WARNING_LABELS:
        return "warning"
    return "normal"
