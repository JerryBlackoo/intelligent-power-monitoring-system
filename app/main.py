from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.config import DASHBOARD_DIR, IMAGE_DIR, REPORT_DIR
from app.database import Base, engine, get_db
from app.models import Alert, InspectionRecord
from app.schemas import (
    AlertReviewIn,
    ApiResponse,
    ExplainIn,
    HeartbeatIn,
    InferenceIn,
    ReportIn,
    TriggerInspectionIn,
)
from app.services import (
    alert_to_dict,
    create_report,
    explain_alert,
    get_latest_status,
    record_to_dict,
    save_heartbeat,
    save_inference,
)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="电力智能巡检系统后端", version="1.0.0")
app.mount("/images", StaticFiles(directory=IMAGE_DIR), name="images")
app.mount("/reports", StaticFiles(directory=REPORT_DIR), name="reports")
app.mount("/dashboard-assets", StaticFiles(directory=DASHBOARD_DIR), name="dashboard-assets")


def ok(data: object = None, message: str = "success") -> ApiResponse:
    return ApiResponse(code=200, message=message, data=data)


@app.get("/api/health", response_model=ApiResponse)
def health() -> ApiResponse:
    return ok({"status": "ok"})


@app.get("/", include_in_schema=False)
def root() -> FileResponse:
    return FileResponse(DASHBOARD_DIR / "index.html")


@app.get("/dashboard", include_in_schema=False)
def dashboard() -> FileResponse:
    return FileResponse(DASHBOARD_DIR / "index.html")


@app.post("/api/edge/heartbeat", response_model=ApiResponse)
def edge_heartbeat(payload: HeartbeatIn, db: Session = Depends(get_db)) -> ApiResponse:
    node = save_heartbeat(db, payload)
    return ok({"node_id": node.node_id, "server_time": node.last_heartbeat}, "heartbeat received")


@app.post("/api/edge/inference", response_model=ApiResponse)
def edge_inference(payload: InferenceIn, db: Session = Depends(get_db)) -> ApiResponse:
    return ok(save_inference(db, payload), "inference result saved")


@app.post("/api/inspection/trigger", response_model=ApiResponse)
def trigger_inspection(payload: TriggerInspectionIn) -> ApiResponse:
    return ok({"task_id": "task_mock_001", "status": "pending", "device_id": payload.device_id})


@app.get("/api/status/latest", response_model=ApiResponse)
def latest_status(db: Session = Depends(get_db)) -> ApiResponse:
    return ok(get_latest_status(db))


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
        joinedload(InspectionRecord.detections), joinedload(InspectionRecord.alerts)
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
        .options(joinedload(InspectionRecord.detections), joinedload(InspectionRecord.alerts))
        .where(InspectionRecord.record_id == record_id)
    )
    if record is None:
        raise HTTPException(status_code=404, detail="record not found")
    return ok(record_to_dict(record, detail=True))


@app.get("/api/alerts/active", response_model=ApiResponse)
def list_active_alerts(
    level: str | None = None,
    device_id: str | None = None,
    db: Session = Depends(get_db),
) -> ApiResponse:
    query = select(Alert).where(Alert.status.in_(["open", "reviewing"]))
    if level:
        query = query.where(Alert.level == level)
    if device_id:
        query = query.where(Alert.device_id == device_id)
    alerts = db.scalars(query.order_by(Alert.created_at.desc())).all()
    return ok([alert_to_dict(item, include_advice=False) for item in alerts])


@app.get("/api/alerts/{alert_id}", response_model=ApiResponse)
def get_alert(alert_id: str, db: Session = Depends(get_db)) -> ApiResponse:
    alert = db.scalar(
        select(Alert)
        .options(joinedload(Alert.advice))
        .where(Alert.alert_id == alert_id)
    )
    if alert is None:
        raise HTTPException(status_code=404, detail="alert not found")
    data = alert_to_dict(alert)
    data["related_detections"] = [item for item in record_to_dict(alert.record, detail=True)["detections"]]
    return ok(data)


@app.post("/api/alerts/{alert_id}/review", response_model=ApiResponse)
def review_alert(alert_id: str, payload: AlertReviewIn, db: Session = Depends(get_db)) -> ApiResponse:
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="alert not found")
    mapping = {"confirm": "reviewing", "false_alarm": "closed", "resolve": "resolved", "close": "closed"}
    if payload.action not in mapping:
        raise HTTPException(status_code=400, detail="invalid review action")
    alert.status = mapping[payload.action]
    db.commit()
    return ok({"alert_id": alert.alert_id, "status": alert.status}, "alert reviewed")


@app.post("/api/reports", response_model=ApiResponse)
def reports(payload: ReportIn, db: Session = Depends(get_db)) -> ApiResponse:
    return ok(create_report(db, payload), "report generated")


@app.post("/api/llm/explain", response_model=ApiResponse)
def llm_explain(payload: ExplainIn, db: Session = Depends(get_db)) -> ApiResponse:
    advice = explain_alert(db, payload.alert_id)
    if advice is None:
        raise HTTPException(status_code=404, detail="alert not found")
    return ok(advice, "explanation generated")
