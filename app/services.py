import json
from html import escape

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.config import REPORT_DIR
from app.models import Alert, DetectionResult, EdgeNode, InspectionRecord, MaintenanceAdvice, Report
from app.schemas import HeartbeatIn, InferenceIn, ReportIn
from app.utils import highest_status, next_id, now_text


def save_heartbeat(db: Session, payload: HeartbeatIn) -> EdgeNode:
    node = db.get(EdgeNode, payload.node_id)
    if node is None:
        node = EdgeNode(node_id=payload.node_id, ip=payload.ip, status=payload.status,
                        model_version=payload.model_version, last_heartbeat=payload.timestamp)
        db.add(node)
    else:
        node.ip = payload.ip
        node.status = payload.status
        node.model_version = payload.model_version
        node.last_heartbeat = payload.timestamp
    db.commit()
    db.refresh(node)
    return node


def save_inference(db: Session, payload: InferenceIn) -> dict:
    record_id = payload.record_id or next_id(db, InspectionRecord, "record_id", "rec")
    statuses = [item.status for item in payload.detections]
    overall_status = highest_status(statuses)

    record = InspectionRecord(
        record_id=record_id,
        node_id=payload.node_id,
        device_id=payload.device_id,
        inspected_at=payload.captured_at,
        image_uri=payload.image_uri,
        model_version=payload.model_version,
        overall_status=overall_status,
    )
    db.add(record)
    db.flush()

    alerts: list[Alert] = []
    for detection in payload.detections:
        db.add(
            DetectionResult(
                record_id=record_id,
                label=detection.label,
                confidence=detection.confidence,
                bbox=json.dumps(detection.bbox),
                status=detection.status,
                description=detection.description,
            )
        )
        if detection.status in {"warning", "critical"}:
            alert = Alert(
                alert_id=next_id(db, Alert, "alert_id", "alert"),
                record_id=record_id,
                device_id=payload.device_id,
                level=detection.status,
                type=f"{detection.label}_{detection.status}",
                description=detection.description or f"检测到 {detection.label} 状态为 {detection.status}",
                status="open",
                created_at=now_text(),
                image_uri=payload.image_uri,
            )
            db.add(alert)
            db.flush()
            alerts.append(alert)

    db.commit()
    return {
        "record_id": record_id,
        "overall_status": overall_status,
        "alert_count": len(alerts),
        "alerts": [alert_to_dict(alert, include_advice=False) for alert in alerts],
    }


def detection_to_dict(detection: DetectionResult) -> dict:
    return {
        "label": detection.label,
        "confidence": detection.confidence,
        "bbox": json.loads(detection.bbox),
        "status": detection.status,
        "description": detection.description,
    }


def advice_to_dict(advice: MaintenanceAdvice | None) -> dict | None:
    if advice is None:
        return None
    return {
        "advice_id": advice.advice_id,
        "alert_id": advice.alert_id,
        "summary": advice.summary,
        "possible_cause": advice.possible_cause,
        "risk_level": advice.risk_level,
        "action_steps": json.loads(advice.action_steps),
        "source": advice.source,
    }


def alert_to_dict(alert: Alert, include_advice: bool = True) -> dict:
    data = {
        "alert_id": alert.alert_id,
        "record_id": alert.record_id,
        "device_id": alert.device_id,
        "level": alert.level,
        "type": alert.type,
        "description": alert.description,
        "status": alert.status,
        "created_at": alert.created_at,
        "image_uri": alert.image_uri,
    }
    if include_advice:
        data["advice"] = advice_to_dict(alert.advice)
    return data


def record_to_dict(record: InspectionRecord, detail: bool = False) -> dict:
    data = {
        "record_id": record.record_id,
        "node_id": record.node_id,
        "device_id": record.device_id,
        "inspected_at": record.inspected_at,
        "image_uri": record.image_uri,
        "model_version": record.model_version,
        "overall_status": record.overall_status,
    }
    if detail:
        data["detections"] = [detection_to_dict(item) for item in record.detections]
        data["alerts"] = [alert_to_dict(item) for item in record.alerts]
    else:
        data["detection_count"] = len(record.detections)
        data["alert_count"] = len(record.alerts)
    return data


def get_latest_status(db: Session) -> dict:
    node = db.scalar(select(EdgeNode).order_by(EdgeNode.last_heartbeat.desc()))
    record = db.scalar(
        select(InspectionRecord)
        .options(joinedload(InspectionRecord.detections), joinedload(InspectionRecord.alerts))
        .order_by(InspectionRecord.inspected_at.desc())
    )
    active_alerts = db.scalars(select(Alert).where(Alert.status.in_(["open", "reviewing"]))).all()
    summary = {"normal_count": 0, "pending_review_count": 0, "warning_count": 0, "critical_count": 0}
    for alert in active_alerts:
        key = f"{alert.level}_count"
        if key in summary:
            summary[key] += 1
    return {
        "edge_node": None if node is None else {
            "node_id": node.node_id,
            "status": node.status,
            "model_version": node.model_version,
            "last_heartbeat": node.last_heartbeat,
        },
        "latest_record": None if record is None else record_to_dict(record, detail=True),
        "summary": summary,
    }


def explain_alert(db: Session, alert_id: str) -> dict | None:
    alert = db.get(Alert, alert_id)
    if alert is None:
        return None
    if alert.advice is not None:
        return advice_to_dict(alert.advice)

    advice = MaintenanceAdvice(
        advice_id=next_id(db, MaintenanceAdvice, "advice_id", "advice"),
        alert_id=alert.alert_id,
        summary=f"{alert.description}，建议进行现场复核。",
        possible_cause="可能存在设备异常、回路故障、保护动作或告警未复位。",
        risk_level=alert.level,
        action_steps=json.dumps([
            "核对现场指示灯、仪表和设备运行状态",
            "查看设备运行日志或保护装置记录",
            "由专业运维人员确认是否需要检修",
        ], ensure_ascii=False),
        source="template",
    )
    db.add(advice)
    db.commit()
    db.refresh(advice)
    return advice_to_dict(advice)


def create_report(db: Session, payload: ReportIn) -> dict:
    query = select(InspectionRecord).options(
        joinedload(InspectionRecord.detections), joinedload(InspectionRecord.alerts)
    ).where(
        InspectionRecord.inspected_at >= payload.start_time,
        InspectionRecord.inspected_at <= payload.end_time,
    )
    if payload.device_id:
        query = query.where(InspectionRecord.device_id == payload.device_id)
    records = db.scalars(query.order_by(InspectionRecord.inspected_at)).unique().all()

    warning_count = sum(1 for record in records if record.overall_status == "warning")
    critical_count = sum(1 for record in records if record.overall_status == "critical")
    pending_count = sum(1 for record in records if record.overall_status == "pending_review")
    normal_count = sum(1 for record in records if record.overall_status == "normal")
    summary = {
        "record_count": len(records),
        "normal_count": normal_count,
        "pending_review_count": pending_count,
        "warning_count": warning_count,
        "critical_count": critical_count,
    }

    report_id = next_id(db, Report, "report_id", "report")
    file_name = f"{report_id}.html"
    file_path = REPORT_DIR / file_name
    file_path.write_text(render_report_html(payload, records, summary), encoding="utf-8")

    report = Report(
        report_id=report_id,
        start_time=payload.start_time,
        end_time=payload.end_time,
        device_id=payload.device_id,
        format="html",
        file_uri=f"/reports/{file_name}",
        generated_at=now_text(),
        summary=json.dumps(summary, ensure_ascii=False),
    )
    db.add(report)
    db.commit()

    return {
        "report_id": report_id,
        "format": "html",
        "file_uri": report.file_uri,
        "summary": summary,
        "generated_at": report.generated_at,
    }


def render_report_html(payload: ReportIn, records: list[InspectionRecord], summary: dict) -> str:
    rows = []
    for record in records:
        rows.append(
            "<tr>"
            f"<td>{escape(record.record_id)}</td>"
            f"<td>{escape(record.device_id or '-')}</td>"
            f"<td>{escape(record.inspected_at)}</td>"
            f"<td>{escape(record.overall_status)}</td>"
            f"<td>{len(record.detections)}</td>"
            f"<td>{len(record.alerts)}</td>"
            f"<td>{escape(record.image_uri)}</td>"
            "</tr>"
        )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>电力智能巡检报告</title>
  <style>
    body {{ font-family: Arial, "Microsoft YaHei", sans-serif; margin: 32px; color: #1f2937; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 16px; }}
    th, td {{ border: 1px solid #d1d5db; padding: 8px; text-align: left; }}
    th {{ background: #f3f4f6; }}
  </style>
</head>
<body>
  <h1>电力智能巡检报告</h1>
  <p>时间范围：{escape(payload.start_time)} 至 {escape(payload.end_time)}</p>
  <p>设备：{escape(payload.device_id or "全部设备")}</p>
  <h2>统计摘要</h2>
  <ul>
    <li>巡检次数：{summary["record_count"]}</li>
    <li>正常：{summary["normal_count"]}</li>
    <li>待复核：{summary["pending_review_count"]}</li>
    <li>一般告警：{summary["warning_count"]}</li>
    <li>严重告警：{summary["critical_count"]}</li>
  </ul>
  <h2>巡检明细</h2>
  <table>
    <thead><tr><th>记录</th><th>设备</th><th>时间</th><th>状态</th><th>检测数</th><th>告警数</th><th>图片</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</body>
</html>
"""
