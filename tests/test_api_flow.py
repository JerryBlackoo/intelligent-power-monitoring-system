from pathlib import Path

from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app


client = TestClient(app)


def reset_db() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_p0_api_flow() -> None:
    reset_db()
    heartbeat = {
        "node_id": "atlas_01",
        "ip": "192.168.1.88",
        "status": "online",
        "model_version": "yolov5s-power-v1",
        "timestamp": "2026-06-16 15:29:59",
    }
    assert client.post("/api/edge/heartbeat", json=heartbeat).status_code == 200

    payload = {
        "node_id": "atlas_01",
        "device_id": "cabinet_01",
        "captured_at": "2026-06-16 15:30:00",
        "image_uri": "/images/rec_001.jpg",
        "model_version": "yolov5s-power-v1",
        "detections": [
            {
                "label": "red_indicator",
                "confidence": 0.91,
                "bbox": [120, 80, 60, 40],
                "status": "warning",
                "description": "检测到红色告警指示灯",
            }
        ],
    }
    inference = client.post("/api/edge/inference", json=payload)
    assert inference.status_code == 200
    assert inference.json()["data"]["overall_status"] == "warning"
    assert inference.json()["data"]["alert_count"] == 1

    latest = client.get("/api/status/latest")
    assert latest.status_code == 200
    assert latest.json()["data"]["latest_record"]["overall_status"] == "warning"

    alerts = client.get("/api/alerts/active")
    assert alerts.status_code == 200
    alert_id = alerts.json()["data"][0]["alert_id"]

    detail = client.get(f"/api/alerts/{alert_id}")
    assert detail.status_code == 200
    assert detail.json()["data"]["related_detections"][0]["label"] == "red_indicator"

    explain = client.post("/api/llm/explain", json={"alert_id": alert_id})
    assert explain.status_code == 200
    assert explain.json()["data"]["source"] == "template"

    report = client.post(
        "/api/reports",
        json={
            "start_time": "2026-06-16 00:00:00",
            "end_time": "2026-06-16 23:59:59",
            "format": "html",
            "include_images": True,
        },
    )
    assert report.status_code == 200
    file_uri = report.json()["data"]["file_uri"]
    assert file_uri.startswith("/reports/")
    assert Path("static/reports", file_uri.removeprefix("/reports/")).exists()


def test_dashboard_page_served() -> None:
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "电力智能巡检工作台" in response.text
    assert "/dashboard-assets/app.js" in response.text
