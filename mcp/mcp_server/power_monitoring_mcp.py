"""MCP server exposing read-only status for the power monitoring system.

Run from the repository root:
    python -m mcp_server.power_monitoring_mcp
"""

from __future__ import annotations

import json
import os
from enum import Enum
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session, joinedload

from app.config import BASE_DIR, DASHBOARD_DIR, DATA_DIR, IMAGE_DIR, REPORT_DIR
from app.database import SessionLocal, engine
from app.entitys import (
    AlarmEvent,
    Device,
    EdgeNode,
    InferenceResult,
    InspectionKnowledge,
    InspectionRecord,
    Model,
    ModelDeployment,
    Report,
)
from app.services import alarm_event_to_dict, record_to_dict


MCP_HOST = os.getenv("POWER_MCP_HOST", "127.0.0.1")
MCP_PORT = int(os.getenv("POWER_MCP_PORT", "8010"))
MCP_PATH = os.getenv("POWER_MCP_PATH", "/mcp")
MCP_TRANSPORT = os.getenv("POWER_MCP_TRANSPORT", "stdio").strip().lower()
MCP_DISABLE_DNS_REBINDING = os.getenv("POWER_MCP_DISABLE_DNS_REBINDING", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}


def _csv_env(name: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, "").split(",") if item.strip()]


MCP_ALLOWED_HOSTS = [
    "127.0.0.1",
    "127.0.0.1:*",
    "localhost",
    "localhost:*",
    "testserver",
    *_csv_env("POWER_MCP_ALLOWED_HOSTS"),
]
MCP_ALLOWED_ORIGINS = [
    "http://127.0.0.1:*",
    "http://localhost:*",
    *_csv_env("POWER_MCP_ALLOWED_ORIGINS"),
]

mcp = FastMCP(
    "power_monitoring_mcp",
    host=MCP_HOST,
    port=MCP_PORT,
    streamable_http_path=MCP_PATH,
    stateless_http=True,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=not MCP_DISABLE_DNS_REBINDING,
        allowed_hosts=MCP_ALLOWED_HOSTS,
        allowed_origins=MCP_ALLOWED_ORIGINS,
    ),
)


class ResponseFormat(str, Enum):
    JSON = "json"
    MARKDOWN = "markdown"


class BaseInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class OverviewInput(BaseInput):
    response_format: ResponseFormat = Field(
        default=ResponseFormat.JSON,
        description="Use 'json' for structured data or 'markdown' for a concise human-readable summary.",
    )


class RecordsInput(BaseInput):
    start_time: str | None = Field(
        default=None,
        description="Optional inclusive start time filter, e.g. '2026-06-16 00:00:00'.",
        max_length=32,
    )
    end_time: str | None = Field(
        default=None,
        description="Optional inclusive end time filter, e.g. '2026-06-16 23:59:59'.",
        max_length=32,
    )
    device_id: str | None = Field(
        default=None,
        description="Optional exact device id filter, e.g. 'cabinet_01'.",
        max_length=100,
    )
    status: str | None = Field(
        default=None,
        description="Optional overall status filter: normal, pending_review, warning, critical, or failed.",
        max_length=32,
    )
    limit: int = Field(default=20, description="Maximum records to return.", ge=1, le=100)
    offset: int = Field(default=0, description="Number of records to skip for pagination.", ge=0)
    include_detail: bool = Field(
        default=False,
        description="When true, include detections and alerts for each returned record.",
    )
    response_format: ResponseFormat = Field(default=ResponseFormat.JSON, description="Output format.")


class AlertsInput(BaseInput):
    level: str | None = Field(
        default=None,
        description="Optional exact alert level filter, e.g. warning or critical.",
        max_length=32,
    )
    device_id: str | None = Field(
        default=None,
        description="Optional exact device id filter, e.g. 'cabinet_01'.",
        max_length=100,
    )
    status: str | None = Field(
        default=None,
        description="Optional exact alert status. Defaults to open and reviewing alerts only.",
        max_length=32,
    )
    include_closed: bool = Field(
        default=False,
        description="When false, only open and reviewing alerts are returned.",
    )
    limit: int = Field(default=20, description="Maximum alerts to return.", ge=1, le=100)
    offset: int = Field(default=0, description="Number of alerts to skip for pagination.", ge=0)
    response_format: ResponseFormat = Field(default=ResponseFormat.JSON, description="Output format.")


class RecordDetailInput(BaseInput):
    record_id: str = Field(..., description="Inspection record id, e.g. 'rec_001'.", min_length=1, max_length=100)
    response_format: ResponseFormat = Field(default=ResponseFormat.JSON, description="Output format.")


class AlertDetailInput(BaseInput):
    alert_id: str = Field(..., description="Alert id, e.g. 'alert_001'.", min_length=1, max_length=100)
    response_format: ResponseFormat = Field(default=ResponseFormat.JSON, description="Output format.")


class DiagnosticsInput(BaseInput):
    response_format: ResponseFormat = Field(default=ResponseFormat.JSON, description="Output format.")


def _json_or_markdown(data: dict[str, Any], response_format: ResponseFormat, title: str) -> dict[str, Any] | str:
    if response_format == ResponseFormat.JSON:
        return data
    return _to_markdown(data, title)


def _to_markdown(data: dict[str, Any], title: str) -> str:
    lines = [f"# {title}", ""]
    for key, value in data.items():
        label = key.replace("_", " ")
        if isinstance(value, dict):
            lines.append(f"## {label}")
            for child_key, child_value in value.items():
                child_label = child_key.replace("_", " ")
                lines.append(f"- **{child_label}**: {_short_value(child_value)}")
            lines.append("")
        elif isinstance(value, list):
            lines.append(f"## {label}")
            if not value:
                lines.append("- none")
            else:
                for item in value[:20]:
                    lines.append(f"- {_short_value(item)}")
            lines.append("")
        else:
            lines.append(f"- **{label}**: {_short_value(value)}")
    return "\n".join(lines).strip()


def _short_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, default=str)
    if value is None:
        return "null"
    return str(value)


def _db_session() -> Session:
    return SessionLocal()


def _db_table_names() -> set[str]:
    try:
        return set(inspect(engine).get_table_names())
    except Exception:
        return set()


def _db_ready() -> bool:
    required = {
        EdgeNode.__tablename__,
        InspectionRecord.__tablename__,
        InferenceResult.__tablename__,
        AlarmEvent.__tablename__,
        InspectionKnowledge.__tablename__,
        Report.__tablename__,
    }
    return required.issubset(_db_table_names())


def _safe_count(db: Session, model: type) -> int:
    if model.__tablename__ not in _db_table_names():
        return 0
    return int(db.scalar(select(func.count()).select_from(model)) or 0)


def _directory_snapshot(path: Path) -> dict[str, Any]:
    files = [item for item in path.glob("*") if item.is_file() and item.name != ".gitkeep"]
    total_bytes = sum(item.stat().st_size for item in files)
    latest = max(files, key=lambda item: item.stat().st_mtime, default=None)
    return {
        "path": str(path),
        "exists": path.exists(),
        "file_count": len(files),
        "total_bytes": total_bytes,
        "latest_file": None if latest is None else latest.name,
    }


def _model_snapshot() -> dict[str, Any]:
    model_path = BASE_DIR / "model" / "best.om"
    return {
        "path": str(model_path),
        "exists": model_path.is_file(),
        "size_bytes": model_path.stat().st_size if model_path.is_file() else 0,
    }


def _pagination(total: int, count: int, offset: int) -> dict[str, Any]:
    next_offset = offset + count
    has_more = next_offset < total
    return {
        "total": total,
        "count": count,
        "offset": offset,
        "has_more": has_more,
        "next_offset": next_offset if has_more else None,
    }


def get_system_overview_data() -> dict[str, Any]:
    """Return aggregate health and current business status from local project data."""
    table_names = _db_table_names()
    db_exists = (DATA_DIR / "power_inspection.db").is_file()
    data: dict[str, Any] = {
        "project": {
            "name": "intelligent-power-monitoring-system",
            "root": str(BASE_DIR),
            "database_path": str(DATA_DIR / "power_inspection.db"),
            "database_exists": db_exists,
            "database_ready": _db_ready(),
            "tables": sorted(table_names),
        },
        "counts": {
            "edge_nodes": 0,
            "inspection_records": 0,
            "inference_results": 0,
            "alarm_events": 0,
            "inspection_knowledge": 0,
            "reports": 0,
        },
        "current": {
            "edge_node": None,
            "latest_record": None,
            "active_alert_summary": {"open": 0, "reviewing": 0, "warning": 0, "critical": 0},
        },
        "assets": {
            "images": _directory_snapshot(IMAGE_DIR),
            "reports": _directory_snapshot(REPORT_DIR),
            "dashboard_exists": (DASHBOARD_DIR / "index.html").is_file(),
            "model": _model_snapshot(),
        },
    }
    if not data["project"]["database_ready"]:
        data["warnings"] = ["Database file or expected tables are missing. Start the FastAPI app or run tests to create schema."]
        return data

    with _db_session() as db:
        data["counts"] = {
            "edge_nodes": _safe_count(db, EdgeNode),
            "inspection_records": _safe_count(db, InspectionRecord),
            "inference_results": _safe_count(db, InferenceResult),
            "alarm_events": _safe_count(db, AlarmEvent),
            "inspection_knowledge": _safe_count(db, InspectionKnowledge),
            "reports": _safe_count(db, Report),
        }
        node = db.scalar(select(EdgeNode).order_by(EdgeNode.last_heartbeat.desc()))
        record = db.scalar(
            select(InspectionRecord)
            .options(joinedload(InspectionRecord.inference_result), joinedload(InspectionRecord.alarm_events))
            .order_by(InspectionRecord.inspected_at.desc())
        )
        active_alarms = db.scalars(select(AlarmEvent).where(AlarmEvent.alarm_status.in_(["open", "reviewing"]))).all()
        summary = {"open": 0, "reviewing": 0, "warning": 0, "critical": 0}
        for alarm in active_alarms:
            if alarm.alarm_status in summary:
                summary[alarm.alarm_status] += 1
            if alarm.alarm_level in summary:
                summary[alarm.alarm_level] += 1
        data["current"] = {
            "edge_node": None
            if node is None
            else {
                "node_id": node.node_id,
                "ip": node.ip,
                "status": node.status,
                "model_version": node.model_version,
                "last_heartbeat": node.last_heartbeat,
            },
            "latest_record": None if record is None else record_to_dict(record, detail=True),
            "active_alert_summary": summary,
        }
    return data


def list_records_data(params: RecordsInput) -> dict[str, Any]:
    """Return paginated inspection records using optional business filters."""
    if not _db_ready():
        return {"error": "Database is not ready. Start the backend once so tables are created.", "items": []}

    with _db_session() as db:
        query = select(InspectionRecord).options(
            joinedload(InspectionRecord.inference_result), joinedload(InspectionRecord.alarm_events)
        )
        count_query = select(func.count()).select_from(InspectionRecord)
        filters = []
        if params.start_time:
            filters.append(InspectionRecord.inspected_at >= params.start_time)
        if params.end_time:
            filters.append(InspectionRecord.inspected_at <= params.end_time)
        if params.device_id:
            filters.append(InspectionRecord.device_id == params.device_id)
        if params.status:
            filters.append(InspectionRecord.overall_status == params.status)
        for condition in filters:
            query = query.where(condition)
            count_query = count_query.where(condition)

        total = int(db.scalar(count_query) or 0)
        records = (
            db.scalars(query.order_by(InspectionRecord.inspected_at.desc()).offset(params.offset).limit(params.limit))
            .unique()
            .all()
        )
        return {
            **_pagination(total, len(records), params.offset),
            "items": [record_to_dict(record, detail=params.include_detail) for record in records],
        }


def get_record_detail_data(record_id: str) -> dict[str, Any]:
    """Return a single inspection record with detections and related alerts."""
    if not _db_ready():
        return {"error": "Database is not ready. Start the backend once so tables are created."}

    with _db_session() as db:
        record = db.scalar(
            select(InspectionRecord)
            .options(joinedload(InspectionRecord.inference_result), joinedload(InspectionRecord.alarm_events))
            .where(InspectionRecord.record_id == record_id)
        )
        if record is None:
            return {"error": f"Record '{record_id}' was not found. Use power_list_records first to discover valid ids."}
        return record_to_dict(record, detail=True)


def list_alerts_data(params: AlertsInput) -> dict[str, Any]:
    """Return paginated alerts with optional level, device, and status filters."""
    if not _db_ready():
        return {"error": "Database is not ready. Start the backend once so tables are created.", "items": []}

    with _db_session() as db:
        query = select(AlarmEvent).options(joinedload(AlarmEvent.knowledge))
        count_query = select(func.count()).select_from(AlarmEvent)
        filters = []
        if not params.include_closed and not params.status:
            filters.append(AlarmEvent.alarm_status.in_(["open", "reviewing"]))
        if params.status:
            filters.append(AlarmEvent.alarm_status == params.status)
        if params.level:
            filters.append(AlarmEvent.alarm_level == params.level)
        if params.device_id:
            filters.append(AlarmEvent.device_id == params.device_id)
        for condition in filters:
            query = query.where(condition)
            count_query = count_query.where(condition)

        total = int(db.scalar(count_query) or 0)
        alerts = db.scalars(query.order_by(AlarmEvent.alarm_time.desc()).offset(params.offset).limit(params.limit)).all()
        return {
            **_pagination(total, len(alerts), params.offset),
            "items": [alarm_event_to_dict(alert) for alert in alerts],
        }


def get_alert_detail_data(alert_id: str) -> dict[str, Any]:
    """Return a single alert with advice and detections from its inspection record."""
    if not _db_ready():
        return {"error": "Database is not ready. Start the backend once so tables are created."}

    with _db_session() as db:
        alert = db.scalar(
            select(AlarmEvent)
            .options(
                joinedload(AlarmEvent.knowledge),
                joinedload(AlarmEvent.inspection_record).joinedload(InspectionRecord.inference_result),
            )
            .where(AlarmEvent.alarm_id == alert_id)
        )
        if alert is None:
            return {"error": f"Alert '{alert_id}' was not found. Use power_list_alerts first to discover valid ids."}
        data = alarm_event_to_dict(alert)
        data["related_detections"] = record_to_dict(alert.inspection_record, detail=True)["detections"]
        return data


def get_runtime_diagnostics_data() -> dict[str, Any]:
    """Return local filesystem and configuration diagnostics for deployment checks."""
    return {
        "paths": {
            "project_root": str(BASE_DIR),
            "data_dir": str(DATA_DIR),
            "image_dir": str(IMAGE_DIR),
            "report_dir": str(REPORT_DIR),
            "dashboard_dir": str(DASHBOARD_DIR),
        },
        "database": {
            "url": str(engine.url),
            "exists": (DATA_DIR / "power_inspection.db").is_file(),
            "ready": _db_ready(),
            "tables": sorted(_db_table_names()),
        },
        "assets": {
            "images": _directory_snapshot(IMAGE_DIR),
            "reports": _directory_snapshot(REPORT_DIR),
            "model": _model_snapshot(),
        },
        "api_entrypoints": [
            "GET /api/health",
            "POST /api/auth/login",
            "POST /api/auth/register",
            "POST /api/edge/heartbeat",
            "POST /api/edge/evidence",
            "POST /api/edge/inference",
            "POST /api/inspection/trigger",
            "GET /api/status/latest",
            "GET /api/edge/nodes",
            "GET /api/devices",
            "GET /api/devices/{device_id}",
            "GET /api/models",
            "GET /api/models/{model_id}",
            "POST /api/models/{model_id}/deploy",
            "GET /api/records",
            "GET /api/records/{record_id}",
            "GET /api/alerts/active",
            "GET /api/alerts/{alert_id}",
            "POST /api/alerts/{alert_id}/review",
            "POST /api/reports",
            "POST /api/llm/explain",
            "GET /api/knowledge",
            "POST /api/knowledge",
        ],
    }


@mcp.tool(
    name="power_get_system_overview",
    annotations={
        "title": "Get Power Monitoring System Overview",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def power_get_system_overview(params: OverviewInput = OverviewInput()) -> dict[str, Any] | str:
    """Get aggregate current state for the local intelligent power monitoring system.

    Args:
        params (OverviewInput): Output options.

    Returns:
        dict or str: Project, database, current node, latest inspection, active alert summary,
        evidence/report directory information, and model file status.
    """
    return _json_or_markdown(get_system_overview_data(), params.response_format, "Power Monitoring Overview")


@mcp.tool(
    name="power_list_records",
    annotations={
        "title": "List Power Inspection Records",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def power_list_records(params: RecordsInput = RecordsInput()) -> dict[str, Any] | str:
    """List inspection records with filters and pagination.

    Args:
        params (RecordsInput): Optional time range, device, status, limit, offset, detail flag,
        and output format.

    Returns:
        dict or str: Pagination metadata and inspection records. Records can include detections
        and alerts when include_detail is true.
    """
    return _json_or_markdown(list_records_data(params), params.response_format, "Inspection Records")


@mcp.tool(
    name="power_get_record_detail",
    annotations={
        "title": "Get Power Inspection Record Detail",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def power_get_record_detail(params: RecordDetailInput) -> dict[str, Any] | str:
    """Get one inspection record by id, including detections and related alerts.

    Args:
        params (RecordDetailInput): record_id and output format.

    Returns:
        dict or str: Detailed inspection record, or an actionable error if not found.
    """
    return _json_or_markdown(get_record_detail_data(params.record_id), params.response_format, "Inspection Record Detail")


@mcp.tool(
    name="power_list_alerts",
    annotations={
        "title": "List Power Alerts",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def power_list_alerts(params: AlertsInput = AlertsInput()) -> dict[str, Any] | str:
    """List alerts with status, level, device, and pagination filters.

    Args:
        params (AlertsInput): Optional level, device_id, status, include_closed, limit, offset,
        and output format.

    Returns:
        dict or str: Pagination metadata and alert summaries, including advice when available.
    """
    return _json_or_markdown(list_alerts_data(params), params.response_format, "Power Alerts")


@mcp.tool(
    name="power_get_alert_detail",
    annotations={
        "title": "Get Power Alert Detail",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def power_get_alert_detail(params: AlertDetailInput) -> dict[str, Any] | str:
    """Get one alert by id, including advice and detections from its inspection record.

    Args:
        params (AlertDetailInput): alert_id and output format.

    Returns:
        dict or str: Detailed alert data, or an actionable error if not found.
    """
    return _json_or_markdown(get_alert_detail_data(params.alert_id), params.response_format, "Power Alert Detail")


@mcp.tool(
    name="power_get_runtime_diagnostics",
    annotations={
        "title": "Get Power Monitoring Runtime Diagnostics",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def power_get_runtime_diagnostics(params: DiagnosticsInput = DiagnosticsInput()) -> dict[str, Any] | str:
    """Get local runtime diagnostics for MCP clients and deployment checks.

    Args:
        params (DiagnosticsInput): Output options.

    Returns:
        dict or str: Paths, database readiness, static artifact counts, model file status,
        and backend API entrypoints.
    """
    return _json_or_markdown(get_runtime_diagnostics_data(), params.response_format, "Runtime Diagnostics")


@mcp.resource("power://api")
def power_api_resource() -> str:
    """Expose backend API endpoint inventory as a resource."""
    return json.dumps(get_runtime_diagnostics_data()["api_entrypoints"], ensure_ascii=False, indent=2)


@mcp.resource("power://overview")
def power_overview_resource() -> str:
    """Expose the current monitoring overview as a JSON resource."""
    return json.dumps(get_system_overview_data(), ensure_ascii=False, indent=2, default=str)


def main() -> None:
    """Run the MCP server with stdio by default or Streamable HTTP when requested."""
    if MCP_TRANSPORT in {"http", "streamable-http", "streamable_http"}:
        mcp.run(transport="streamable-http")
        return
    if MCP_TRANSPORT == "sse":
        mcp.run(transport="sse")
        return
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
