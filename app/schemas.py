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


class AlertResolveIn(BaseModel):
    reviewer: str = "admin"
    remark: str | None = None


class RecordCompleteIn(BaseModel):
    handler: str = "admin"
    remark: str | None = None
    close_alerts: bool = True


class TriggerInspectionIn(BaseModel):
    device_id: str | None = None
    source: str | None = "web"


class StartDeviceIn(BaseModel):
    source: str = "web"
    once: bool = True
    payload: dict | None = None


class CommandAckIn(BaseModel):
    status: str
    result: dict | None = None
    error_message: str | None = None


class ReportIn(BaseModel):
    start_time: str
    end_time: str
    device_id: str | None = None
    format: str = "html"
    include_images: bool = True


class AgentMessageIn(BaseModel):
    role: str
    content: str


class AgentChatIn(BaseModel):
    message: str
    history: list[AgentMessageIn] | None = None
    image_uri: str | None = None
    image_data_url: str | None = None


class ExplainIn(BaseModel):
    alert_id: str
    question: str | None = None
    use_template_fallback: bool = True


class LoginIn(BaseModel):
    username: str
    password: str


class RegisterIn(BaseModel):
    username: str
    password: str
    role: str = "inspector"
    phone: str | None = None


class KnowledgeIn(BaseModel):
    knowledge_type: str
    title: str
    content: str
    device_id: str | None = None
    device_type: str | None = None
    tags: list[str] | None = None
    alarm_id: str | None = None
    source: str = "manual"


class DeployModelIn(BaseModel):
    node_id: str
    inference_config: dict | None = None


class DeviceIn(BaseModel):
    device_name: str
    node_id: str
    device_type: str
    location: str | None = None


class EdgeDetectionDataIn(BaseModel):
    device_id: str
    node_id: str
    image_uri: str | None = None
    temperature: float | None = None
    voltage: float | None = None
    current: float | None = None
    meter_value: str | None = None
    collect_time: str | None = None
