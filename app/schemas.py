from pydantic import BaseModel, Field


class ApiResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: object | None = None


class DetectionIn(BaseModel):
    label: str
    confidence: float = Field(ge=0, le=1)
    bbox: list[float] = Field(min_length=4, max_length=4)
    status: str
    description: str | None = None


class HeartbeatIn(BaseModel):
    node_id: str
    ip: str
    status: str
    model_version: str
    timestamp: str


class InferenceIn(BaseModel):
    record_id: str | None = None
    node_id: str
    device_id: str | None = None
    captured_at: str
    image_uri: str
    model_version: str
    detections: list[DetectionIn]


class AlertReviewIn(BaseModel):
    action: str
    reviewer: str
    remark: str | None = None


class TriggerInspectionIn(BaseModel):
    device_id: str | None = None
    source: str | None = "web"


class ReportIn(BaseModel):
    start_time: str
    end_time: str
    device_id: str | None = None
    format: str = "html"
    include_images: bool = True


class ExplainIn(BaseModel):
    alert_id: str
    question: str | None = None
    use_template_fallback: bool = True
