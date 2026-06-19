import csv
import io
import json
import re
from html import escape
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.orm import object_session

from app.config import IMAGE_DIR, REPORT_DIR
from app.entitys import (
    AlarmEvent,
    Device,
    EdgeCommand,
    EdgeNode,
    InferenceResult,
    InspectionKnowledge,
    InspectionRecord,
    Model,
    ModelDeployment,
    OperationLog,
    Report,
    User,
)
from app.schemas import HeartbeatIn, InferenceIn, ReportIn
from app.utils import highest_status, next_id, now_text


# ═══════════════════════════ Edge Node ═══════════════════════════

def save_heartbeat(db: Session, payload: HeartbeatIn) -> EdgeNode:
    node = db.get(EdgeNode, payload.node_id)
    now = now_text()
    if node is None:
        node = EdgeNode(
            node_id=payload.node_id,
            node_name=payload.node_id,
            ip=payload.ip,
            location=None,
            status=payload.status,
            model_version=payload.model_version,
            last_heartbeat=payload.timestamp,
            created_at=now,
        )
        db.add(node)
    else:
        node.ip = payload.ip
        node.status = payload.status
        node.model_version = payload.model_version
        node.last_heartbeat = payload.timestamp
    db.commit()
    db.refresh(node)
    return node


def get_edge_nodes_with_devices(db: Session) -> list[dict]:
    nodes = db.scalars(select(EdgeNode).order_by(EdgeNode.last_heartbeat.desc())).all()
    return [
        {
            "node_id": node.node_id,
            "node_name": node.node_name,
            "ip": node.ip,
            "status": node.status,
            "model_version": node.model_version,
            "last_heartbeat": node.last_heartbeat,
            "devices": _devices_for_node(db, node.node_id),
        }
        for node in nodes
    ]


def _devices_for_node(db: Session, node_id: str) -> list[dict]:
    devs = db.scalars(
        select(Device).where(Device.node_id == node_id).order_by(Device.last_report_time.desc())
    ).all()
    results: list[dict] = []
    for dev in devs:
        latest_record = db.scalar(
            select(InspectionRecord)
            .where(InspectionRecord.device_id == dev.device_id)
            .order_by(InspectionRecord.inspected_at.desc())
        )
        results.append({
            "device_id": dev.device_id,
            "device_name": dev.device_name,
            "device_type": dev.device_type,
            "online_status": dev.online_status,
            "latest_status": latest_record.overall_status if latest_record else None,
            "last_inspected_at": latest_record.inspected_at if latest_record else None,
            "record_count": db.scalar(
                select(InspectionRecord).where(InspectionRecord.device_id == dev.device_id)
            ).count() if False else len(db.scalars(
                select(InspectionRecord).where(InspectionRecord.device_id == dev.device_id)
            ).all()),
        })
    return results


# ═══════════════════════════ Evidence ═══════════════════════════

def save_evidence_image(
    filename: str,
    contents: bytes,
    node_id: str,
    captured_at: str | None = None,
    record_id: str | None = None,
) -> dict:
    suffix = Path(filename).suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}:
        suffix = ".jpg"
    time_part = re.sub(r"[^0-9]", "", captured_at or now_text())[:14]
    safe_node = re.sub(r"[^A-Za-z0-9_-]", "_", node_id) or "edge"
    safe_record = re.sub(r"[^A-Za-z0-9_-]", "_", record_id or "") if record_id else ""
    stem = "_".join(part for part in [safe_node, safe_record, time_part] if part)
    target_name = f"{stem or 'evidence'}{suffix}"
    target_path = IMAGE_DIR / target_name
    counter = 1
    while target_path.exists():
        target_name = f"{stem or 'evidence'}_{counter}{suffix}"
        target_path = IMAGE_DIR / target_name
        counter += 1
    target_path.write_bytes(contents)
    return {
        "image_uri": f"/images/{target_name}",
        "filename": target_name,
        "size": len(contents),
    }


# ═══════════════════════════ Inference ═══════════════════════════

def save_inference(db: Session, payload: InferenceIn) -> dict:
    now = now_text()
    record_id = payload.record_id or next_id(db, InspectionRecord, "record_id", "rec")
    statuses = [item.status for item in payload.detections]
    overall_status = highest_status(statuses)

    # ensure device exists
    dev_id = payload.device_id or "unknown"
    if not db.get(Device, dev_id):
        db.add(Device(
            device_id=dev_id, device_name=dev_id, node_id=payload.node_id,
            device_type="auto", online_status="online", created_at=now,
        ))
        db.flush()

    # ensure edge_node exists
    if not db.get(EdgeNode, payload.node_id):
        db.add(EdgeNode(
            node_id=payload.node_id, node_name=payload.node_id,
            ip="unknown", status="online", model_version=payload.model_version,
            last_heartbeat=now, created_at=now,
        ))
        db.flush()

    # ensure model
    model_info = db.scalar(select(Model).where(Model.version == payload.model_version))
    if not model_info:
        model_id = next_id(db, Model, "model_id", "model")
        model_info = Model(
            model_id=model_id, model_name=payload.model_version,
            version=payload.model_version, model_file_uri=f"./model/{payload.model_version}.om",
            status="active", created_at=now, updated_at=now,
        )
        db.add(model_info)
        db.flush()

    # inference results
    inference_results: list[InferenceResult] = []
    for detection in payload.detections:
        infer = InferenceResult(
            result_id=next_id(db, InferenceResult, "result_id", "infer"),
            device_id=dev_id,
            node_id=payload.node_id,
            model_id=model_info.model_id,
            image_uri=payload.image_uri,
            detect_class=detection.label,
            confidence=detection.confidence,
            bbox=json.dumps(detection.bbox),
            abnormal_level=detection.status,
            infer_time=payload.captured_at,
            created_at=now,
        )
        db.add(infer)
        db.flush()
        inference_results.append(infer)

    # inspection record
    record = InspectionRecord(
        record_id=record_id,
        inspector_id=_default_inspector_id(db),
        device_id=dev_id,
        node_id=payload.node_id,
        result_id=inference_results[0].result_id if inference_results else None,
        description=None,
        image_uri=payload.image_uri,
        agent_advice=None,
        overall_status=overall_status,
        handle_status="pending",
        inspected_at=payload.captured_at,
        created_at=now,
        updated_at=now,
    )
    db.add(record)
    db.flush()

    # alarm events
    alarm_events: list[AlarmEvent] = []
    for detection, infer in zip(payload.detections, inference_results):
        if detection.status in {"warning", "critical"}:
            alarm = AlarmEvent(
                alarm_id=next_id(db, AlarmEvent, "alarm_id", "alarm"),
                device_id=dev_id,
                result_id=infer.result_id,
                record_id=record_id,
                alarm_type=f"{detection.label}_{detection.status}",
                alarm_level=detection.status,
                alarm_status="open",
                description=detection.description or f"检测到 {detection.label} 状态为 {detection.status}",
                image_uri=payload.image_uri,
                alarm_time=now,
                created_at=now,
            )
            db.add(alarm)
            db.flush()
            alarm_events.append(alarm)

    db.commit()
    return {
        "record_id": record_id,
        "overall_status": overall_status,
        "alert_count": len(alarm_events),
        "alerts": [alarm_event_to_dict(a) for a in alarm_events],
    }


# ═══════════════════════════ Edge Deployment Config ═══════════

def get_edge_deployment_config(db: Session, node_id: str) -> dict:
    """Return the latest model deployment config for an edge node."""
    from app.entitys import ModelDeployment
    deployment = db.scalar(
        select(ModelDeployment)
        .options(joinedload(ModelDeployment.model))
        .where(ModelDeployment.node_id == node_id, ModelDeployment.deploy_status == "deployed")
        .order_by(ModelDeployment.deploy_time.desc())
    )
    if deployment is None:
        active_model = db.scalar(select(Model).where(Model.status == "active").order_by(Model.updated_at.desc()))
        if active_model is None:
            return {"model_version": "unknown", "deploy_status": "none", "inference_config": None}
        return {
            "model_version": active_model.version,
            "deploy_status": "pending",
            "inference_config": None,
            "model_id": active_model.model_id,
        }
    return {
        "model_version": deployment.model.version,
        "deploy_status": deployment.deploy_status,
        "inference_config": json.loads(deployment.inference_config) if deployment.inference_config else None,
        "model_id": deployment.model_id,
        "deployment_id": deployment.deployment_id,
    }


def save_edge_detection_data(db: Session, payload: dict) -> dict:
    """Save raw sensor data from edge device."""
    from app.entitys import EdgeDetectionData
    now = now_text()
    data = EdgeDetectionData(
        data_id=next_id(db, EdgeDetectionData, "data_id", "edata"),
        device_id=payload.get("device_id", "unknown"),
        node_id=payload.get("node_id", "unknown"),
        image_uri=payload.get("image_uri"),
        temperature=payload.get("temperature"),
        voltage=payload.get("voltage"),
        current=payload.get("current"),
        meter_value=payload.get("meter_value"),
        collect_time=payload.get("collect_time", now),
        created_at=now,
    )
    db.add(data)
    db.commit()
    db.refresh(data)
    return {
        "data_id": data.data_id,
        "device_id": data.device_id,
        "collect_time": data.collect_time,
    }


# ═══════════════════════════ Edge Commands ════════════════════

def create_start_inspection_command(
    db: Session,
    device_id: str,
    source: str = "web",
    once: bool = True,
    payload: dict | None = None,
) -> dict | None:
    device = db.get(Device, device_id)
    if device is None:
        return None
    now = now_text()
    command_payload = {
        "source": source,
        "once": once,
        **(payload or {}),
    }
    command = EdgeCommand(
        command_id=next_id(db, EdgeCommand, "command_id", "cmd"),
        node_id=device.node_id,
        device_id=device.device_id,
        command_type="start_inspection",
        payload=json.dumps(command_payload, ensure_ascii=False),
        status="pending",
        created_at=now,
    )
    db.add(command)
    db.commit()
    db.refresh(command)
    return edge_command_to_dict(command)


def claim_edge_commands(db: Session, node_id: str, limit: int = 5) -> list[dict]:
    now = now_text()
    commands = db.scalars(
        select(EdgeCommand)
        .where(EdgeCommand.node_id == node_id, EdgeCommand.status == "pending")
        .order_by(EdgeCommand.created_at.asc())
        .limit(limit)
    ).all()
    for command in commands:
        command.status = "running"
        command.dispatched_at = now
    db.commit()
    for command in commands:
        db.refresh(command)
    return [edge_command_to_dict(command) for command in commands]


def ack_edge_command(db: Session, command_id: str, status: str, result: dict | None = None,
                     error_message: str | None = None) -> dict | None:
    command = db.get(EdgeCommand, command_id)
    if command is None:
        return None
    if status not in {"success", "failed", "running"}:
        raise ValueError("invalid command status")
    command.status = status
    if result is not None:
        command.result = json.dumps(result, ensure_ascii=False)
    if error_message:
        command.error_message = error_message
    if status in {"success", "failed"}:
        command.finished_at = now_text()
    db.commit()
    db.refresh(command)
    return edge_command_to_dict(command)


def get_edge_command(db: Session, command_id: str) -> dict | None:
    command = db.get(EdgeCommand, command_id)
    if command is None:
        return None
    return edge_command_to_dict(command)


def edge_command_to_dict(command: EdgeCommand) -> dict:
    return {
        "command_id": command.command_id,
        "node_id": command.node_id,
        "device_id": command.device_id,
        "command_type": command.command_type,
        "payload": json.loads(command.payload) if command.payload else {},
        "status": command.status,
        "created_at": command.created_at,
        "dispatched_at": command.dispatched_at,
        "finished_at": command.finished_at,
        "result": json.loads(command.result) if command.result else None,
        "error_message": command.error_message,
    }


# ═══════════════════════════ Dict Converters ═══════════════════

def _default_inspector_id(db: Session) -> str:
    user = db.scalar(select(User).where(User.role == "inspector"))
    if user:
        return user.user_id
    now = now_text()
    user = User(
        user_id="inspector_default",
        username="default_inspector",
        password_hash="default",
        role="inspector",
        status="active",
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    db.flush()
    return user.user_id


def inference_result_to_dict(ir: InferenceResult) -> dict:
    """Backward-compatible dict (maps detect_class→label, abnormal_level→status)."""
    return {
        "label": ir.detect_class,
        "confidence": float(ir.confidence),
        "bbox": json.loads(ir.bbox),
        "status": ir.abnormal_level,
        "description": ir.description,
    }


def alarm_event_to_dict(ae: AlarmEvent) -> dict:
    """Backward-compatible dict (maps alarm_id→alert_id etc.)."""
    return {
        "alert_id": ae.alarm_id,
        "record_id": ae.record_id,
        "device_id": ae.device_id,
        "level": ae.alarm_level,
        "type": ae.alarm_type,
        "description": ae.description,
        "status": ae.alarm_status,
        "created_at": ae.alarm_time,
        "resolved_time": ae.resolved_time,
        "image_uri": ae.image_uri,
    }


def knowledge_to_dict(k: InspectionKnowledge) -> dict:
    return {
        "knowledge_id": k.knowledge_id,
        "device_id": k.device_id,
        "device_type": k.device_type,
        "knowledge_type": k.knowledge_type,
        "title": k.title,
        "content": k.content,
        "tags": json.loads(k.tags) if k.tags else [],
        "source": k.source,
        "alarm_id": k.alarm_id,
    }


def record_to_dict(record: InspectionRecord, detail: bool = False) -> dict:
    model_version = _model_version_for_record(record)
    inference_results = _inference_results_for_record(record)
    alarm_events_list = record.alarm_events if hasattr(record, "alarm_events") and record.alarm_events else []
    active_alarm_count = sum(1 for alarm in alarm_events_list if alarm.alarm_status in {"open", "reviewing"})
    resolved_alarm_count = sum(1 for alarm in alarm_events_list if alarm.alarm_status == "resolved")

    # enrich with inference metadata for frontend
    backend = "待接入"
    inference_ms = None
    if record.inference_result and record.inference_result.inference_time_ms:
        inference_ms = float(record.inference_result.inference_time_ms)
    if record.inference_result and record.inference_result.model and record.inference_result.model.framework:
        backend = record.inference_result.model.framework

    data = {
        "record_id": record.record_id,
        "node_id": record.node_id,
        "device_id": record.device_id,
        "inspected_at": record.inspected_at,
        "image_uri": record.image_uri,
        "model_version": model_version,
        "overall_status": record.overall_status,
        "backend": backend,
        "inference_ms": inference_ms,
        "inspection_file_uri": record.inspection_file_uri,
        "inspection_file_name": record.inspection_file_name,
        "staff_name": record.inspector.username if record.inspector else None,
        "handle_status": record.handle_status,
        "agent_advice": record.agent_advice,
        "active_alert_count": active_alarm_count,
        "resolved_alert_count": resolved_alarm_count,
    }
    if detail:
        data["detections"] = [inference_result_to_dict(ir) for ir in inference_results]
        data["alerts"] = [alarm_event_to_dict(a) for a in alarm_events_list]
    else:
        data["detection_count"] = len(inference_results)
        data["alert_count"] = len(alarm_events_list)
    return data


def resolve_record_alerts(db: Session, record_id: str) -> dict | None:
    record = db.scalar(
        select(InspectionRecord)
        .options(joinedload(InspectionRecord.alarm_events))
        .where(InspectionRecord.record_id == record_id)
    )
    if record is None:
        return None
    now = now_text()
    resolved_count = 0
    for alarm in record.alarm_events:
        if alarm.alarm_status in {"open", "reviewing"}:
            alarm.alarm_status = "resolved"
            alarm.resolved_time = now
            resolved_count += 1
    if resolved_count:
        record.handle_status = "resolved"
        record.updated_at = now
    db.commit()
    db.refresh(record)
    return {
        "record_id": record.record_id,
        "resolved_count": resolved_count,
        "handle_status": record.handle_status,
        "active_alert_count": sum(1 for alarm in record.alarm_events if alarm.alarm_status in {"open", "reviewing"}),
        "resolved_at": now if resolved_count else None,
    }


def resolve_alarm(db: Session, alarm_id: str, remark: str | None = None) -> dict | None:
    alarm = db.get(AlarmEvent, alarm_id)
    if alarm is None:
        return None
    now = now_text()
    alarm.alarm_status = "resolved"
    alarm.resolved_time = now
    if remark:
        alarm.description = f"{alarm.description or ''}\n处理备注：{remark}".strip()
    db.commit()
    db.refresh(alarm)
    return alarm_event_to_dict(alarm)


def complete_inspection_record(
    db: Session,
    record_id: str,
    handler: str = "admin",
    remark: str | None = None,
    close_alerts: bool = True,
) -> dict | None:
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
        return None

    now = now_text()
    resolved_count = 0
    if close_alerts:
        for alarm in record.alarm_events:
            if alarm.alarm_status in {"open", "reviewing"}:
                alarm.alarm_status = "resolved"
                alarm.resolved_time = now
                resolved_count += 1

    record.handle_status = "resolved"
    record.updated_at = now
    advice_parts = [record.agent_advice] if record.agent_advice else []
    complete_note = f"{handler} 已完成现场处理"
    if remark:
        complete_note = f"{complete_note}：{remark}"
    advice_parts.append(complete_note)
    record.agent_advice = "\n".join(advice_parts)
    db.commit()
    db.refresh(record)
    return {
        "record": record_to_dict(record),
        "resolved_alert_count": resolved_count,
        "completed_at": now,
    }


def _model_version_for_record(record: InspectionRecord) -> str:
    if record.inference_result and record.inference_result.model:
        return record.inference_result.model.version
    return "unknown"


def _inference_results_for_record(record: InspectionRecord) -> list[InferenceResult]:
    """Collect inference results linked to this record."""
    results: list[InferenceResult] = []
    if record.inference_result:
        results.append(record.inference_result)
    if hasattr(record, "alarm_events") and record.alarm_events:
        for alarm in record.alarm_events:
            if alarm.inference_result and alarm.inference_result not in results:
                results.append(alarm.inference_result)
    db = object_session(record)
    if db is not None and record.image_uri and record.inspected_at:
        related = db.scalars(
            select(InferenceResult)
            .where(
                InferenceResult.device_id == record.device_id,
                InferenceResult.node_id == record.node_id,
                InferenceResult.image_uri == record.image_uri,
                InferenceResult.infer_time == record.inspected_at,
            )
            .order_by(InferenceResult.result_id)
        ).all()
        for item in related:
            if item not in results:
                results.append(item)
    return results


# ═══════════════════════════ Status ═══════════════════════════

def get_latest_status(db: Session) -> dict:
    node = db.scalar(select(EdgeNode).order_by(EdgeNode.last_heartbeat.desc()))
    record = db.scalar(
        select(InspectionRecord)
        .options(
            joinedload(InspectionRecord.inspector),
            joinedload(InspectionRecord.inference_result).joinedload(InferenceResult.model),
            joinedload(InspectionRecord.alarm_events).joinedload(AlarmEvent.inference_result),
        )
        .order_by(InspectionRecord.inspected_at.desc())
    )
    active_alarms = db.scalars(
        select(AlarmEvent).where(AlarmEvent.alarm_status.in_(["open", "reviewing"]))
    ).all()
    summary = {"normal_count": 0, "pending_review_count": 0, "warning_count": 0, "critical_count": 0}
    for a in active_alarms:
        key = f"{a.alarm_level}_count"
        if key in summary:
            summary[key] += 1
    return {
        "edge_node": None if node is None else {
            "node_id": node.node_id,
            "node_name": node.node_name,
            "status": node.status,
            "model_version": node.model_version,
            "last_heartbeat": node.last_heartbeat,
        },
        "latest_record": None if record is None else record_to_dict(record, detail=True),
        "summary": summary,
    }


# ═══════════════════════════ Alerts ═══════════════════════════

def explain_alert(db: Session, alarm_id: str) -> dict | None:
    alarm = db.scalar(
        select(AlarmEvent)
        .options(joinedload(AlarmEvent.knowledge))
        .where(AlarmEvent.alarm_id == alarm_id)
    )
    if alarm is None:
        return None
    if alarm.knowledge:
        # return first knowledge item as the "advice"
        existing = alarm.knowledge[0] if alarm.knowledge else None
        if existing:
            return {
                "advice_id": existing.knowledge_id,
                "alert_id": alarm.alarm_id,
                "summary": existing.title,
                "possible_cause": existing.content[:200],
                "risk_level": alarm.alarm_level,
                "action_steps": [],
                "source": existing.source,
            }

    now = now_text()
    k = InspectionKnowledge(
        knowledge_id=next_id(db, InspectionKnowledge, "knowledge_id", "info"),
        device_id=alarm.device_id,
        device_type=None,
        knowledge_type="advice",
        title=f"{alarm.description}，建议进行现场复核。",
        content=f"可能存在设备异常、回路故障、保护动作或告警未复位。\n"
                f"建议：核对现场指示灯、仪表和设备运行状态；"
                f"查看设备运行日志或保护装置记录；"
                f"由专业运维人员确认是否需要检修。",
        tags=None,
        source="template",
        alarm_id=alarm.alarm_id,
        created_at=now,
        updated_at=now,
    )
    db.add(k)
    db.commit()
    db.refresh(k)
    return {
        "advice_id": k.knowledge_id,
        "alert_id": alarm.alarm_id,
        "summary": k.title,
        "possible_cause": k.content[:200],
        "risk_level": alarm.alarm_level,
        "action_steps": [],
        "source": k.source,
    }


# ═══════════════════════════ Reports ═══════════════════════════

def create_report(db: Session, payload: ReportIn) -> dict:
    query = select(InspectionRecord).options(
        joinedload(InspectionRecord.inference_result),
        joinedload(InspectionRecord.alarm_events),
    ).where(
        InspectionRecord.inspected_at >= payload.start_time,
        InspectionRecord.inspected_at <= payload.end_time,
    )
    if payload.device_id:
        query = query.where(InspectionRecord.device_id == payload.device_id)
    records = db.scalars(query.order_by(InspectionRecord.inspected_at)).unique().all()

    summary = _report_summary(records)
    report_id = next_id(db, Report, "report_id", "report")
    report_format = payload.format.lower()
    if report_format not in {"html", "csv"}:
        report_format = "html"
    file_name = f"{report_id}.{report_format}"
    file_path = REPORT_DIR / file_name
    if report_format == "csv":
        file_path.write_text(render_report_csv(payload, records, summary), encoding="utf-8-sig", newline="")
    else:
        file_path.write_text(render_report_html(payload, records, summary), encoding="utf-8")

    report = Report(
        report_id=report_id,
        start_time=payload.start_time,
        end_time=payload.end_time,
        device_id=payload.device_id,
        format=report_format,
        file_uri=f"/reports/{file_name}",
        generated_at=now_text(),
        summary=json.dumps(summary, ensure_ascii=False),
    )
    db.add(report)
    db.commit()

    return {
        "report_id": report_id,
        "format": report_format,
        "file_uri": report.file_uri,
        "file_name": file_name,
        "summary": summary,
        "generated_at": report.generated_at,
    }


def save_uploaded_report(
    db: Session,
    filename: str,
    contents: bytes,
    device_id: str | None = None,
    record_id: str | None = None,
    handler: str | None = None,
    handle_status: str = "reviewing",
    note: str | None = None,
) -> dict:
    if not contents:
        raise ValueError("empty report file")

    now = now_text()
    report_id = next_id(db, Report, "report_id", "report")
    original_name = filename or "inspection_report"
    suffix = Path(original_name).suffix.lower() or ".bin"
    if suffix not in {".pdf", ".doc", ".docx", ".jpg", ".jpeg", ".png", ".txt", ".html"}:
        suffix = ".bin"
    safe_stem = re.sub(r"[^A-Za-z0-9_-]", "_", Path(original_name).stem)[:80] or "report"
    file_name = f"{report_id}_{safe_stem}{suffix}"
    file_path = REPORT_DIR / file_name
    file_path.write_bytes(contents)

    related_record = db.get(InspectionRecord, record_id) if record_id else None
    resolved_device_id = device_id or (related_record.device_id if related_record else None)
    generated_by = _user_id_by_username(db, handler) if handler else None
    file_uri = f"/reports/{file_name}"
    summary = {
        "type": "uploaded_report",
        "original_filename": original_name,
        "stored_filename": file_name,
        "size": len(contents),
        "device_id": resolved_device_id,
        "record_id": record_id,
        "handler": handler,
        "handle_status": handle_status,
        "note": note,
    }

    report = Report(
        report_id=report_id,
        start_time=now,
        end_time=now,
        device_id=resolved_device_id,
        format=suffix.lstrip("."),
        file_uri=file_uri,
        summary=json.dumps(summary, ensure_ascii=False),
        generated_by=generated_by,
        generated_at=now,
    )
    db.add(report)

    if related_record:
        related_record.inspection_file_uri = file_uri
        related_record.inspection_file_name = original_name
        related_record.handle_status = handle_status
        related_record.updated_at = now
        if note:
            existing = related_record.agent_advice or ""
            prefix = f"[{now}] {handler or 'inspector'} 上传报告"
            related_record.agent_advice = "\n".join(part for part in [existing, f"{prefix}: {note}"] if part)

    if resolved_device_id:
        device = db.get(Device, resolved_device_id)
        if device:
            device.last_report_time = now

    db.commit()
    db.refresh(report)
    return {
        "report_id": report.report_id,
        "file_uri": report.file_uri,
        "file_name": original_name,
        "format": report.format,
        "device_id": report.device_id,
        "record_id": record_id,
        "summary": summary,
        "generated_at": report.generated_at,
    }


def list_reports(db: Session, limit: int = 20) -> list[dict]:
    reports = db.scalars(select(Report).order_by(Report.generated_at.desc()).limit(limit)).all()
    return [
        {
            "report_id": report.report_id,
            "device_id": report.device_id,
            "format": report.format,
            "file_uri": report.file_uri,
            "summary": _loads_json(report.summary),
            "generated_by": report.generated_by,
            "generated_at": report.generated_at,
        }
        for report in reports
    ]


def _loads_json(value: str | None) -> object:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _user_id_by_username(db: Session, username: str | None) -> str | None:
    if not username:
        return None
    user = db.scalar(select(User).where(User.username == username))
    return user.user_id if user else None


def _report_summary(records: list[InspectionRecord]) -> dict:
    w = sum(1 for r in records if r.overall_status == "warning")
    c = sum(1 for r in records if r.overall_status == "critical")
    p = sum(1 for r in records if r.overall_status == "pending_review")
    n = sum(1 for r in records if r.overall_status == "normal")
    return {
        "record_count": len(records),
        "normal_count": n,
        "pending_review_count": p,
        "warning_count": w,
        "critical_count": c,
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
            f"<td>{len(_inference_results_for_record(record))}</td>"
            f"<td>{len(record.alarm_events) if hasattr(record, 'alarm_events') and record.alarm_events else 0}</td>"
            f"<td>{escape(record.image_uri or '')}</td>"
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


def render_report_csv(payload: ReportIn, records: list[InspectionRecord], summary: dict) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["电力智能巡检报告"])
    writer.writerow(["开始时间", payload.start_time])
    writer.writerow(["结束时间", payload.end_time])
    writer.writerow(["设备", payload.device_id or "全部设备"])
    writer.writerow([])
    writer.writerow(["统计项", "数量"])
    writer.writerow(["记录总数", summary["record_count"]])
    writer.writerow(["正常", summary["normal_count"]])
    writer.writerow(["待复核", summary["pending_review_count"]])
    writer.writerow(["一般告警", summary["warning_count"]])
    writer.writerow(["严重告警", summary["critical_count"]])
    writer.writerow([])
    writer.writerow(["记录", "设备", "时间", "状态", "检测数", "告警数", "图片"])
    for record in records:
        writer.writerow([
            record.record_id,
            record.device_id or "-",
            record.inspected_at,
            record.overall_status,
            len(_inference_results_for_record(record)),
            len(record.alarm_events) if hasattr(record, "alarm_events") and record.alarm_events else 0,
            record.image_uri or "",
        ])
    return output.getvalue()


# ═══════════════════════════ Device management ═════════════════

def get_devices(db: Session, node_id: str | None = None) -> list[dict]:
    query = select(Device)
    if node_id:
        query = query.where(Device.node_id == node_id)
    devices = db.scalars(query.order_by(Device.device_id)).all()
    return [_device_to_dict(db, d) for d in devices]


def get_device_detail(db: Session, device_id: str) -> dict | None:
    dev = db.get(Device, device_id)
    if dev is None:
        return None
    return _device_to_dict(db, dev)


def _device_to_dict(db: Session, dev: Device) -> dict:
    latest = db.scalar(
        select(InspectionRecord)
        .where(InspectionRecord.device_id == dev.device_id)
        .order_by(InspectionRecord.inspected_at.desc())
    )
    return {
        "device_id": dev.device_id,
        "device_name": dev.device_name,
        "node_id": dev.node_id,
        "location": dev.location,
        "device_type": dev.device_type,
        "online_status": dev.online_status,
        "last_report_time": dev.last_report_time,
        "latest_record": record_to_dict(latest, detail=False) if latest else None,
    }


def get_device_detection_data(db: Session, device_id: str, limit: int = 20) -> list[dict]:
    from app.entitys import EdgeDetectionData
    items = db.scalars(
        select(EdgeDetectionData)
        .where(EdgeDetectionData.device_id == device_id)
        .order_by(EdgeDetectionData.collect_time.desc())
        .limit(limit)
    ).all()
    return [
        {
            "data_id": d.data_id,
            "device_id": d.device_id,
            "node_id": d.node_id,
            "image_uri": d.image_uri,
            "temperature": float(d.temperature) if d.temperature else None,
            "voltage": float(d.voltage) if d.voltage else None,
            "current": float(d.current) if d.current else None,
            "meter_value": d.meter_value,
            "collect_time": d.collect_time,
            "created_at": d.created_at,
        }
        for d in items
    ]


# ═══════════════════════════ Model management ═════════════════

def get_models(db: Session) -> list[dict]:
    models = db.scalars(select(Model).order_by(Model.updated_at.desc())).all()
    return [_model_to_dict(db, m) for m in models]


def get_model_detail(db: Session, model_id: str) -> dict | None:
    m = db.get(Model, model_id)
    if m is None:
        return None
    return _model_to_dict(db, m)


def deploy_model(db: Session, model_id: str, node_id: str, config: dict | None = None) -> dict:
    now = now_text()
    deployment = ModelDeployment(
        deployment_id=next_id(db, ModelDeployment, "deployment_id", "deploy"),
        model_id=model_id,
        node_id=node_id,
        deploy_status="pending",
        deploy_time=now,
        inference_config=json.dumps(config, ensure_ascii=False) if config else None,
        created_at=now,
    )
    db.add(deployment)
    db.commit()
    db.refresh(deployment)
    return {
        "deployment_id": deployment.deployment_id,
        "model_id": deployment.model_id,
        "node_id": deployment.node_id,
        "deploy_status": deployment.deploy_status,
        "deploy_time": deployment.deploy_time,
    }


def _model_to_dict(db: Session, m: Model) -> dict:
    deploys = db.scalars(
        select(ModelDeployment).where(ModelDeployment.model_id == m.model_id)
    ).all()
    return {
        "model_id": m.model_id,
        "model_name": m.model_name,
        "version": m.version,
        "model_file_uri": m.model_file_uri,
        "input_size": m.input_size,
        "framework": m.framework,
        "status": m.status,
        "description": m.description,
        "created_at": m.created_at,
        "updated_at": m.updated_at,
        "deployment_count": len(deploys),
    }


# ═══════════════════════════ Knowledge ═══════════════════════

def search_knowledge(
    db: Session,
    device_type: str | None = None,
    knowledge_type: str | None = None,
    keyword: str | None = None,
    limit: int = 20,
) -> list[dict]:
    query = select(InspectionKnowledge)
    if device_type:
        query = query.where(InspectionKnowledge.device_type == device_type)
    if knowledge_type:
        query = query.where(InspectionKnowledge.knowledge_type == knowledge_type)
    items = db.scalars(query.order_by(InspectionKnowledge.updated_at.desc()).limit(limit)).all()
    return [knowledge_to_dict(k) for k in items]


def add_knowledge(db: Session, knowledge_type: str, title: str, content: str,
                  device_id: str | None = None, device_type: str | None = None,
                  tags: list[str] | None = None, alarm_id: str | None = None,
                  source: str = "manual") -> dict:
    now = now_text()
    k = InspectionKnowledge(
        knowledge_id=next_id(db, InspectionKnowledge, "knowledge_id", "info"),
        device_id=device_id,
        device_type=device_type,
        knowledge_type=knowledge_type,
        title=title,
        content=content,
        tags=json.dumps(tags, ensure_ascii=False) if tags else None,
        source=source,
        alarm_id=alarm_id,
        created_at=now,
        updated_at=now,
    )
    db.add(k)
    db.commit()
    db.refresh(k)
    return knowledge_to_dict(k)


# ═══════════════════════════ User ═══════════════════════════

def get_user_info(db: Session, user_id: str) -> dict | None:
    user = db.get(User, user_id)
    if user is None:
        return None
    return {
        "user_id": user.user_id,
        "username": user.username,
        "role": user.role,
        "phone": user.phone,
        "status": user.status,
        "created_at": user.created_at,
    }


def authenticate_user(db: Session, username: str, password: str) -> dict | None:
    user = db.scalar(select(User).where(User.username == username))
    if user is None or user.password_hash != password:
        return None
    if user.status != "active":
        return None
    return {
        "user_id": user.user_id,
        "username": user.username,
        "role": user.role,
        "phone": user.phone,
    }


def create_user(db: Session, username: str, password: str, role: str,
                phone: str | None = None) -> dict:
    now = now_text()
    user = User(
        user_id=next_id(db, User, "user_id", "user"),
        username=username,
        password_hash=password,
        role=role,
        phone=phone,
        status="active",
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {
        "user_id": user.user_id,
        "username": user.username,
        "role": user.role,
        "phone": user.phone,
    }


def list_users(db: Session) -> list[dict]:
    users = db.scalars(select(User).order_by(User.created_at.desc())).all()
    return [
        {
            "user_id": u.user_id,
            "username": u.username,
            "role": u.role,
            "phone": u.phone,
            "status": u.status,
            "created_at": u.created_at,
        }
        for u in users
    ]


# ═══════════════════════════ Operation Log ═════════════════════

def log_operation(db: Session, user_id: str, operation_type: str,
                  target_type: str | None = None, target_id: str | None = None,
                  detail: str | None = None, ip_address: str | None = None) -> None:
    now = now_text()
    db.add(OperationLog(
        log_id=next_id(db, OperationLog, "log_id", "log"),
        user_id=user_id,
        operation_type=operation_type,
        target_type=target_type,
        target_id=target_id,
        detail=detail,
        ip_address=ip_address,
        operation_time=now,
    ))
    db.commit()
