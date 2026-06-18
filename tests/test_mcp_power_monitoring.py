from app.database import Base, SessionLocal, engine
from app.schemas import DetectionIn, HeartbeatIn, InferenceIn
from app.services import save_heartbeat, save_inference
from mcp_server.power_monitoring_mcp import (
    AlertsInput,
    RecordsInput,
    get_alert_detail_data,
    get_record_detail_data,
    get_runtime_diagnostics_data,
    get_system_overview_data,
    list_alerts_data,
    list_records_data,
)


def reset_db() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def seed_warning_record() -> tuple[str, str]:
    with SessionLocal() as db:
        save_heartbeat(
            db,
            HeartbeatIn(
                node_id="atlas_01",
                ip="192.168.1.88",
                status="online",
                model_version="yolov5s-power-v1",
                timestamp="2026-06-18 10:00:00",
            ),
        )
        result = save_inference(
            db,
            InferenceIn(
                node_id="atlas_01",
                device_id="cabinet_01",
                captured_at="2026-06-18 10:01:00",
                image_uri="/images/test.jpg",
                model_version="yolov5s-power-v1",
                detections=[
                    DetectionIn(
                        label="red_indicator",
                        confidence=0.91,
                        bbox=[120, 80, 60, 40],
                        status="warning",
                        description="检测到红色告警指示灯",
                    )
                ],
            ),
        )
        return result["record_id"], result["alerts"][0]["alert_id"]


def test_mcp_data_helpers_expose_current_system_state() -> None:
    reset_db()
    record_id, alert_id = seed_warning_record()

    overview = get_system_overview_data()
    assert overview["project"]["database_ready"] is True
    assert overview["counts"]["inspection_records"] == 1
    assert overview["current"]["edge_node"]["node_id"] == "atlas_01"
    assert overview["current"]["latest_record"]["overall_status"] == "warning"

    records = list_records_data(RecordsInput(limit=10, include_detail=True))
    assert records["total"] == 1
    assert records["items"][0]["record_id"] == record_id
    assert records["items"][0]["detections"][0]["label"] == "red_indicator"

    record_detail = get_record_detail_data(record_id)
    assert record_detail["record_id"] == record_id
    assert record_detail["alerts"][0]["alert_id"] == alert_id

    alerts = list_alerts_data(AlertsInput(level="warning", limit=10))
    assert alerts["total"] == 1
    assert alerts["items"][0]["alert_id"] == alert_id

    alert_detail = get_alert_detail_data(alert_id)
    assert alert_detail["alert_id"] == alert_id
    assert alert_detail["related_detections"][0]["status"] == "warning"


def test_mcp_runtime_diagnostics_reports_local_paths() -> None:
    diagnostics = get_runtime_diagnostics_data()
    assert diagnostics["database"]["exists"] is True
    assert "GET /api/status/latest" in diagnostics["api_entrypoints"]
    model_path = diagnostics["assets"]["model"]["path"].replace("\\", "/")
    assert model_path.endswith("model/best.om")
