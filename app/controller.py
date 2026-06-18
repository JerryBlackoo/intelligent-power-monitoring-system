from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.config import DASHBOARD_DIR, IMAGE_DIR, REPORT_DIR
from app.database import Base, engine, get_db
from app.entitys import AlarmEvent, InferenceResult, InspectionRecord
from app.agent_service import chat_with_power_agent
from app.schemas import (
    AlertReviewIn,
    AlertResolveIn,
    AgentChatIn,
    ApiResponse,
    CommandAckIn,
    DeployModelIn,
    DeviceIn,
    EdgeDetectionDataIn,
    ExplainIn,
    HeartbeatIn,
    InferenceIn,
    KnowledgeIn,
    LoginIn,
    RegisterIn,
    RecordCompleteIn,
    ReportIn,
    StartDeviceIn,
    TriggerInspectionIn,
)
from app.services import (
    add_knowledge,
    ack_edge_command,
    alarm_event_to_dict,
    authenticate_user,
    claim_edge_commands,
    complete_inspection_record,
    create_report,
    create_start_inspection_command,
    create_user,
    deploy_model,
    explain_alert,
    get_device_detail,
    get_device_detection_data,
    get_devices,
    get_edge_command,
    get_edge_deployment_config,
    get_edge_nodes_with_devices,
    get_latest_status,
    get_model_detail,
    get_models,
    get_user_info,
    inference_result_to_dict,
    list_reports,
    list_users,
    record_to_dict,
    resolve_alarm,
    resolve_record_alerts,
    save_edge_detection_data,
    save_evidence_image,
    save_uploaded_report,
    save_heartbeat,
    save_inference,
    search_knowledge,
)
from app.utils import now_text
from mcp_server.power_monitoring_mcp import mcp as power_mcp

Base.metadata.create_all(bind=engine)

power_mcp_app = power_mcp.streamable_http_app()


@asynccontextmanager
async def lifespan(app_: FastAPI):
    async with power_mcp.session_manager.run():
        yield


app = FastAPI(title="电力智能巡检系统后端", version="1.0.0", lifespan=lifespan)
app.mount("/images", StaticFiles(directory=IMAGE_DIR), name="images")
app.mount("/reports", StaticFiles(directory=REPORT_DIR), name="reports")
app.mount("/dashboard-assets", StaticFiles(directory=DASHBOARD_DIR), name="dashboard-assets")


def ok(data: object = None, message: str = "success") -> ApiResponse:
    return ApiResponse(code=200, message=message, data=data)


def dashboard_response() -> FileResponse:
    response = FileResponse(DASHBOARD_DIR / "index.html")
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response


# ═══════════════════════════ Dashboard ═══════════════════════════

@app.get("/api/health", response_model=ApiResponse)
def health() -> ApiResponse:
    return ok({"status": "ok"})


@app.get("/", include_in_schema=False)
def root() -> FileResponse:
    return dashboard_response()


@app.get("/dashboard", include_in_schema=False)
def dashboard() -> FileResponse:
    return dashboard_response()


# ═══════════════════════════ Auth (new) ═══════════════════════════

@app.post("/api/auth/login", response_model=ApiResponse)
def login(payload: LoginIn, db: Session = Depends(get_db)) -> ApiResponse:
    user = authenticate_user(db, payload.username, payload.password)
    if user is None:
        raise HTTPException(status_code=401, detail="invalid credentials")
    return ok(user, "login success")


@app.post("/api/auth/register", response_model=ApiResponse)
def register(payload: RegisterIn, db: Session = Depends(get_db)) -> ApiResponse:
    return ok(create_user(db, payload.username, payload.password, payload.role, payload.phone), "registered")


@app.get("/api/users/me", response_model=ApiResponse)
def users_me(user_id: str = "admin", db: Session = Depends(get_db)) -> ApiResponse:
    user = get_user_info(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    return ok(user)


@app.get("/api/users/list", response_model=ApiResponse)
def users_list(db: Session = Depends(get_db)) -> ApiResponse:
    return ok(list_users(db))


# ═══════════════════════════ Edge ═══════════════════════════

@app.post("/api/edge/heartbeat", response_model=ApiResponse)
def edge_heartbeat(payload: HeartbeatIn, db: Session = Depends(get_db)) -> ApiResponse:
    node = save_heartbeat(db, payload)
    return ok({"node_id": node.node_id, "server_time": node.last_heartbeat}, "heartbeat received")


@app.post("/api/edge/evidence", response_model=ApiResponse)
async def edge_evidence(
    file: UploadFile = File(...),
    node_id: str = Form(...),
    captured_at: str | None = Form(None),
    record_id: str | None = Form(None),
) -> ApiResponse:
    if file.content_type and not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="only image uploads are supported")
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="empty image file")
    return ok(
        save_evidence_image(
            filename=file.filename or "evidence.jpg",
            contents=contents,
            node_id=node_id,
            captured_at=captured_at,
            record_id=record_id,
        ),
        "evidence uploaded",
    )


@app.post("/api/edge/inference", response_model=ApiResponse)
def edge_inference(payload: InferenceIn, db: Session = Depends(get_db)) -> ApiResponse:
    return ok(save_inference(db, payload), "inference result saved")


# ═══════════════════════════ Inspection ═══════════════════════════

@app.post("/api/inspection/trigger", response_model=ApiResponse)
def trigger_inspection(payload: TriggerInspectionIn, db: Session = Depends(get_db)) -> ApiResponse:
    if not payload.device_id:
        raise HTTPException(status_code=400, detail="device_id is required")
    command = create_start_inspection_command(db, payload.device_id, source=payload.source or "web")
    if command is None:
        raise HTTPException(status_code=404, detail="device not found")
    return ok(command, "inspection command created")


# ═══════════════════════════ Status / Nodes ═════════════════════

@app.get("/api/status/latest", response_model=ApiResponse)
def latest_status(db: Session = Depends(get_db)) -> ApiResponse:
    return ok(get_latest_status(db))


@app.get("/api/edge/nodes", response_model=ApiResponse)
def list_edge_nodes(db: Session = Depends(get_db)) -> ApiResponse:
    return ok(get_edge_nodes_with_devices(db))


@app.get("/api/edge/commands", response_model=ApiResponse)
def edge_commands(node_id: str, limit: int = 5, db: Session = Depends(get_db)) -> ApiResponse:
    return ok(claim_edge_commands(db, node_id, limit), "commands claimed")


@app.post("/api/edge/commands/{command_id}/ack", response_model=ApiResponse)
def edge_command_ack(command_id: str, payload: CommandAckIn, db: Session = Depends(get_db)) -> ApiResponse:
    try:
        command = ack_edge_command(db, command_id, payload.status, payload.result, payload.error_message)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if command is None:
        raise HTTPException(status_code=404, detail="command not found")
    return ok(command, "command acknowledged")


@app.get("/api/edge/commands/{command_id}", response_model=ApiResponse)
def edge_command_detail(command_id: str, db: Session = Depends(get_db)) -> ApiResponse:
    command = get_edge_command(db, command_id)
    if command is None:
        raise HTTPException(status_code=404, detail="command not found")
    return ok(command)


# ═══════════════════════════ Records ═══════════════════════════

@app.get("/api/records", response_model=ApiResponse)
def list_records(
    start_time: str | None = None,
    end_time: str | None = None,
    device_id: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 10,
    db: Session = Depends(get_db),
) -> ApiResponse:
    query = select(InspectionRecord).options(
        joinedload(InspectionRecord.inspector),
        joinedload(InspectionRecord.inference_result).joinedload(InferenceResult.model),
        joinedload(InspectionRecord.alarm_events),
    )
    if start_time:
        query = query.where(InspectionRecord.inspected_at >= start_time)
    if end_time:
        query = query.where(InspectionRecord.inspected_at <= end_time)
    if device_id:
        query = query.where(InspectionRecord.device_id == device_id)
    if status:
        query = query.where(InspectionRecord.overall_status == status)

    all_items = db.scalars(query.order_by(InspectionRecord.inspected_at.desc())).unique().all()
    start = max(page - 1, 0) * page_size
    end = start + page_size
    return ok({"total": len(all_items), "items": [record_to_dict(item) for item in all_items[start:end]]})


@app.get("/api/records/{record_id}", response_model=ApiResponse)
def get_record(record_id: str, db: Session = Depends(get_db)) -> ApiResponse:
    record = db.scalar(
        select(InspectionRecord)
        .options(
            joinedload(InspectionRecord.inspector),
            joinedload(InspectionRecord.inference_result).joinedload(InferenceResult.model),
            joinedload(InspectionRecord.alarm_events),
        )
        .where(InspectionRecord.record_id == record_id)
    )
    if record is None:
        raise HTTPException(status_code=404, detail="record not found")
    return ok(record_to_dict(record, detail=True))


@app.post("/api/records/{record_id}/alerts/resolve", response_model=ApiResponse)
def resolve_record_alarms(record_id: str, db: Session = Depends(get_db)) -> ApiResponse:
    result = resolve_record_alerts(db, record_id)
    if result is None:
        raise HTTPException(status_code=404, detail="record not found")
    return ok(result, "record alerts resolved")


@app.post("/api/records/{record_id}/complete", response_model=ApiResponse)
def complete_record(record_id: str, payload: RecordCompleteIn | None = None,
                    db: Session = Depends(get_db)) -> ApiResponse:
    body = payload or RecordCompleteIn()
    result = complete_inspection_record(db, record_id, body.handler, body.remark, body.close_alerts)
    if result is None:
        raise HTTPException(status_code=404, detail="record not found")
    return ok(result, "inspection record completed")


# ═══════════════════════════ Alerts ═══════════════════════════

@app.get("/api/alerts/active", response_model=ApiResponse)
def list_active_alarms(
    level: str | None = None,
    device_id: str | None = None,
    db: Session = Depends(get_db),
) -> ApiResponse:
    query = select(AlarmEvent).where(AlarmEvent.alarm_status.in_(["open", "reviewing"]))
    if level:
        query = query.where(AlarmEvent.alarm_level == level)
    if device_id:
        query = query.where(AlarmEvent.device_id == device_id)
    alarms = db.scalars(query.order_by(AlarmEvent.alarm_time.desc())).all()
    return ok([alarm_event_to_dict(item) for item in alarms])


@app.get("/api/alerts/{alert_id}", response_model=ApiResponse)
def get_alarm(alert_id: str, db: Session = Depends(get_db)) -> ApiResponse:
    alarm = db.scalar(
        select(AlarmEvent)
        .options(
            joinedload(AlarmEvent.knowledge),
            joinedload(AlarmEvent.inference_result),
        )
        .where(AlarmEvent.alarm_id == alert_id)
    )
    if alarm is None:
        raise HTTPException(status_code=404, detail="alert not found")
    data = alarm_event_to_dict(alarm)
    if alarm.knowledge:
        data["advice"] = {
            "advice_id": alarm.knowledge[0].knowledge_id if alarm.knowledge else None,
            "summary": alarm.knowledge[0].title if alarm.knowledge else "",
            "possible_cause": alarm.knowledge[0].content[:200] if alarm.knowledge else "",
            "risk_level": alarm.alarm_level,
            "action_steps": [],
            "source": alarm.knowledge[0].source if alarm.knowledge else "",
        }
    return ok(data)


@app.post("/api/alerts/{alert_id}/review", response_model=ApiResponse)
def review_alert(alert_id: str, payload: AlertReviewIn, db: Session = Depends(get_db)) -> ApiResponse:
    alarm = db.get(AlarmEvent, alert_id)
    if alarm is None:
        raise HTTPException(status_code=404, detail="alert not found")
    mapping = {"confirm": "reviewing", "false_alarm": "closed", "resolve": "resolved", "close": "closed"}
    if payload.action not in mapping:
        raise HTTPException(status_code=400, detail="invalid review action")
    alarm.alarm_status = mapping[payload.action]
    if alarm.alarm_status == "resolved":
        alarm.resolved_time = now_text()
    db.commit()
    return ok({"alert_id": alarm.alarm_id, "status": alarm.alarm_status}, "alert reviewed")


@app.post("/api/alerts/{alert_id}/resolve", response_model=ApiResponse)
def resolve_alert(alert_id: str, payload: AlertResolveIn | None = None,
                  db: Session = Depends(get_db)) -> ApiResponse:
    body = payload or AlertResolveIn()
    result = resolve_alarm(db, alert_id, body.remark)
    if result is None:
        raise HTTPException(status_code=404, detail="alert not found")
    return ok(result, "alert resolved")


# ═══════════════════════════ Reports ═══════════════════════════

@app.get("/api/reports", response_model=ApiResponse)
def report_list(limit: int = 20, db: Session = Depends(get_db)) -> ApiResponse:
    return ok(list_reports(db, limit), "reports listed")


@app.post("/api/reports", response_model=ApiResponse)
def reports(payload: ReportIn, db: Session = Depends(get_db)) -> ApiResponse:
    return ok(create_report(db, payload), "report generated")


@app.post("/api/reports/upload", response_model=ApiResponse)
async def upload_report(
    file: UploadFile = File(...),
    device_id: str | None = Form(None),
    record_id: str | None = Form(None),
    handler: str | None = Form(None),
    handle_status: str = Form("reviewing"),
    note: str | None = Form(None),
    db: Session = Depends(get_db),
) -> ApiResponse:
    contents = await file.read()
    try:
        data = save_uploaded_report(
            db=db,
            filename=file.filename or "inspection_report",
            contents=contents,
            device_id=device_id,
            record_id=record_id,
            handler=handler,
            handle_status=handle_status,
            note=note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ok(data, "report uploaded")


@app.post("/api/agent/chat", response_model=ApiResponse)
def agent_chat(payload: AgentChatIn) -> ApiResponse:
    try:
        return ok(chat_with_power_agent(payload), "agent replied")
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"agent provider failed: {exc.response.text[:300]}") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"agent provider unavailable: {exc}") from exc


@app.post("/api/llm/explain", response_model=ApiResponse)
def llm_explain(payload: ExplainIn, db: Session = Depends(get_db)) -> ApiResponse:
    advice = explain_alert(db, payload.alert_id)
    if advice is None:
        raise HTTPException(status_code=404, detail="alert not found")
    return ok(advice, "explanation generated")


# ═══════════════════════════ Devices (new) ═════════════════════

@app.get("/api/devices", response_model=ApiResponse)
def list_devices(node_id: str | None = None, db: Session = Depends(get_db)) -> ApiResponse:
    return ok(get_devices(db, node_id))


@app.get("/api/devices/{device_id}", response_model=ApiResponse)
def device_detail(device_id: str, db: Session = Depends(get_db)) -> ApiResponse:
    dev = get_device_detail(db, device_id)
    if dev is None:
        raise HTTPException(status_code=404, detail="device not found")
    return ok(dev)


@app.get("/api/devices/{device_id}/detection-data", response_model=ApiResponse)
def device_detection_data(device_id: str, limit: int = 20, db: Session = Depends(get_db)) -> ApiResponse:
    return ok(get_device_detection_data(db, device_id, limit))


@app.post("/api/devices/{device_id}/start", response_model=ApiResponse)
def start_device(device_id: str, payload: StartDeviceIn | None = None, db: Session = Depends(get_db)) -> ApiResponse:
    body = payload or StartDeviceIn()
    command = create_start_inspection_command(db, device_id, body.source, body.once, body.payload)
    if command is None:
        raise HTTPException(status_code=404, detail="device not found")
    return ok(command, "inspection command created")


@app.get("/api/edge/deployment-config", response_model=ApiResponse)
def edge_deployment_config(node_id: str, db: Session = Depends(get_db)) -> ApiResponse:
    return ok(get_edge_deployment_config(db, node_id))


@app.post("/api/edge/detection-data", response_model=ApiResponse)
def edge_detection_data(payload: EdgeDetectionDataIn, db: Session = Depends(get_db)) -> ApiResponse:
    return ok(save_edge_detection_data(db, payload.model_dump()), "detection data saved")


# ═══════════════════════════ Models (new) ══════════════════════

@app.get("/api/models", response_model=ApiResponse)
def list_models(db: Session = Depends(get_db)) -> ApiResponse:
    return ok(get_models(db))


@app.get("/api/models/{model_id}", response_model=ApiResponse)
def model_detail(model_id: str, db: Session = Depends(get_db)) -> ApiResponse:
    m = get_model_detail(db, model_id)
    if m is None:
        raise HTTPException(status_code=404, detail="model not found")
    return ok(m)


@app.post("/api/models/{model_id}/deploy", response_model=ApiResponse)
def model_deploy(model_id: str, payload: DeployModelIn, db: Session = Depends(get_db)) -> ApiResponse:
    return ok(deploy_model(db, model_id, payload.node_id, payload.inference_config), "deployment created")


# ═══════════════════════════ Knowledge (new) ═══════════════════

@app.get("/api/knowledge", response_model=ApiResponse)
def list_knowledge(
    device_type: str | None = None,
    knowledge_type: str | None = None,
    keyword: str | None = None,
    limit: int = 20,
    db: Session = Depends(get_db),
) -> ApiResponse:
    return ok(search_knowledge(db, device_type, knowledge_type, keyword, limit))


@app.post("/api/knowledge", response_model=ApiResponse)
def create_knowledge(payload: KnowledgeIn, db: Session = Depends(get_db)) -> ApiResponse:
    return ok(add_knowledge(
        db, payload.knowledge_type, payload.title, payload.content,
        payload.device_id, payload.device_type, payload.tags,
        payload.alarm_id, payload.source,
    ), "knowledge created")


# ═══════════════════════════ MCP Mount ═══════════════════════════

app.mount("/", power_mcp_app, name="power-mcp")
