import base64
import json
import mimetypes
import os
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.config import BASE_DIR
from app.schemas import AgentChatIn

try:
    from mcp_server.power_monitoring_mcp import (
        AlertDetailInput,
        AlertsInput,
        DiagnosticsInput,
        OverviewInput,
        RecordDetailInput,
        RecordsInput,
        get_alert_detail_data,
        get_record_detail_data,
        get_runtime_diagnostics_data,
        get_system_overview_data,
        list_alerts_data,
        list_records_data,
    )
except ModuleNotFoundError:
    class _LocalToolInput(BaseModel):
        model_config = ConfigDict(extra="ignore")


    class OverviewInput(_LocalToolInput):
        pass


    class DiagnosticsInput(_LocalToolInput):
        pass


    class RecordsInput(_LocalToolInput):
        device_id: str | None = None
        status: str | None = None
        limit: int = Field(default=20, ge=1)
        offset: int = Field(default=0, ge=0)
        include_detail: bool = False


    class RecordDetailInput(_LocalToolInput):
        record_id: str


    class AlertsInput(_LocalToolInput):
        device_id: str | None = None
        level: str | None = None
        status: str | None = None
        include_closed: bool = False
        limit: int = Field(default=20, ge=1)
        offset: int = Field(default=0, ge=0)


    class AlertDetailInput(_LocalToolInput):
        alert_id: str


    def _mcp_removed_message() -> str:
        return "mcp_server has been removed from this checkout; local power_* data tools are unavailable."


    def get_system_overview_data() -> dict[str, Any]:
        return {
            "project": {"mcp_server_available": False},
            "current": {"latest_record": None},
            "warnings": [_mcp_removed_message()],
        }


    def get_runtime_diagnostics_data() -> dict[str, Any]:
        return {
            "paths": {"project_root": str(BASE_DIR)},
            "mcp_server_available": False,
            "warnings": [_mcp_removed_message()],
        }


    def list_records_data(params: RecordsInput) -> dict[str, Any]:
        return {"error": _mcp_removed_message(), "items": [], "count": 0}


    def get_record_detail_data(record_id: str) -> dict[str, Any]:
        return {"error": _mcp_removed_message(), "record_id": record_id}


    def list_alerts_data(params: AlertsInput) -> dict[str, Any]:
        return {"error": _mcp_removed_message(), "items": [], "count": 0}


    def get_alert_detail_data(alert_id: str) -> dict[str, Any]:
        return {"error": _mcp_removed_message(), "alert_id": alert_id}


AGENT_SYSTEM_PROMPT = """你是电力智能巡检系统的现场 Agent。
你需要用中文回答，优先结合系统里的巡检记录、告警、运行诊断和用户上传的图片。
当用户问到记录、告警、设备、系统状态时，主动调用可用的 power_* 工具查询数据。
如果用户上传图片，请先描述图像中和电力巡检相关的可见内容，再给出检查建议。
不要编造不存在的 record_id、alert_id 或检测结果；查不到时说明需要先上传数据。"""


def chat_with_power_agent(payload: AgentChatIn) -> dict:
    api_key = (
        os.getenv("POWER_AGENT_API_KEY")
        or os.getenv("MIMO_API_KEY")
        or os.getenv("OPENAI_API_KEY")
    )
    base_url = (
        os.getenv("POWER_AGENT_BASE_URL")
        or os.getenv("MIMO_BASE_URL")
        or os.getenv("OPENAI_BASE_URL")
        or "https://token-plan-cn.xiaomimimo.com/v1"
    ).rstrip("/")
    model = os.getenv("POWER_AGENT_MODEL") or os.getenv("MIMO_MODEL") or "mimo-v2.5"

    if not api_key:
        return _fallback_response(payload, "Agent API key is not configured.")

    messages = _build_messages(payload)
    tool_calls_log: list[dict[str, Any]] = []

    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        for _ in range(5):
            body = {
                "model": model,
                "messages": messages,
                "tools": POWER_TOOLS,
                "tool_choice": "auto",
                "temperature": 0.2,
                "max_tokens": 1200,
            }
            response = client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            response.raise_for_status()
            message = response.json()["choices"][0]["message"]
            messages.append(message)
            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                return {
                    "reply": message.get("content") or "",
                    "tool_calls": tool_calls_log,
                    "model": model,
                }

            for tool_call in tool_calls:
                function = tool_call.get("function") or {}
                name = function.get("name", "")
                arguments = _parse_arguments(function.get("arguments"))
                result = dispatch_power_tool(name, arguments)
                tool_calls_log.append({"name": name, "arguments": arguments, "result_preview": str(result)[:300]})
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": json.dumps(result, ensure_ascii=False, default=str)[:12000],
                })

    return _fallback_response(payload, "Agent tool loop reached the maximum number of rounds.", tool_calls_log)


def dispatch_power_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    try:
        if name == "power_get_system_overview":
            OverviewInput(**arguments)
            return get_system_overview_data()
        if name == "power_list_records":
            return list_records_data(RecordsInput(**arguments))
        if name == "power_get_record_detail":
            params = RecordDetailInput(**arguments)
            return get_record_detail_data(params.record_id)
        if name == "power_list_alerts":
            return list_alerts_data(AlertsInput(**arguments))
        if name == "power_get_alert_detail":
            params = AlertDetailInput(**arguments)
            return get_alert_detail_data(params.alert_id)
        if name == "power_get_runtime_diagnostics":
            DiagnosticsInput(**arguments)
            return get_runtime_diagnostics_data()
        return {"error": f"Unknown tool: {name}"}
    except Exception as exc:
        return {"error": f"{name} failed: {exc}"}


def _build_messages(payload: AgentChatIn) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = [{"role": "system", "content": AGENT_SYSTEM_PROMPT}]
    for item in payload.history or []:
        if item.role in {"user", "assistant"} and item.content:
            messages.append({"role": item.role, "content": item.content})

    content: str | list[dict[str, Any]] = payload.message
    image_url = payload.image_data_url or _image_uri_to_data_url(payload.image_uri)
    if image_url:
        content = [
            {"type": "text", "text": payload.message},
            {"type": "image_url", "image_url": {"url": image_url}},
        ]
    messages.append({"role": "user", "content": content})
    return messages


def _image_uri_to_data_url(image_uri: str | None) -> str | None:
    if not image_uri:
        return None
    if image_uri.startswith("data:image/") or image_uri.startswith("http://") or image_uri.startswith("https://"):
        return image_uri
    if not image_uri.startswith("/"):
        return None
    path = (BASE_DIR / image_uri.lstrip("/")).resolve()
    if not path.is_file() or not path.is_relative_to(BASE_DIR):
        return None
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if not content_type.startswith("image/"):
        return None
    return f"data:{content_type};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def _parse_arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def _fallback_response(payload: AgentChatIn, reason: str, tool_calls: list[dict[str, Any]] | None = None) -> dict:
    overview = get_system_overview_data()
    latest = overview.get("current", {}).get("latest_record")
    reply = (
        f"{reason}\n\n"
        f"已收到你的问题：{payload.message}\n"
        f"当前系统最近巡检记录：{latest.get('record_id') if isinstance(latest, dict) else '暂无'}。\n"
        "配置 Agent API 后，我会结合图片理解和 MCP 查询工具给出完整分析。"
    )
    return {"reply": reply, "tool_calls": tool_calls or [], "model": "local-fallback"}


POWER_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "power_get_system_overview",
            "description": "获取电力巡检系统当前概览、最新记录、活跃告警统计和资产状态。",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "power_list_records",
            "description": "按设备、状态或分页查询巡检记录。",
            "parameters": {
                "type": "object",
                "properties": {
                    "device_id": {"type": "string"},
                    "status": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                    "offset": {"type": "integer", "minimum": 0},
                    "include_detail": {"type": "boolean"},
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "power_get_record_detail",
            "description": "查询单条巡检记录详情，包括检测框、告警和图片。",
            "parameters": {
                "type": "object",
                "properties": {"record_id": {"type": "string"}},
                "required": ["record_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "power_list_alerts",
            "description": "查询告警列表，可按设备、等级、状态过滤。",
            "parameters": {
                "type": "object",
                "properties": {
                    "device_id": {"type": "string"},
                    "level": {"type": "string"},
                    "status": {"type": "string"},
                    "include_closed": {"type": "boolean"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                    "offset": {"type": "integer", "minimum": 0},
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "power_get_alert_detail",
            "description": "查询单条告警详情及关联巡检记录。",
            "parameters": {
                "type": "object",
                "properties": {"alert_id": {"type": "string"}},
                "required": ["alert_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "power_get_runtime_diagnostics",
            "description": "查询后端、数据库、静态文件和模型文件的运行诊断信息。",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
]
