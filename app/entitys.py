from sqlalchemy import DECIMAL, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# ──────────────────────────── 1. users (D1) ────────────────────────────

class User(Base):
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)

    inspection_records: Mapped[list["InspectionRecord"]] = relationship(back_populates="inspector")
    reports: Mapped[list["Report"]] = relationship(back_populates="generated_by_user")
    operation_logs: Mapped[list["OperationLog"]] = relationship(back_populates="user")


# ──────────────────────────── 2. edge_nodes (D2 扩展) ────────────────────

class EdgeNode(Base):
    __tablename__ = "edge_nodes"

    node_id: Mapped[str] = mapped_column(String, primary_key=True)
    node_name: Mapped[str] = mapped_column(String, nullable=False)
    ip: Mapped[str] = mapped_column(String, nullable=False)
    location: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    model_version: Mapped[str] = mapped_column(String, nullable=False)
    last_heartbeat: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)

    devices: Mapped[list["Device"]] = relationship(back_populates="edge_node")
    detection_data: Mapped[list["EdgeDetectionData"]] = relationship(back_populates="edge_node")
    inference_results: Mapped[list["InferenceResult"]] = relationship(back_populates="edge_node")
    model_deployments: Mapped[list["ModelDeployment"]] = relationship(back_populates="edge_node")
    inspection_records: Mapped[list["InspectionRecord"]] = relationship(back_populates="node")
    edge_commands: Mapped[list["EdgeCommand"]] = relationship(back_populates="edge_node")


# ──────────────────────────── 3. devices (D2 新建) ──────────────────────

class Device(Base):
    __tablename__ = "devices"

    device_id: Mapped[str] = mapped_column(String, primary_key=True)
    device_name: Mapped[str] = mapped_column(String, nullable=False)
    node_id: Mapped[str] = mapped_column(ForeignKey("edge_nodes.node_id"), nullable=False)
    location: Mapped[str | None] = mapped_column(String, nullable=True)
    device_type: Mapped[str] = mapped_column(String, nullable=False)
    online_status: Mapped[str] = mapped_column(String, nullable=False, default="offline")
    last_report_time: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)

    edge_node: Mapped[EdgeNode] = relationship(back_populates="devices")
    detection_data: Mapped[list["EdgeDetectionData"]] = relationship(back_populates="device")
    inference_results: Mapped[list["InferenceResult"]] = relationship(back_populates="device")
    inspection_records: Mapped[list["InspectionRecord"]] = relationship(back_populates="device")
    alarm_events: Mapped[list["AlarmEvent"]] = relationship(back_populates="device")
    knowledge: Mapped[list["InspectionKnowledge"]] = relationship(back_populates="device_kr")
    edge_commands: Mapped[list["EdgeCommand"]] = relationship(back_populates="device")


# ──────────────────────────── 4. edge_detection_data (D3 新建) ─────────

class EdgeDetectionData(Base):
    __tablename__ = "edge_detection_data"

    data_id: Mapped[str] = mapped_column(String, primary_key=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.device_id"), nullable=False)
    node_id: Mapped[str] = mapped_column(ForeignKey("edge_nodes.node_id"), nullable=False)
    image_uri: Mapped[str | None] = mapped_column(String, nullable=True)
    temperature: Mapped[float | None] = mapped_column(DECIMAL(6, 2), nullable=True)
    voltage: Mapped[float | None] = mapped_column(DECIMAL(8, 2), nullable=True)
    current: Mapped[float | None] = mapped_column(DECIMAL(8, 2), nullable=True)
    meter_value: Mapped[str | None] = mapped_column(String, nullable=True)
    collect_time: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)

    device: Mapped[Device] = relationship(back_populates="detection_data")
    edge_node: Mapped[EdgeNode] = relationship(back_populates="detection_data")


# ──────────────────────────── 5. inference_results (D4 从 detection_results 改名+扩展) ─

class InferenceResult(Base):
    __tablename__ = "inference_results"

    result_id: Mapped[str] = mapped_column(String, primary_key=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.device_id"), nullable=False)
    node_id: Mapped[str] = mapped_column(ForeignKey("edge_nodes.node_id"), nullable=False)
    model_id: Mapped[str] = mapped_column(ForeignKey("models.model_id"), nullable=False)
    image_uri: Mapped[str | None] = mapped_column(String, nullable=True)
    detect_class: Mapped[str] = mapped_column(String, nullable=False)
    confidence: Mapped[float] = mapped_column(DECIMAL(4, 3), nullable=False)
    bbox: Mapped[str] = mapped_column(String, nullable=False)
    abnormal_level: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    inference_time_ms: Mapped[float | None] = mapped_column(DECIMAL(8, 2), nullable=True)
    infer_time: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)

    device: Mapped[Device] = relationship(back_populates="inference_results")
    edge_node: Mapped[EdgeNode] = relationship(back_populates="inference_results")
    model: Mapped["Model"] = relationship(back_populates="inference_results")
    alarm_events: Mapped[list["AlarmEvent"]] = relationship(back_populates="inference_result")
    inspection_records: Mapped[list["InspectionRecord"]] = relationship(back_populates="inference_result")


# ──────────────────────────── 6. models (D6 新建) ───────────────────────

class Model(Base):
    __tablename__ = "models"

    model_id: Mapped[str] = mapped_column(String, primary_key=True)
    model_name: Mapped[str] = mapped_column(String, nullable=False)
    version: Mapped[str] = mapped_column(String, nullable=False)
    model_file_uri: Mapped[str] = mapped_column(String, nullable=False)
    input_size: Mapped[str | None] = mapped_column(String, nullable=True)
    framework: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)

    inference_results: Mapped[list[InferenceResult]] = relationship(back_populates="model")
    deployments: Mapped[list["ModelDeployment"]] = relationship(back_populates="model")


# ──────────────────────────── 7. model_deployments (D6 新建) ───────────

class ModelDeployment(Base):
    __tablename__ = "model_deployments"

    deployment_id: Mapped[str] = mapped_column(String, primary_key=True)
    model_id: Mapped[str] = mapped_column(ForeignKey("models.model_id"), nullable=False)
    node_id: Mapped[str] = mapped_column(ForeignKey("edge_nodes.node_id"), nullable=False)
    deploy_status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    deploy_time: Mapped[str] = mapped_column(String, nullable=False)
    inference_config: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)

    model: Mapped[Model] = relationship(back_populates="deployments")
    edge_node: Mapped[EdgeNode] = relationship(back_populates="model_deployments")


# ──────────────────────────── 8. inspection_records (D5 扩展) ──────────

class InspectionRecord(Base):
    __tablename__ = "inspection_records"

    record_id: Mapped[str] = mapped_column(String, primary_key=True)
    inspector_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.device_id"), nullable=False)
    node_id: Mapped[str] = mapped_column(ForeignKey("edge_nodes.node_id"), nullable=False)
    result_id: Mapped[str | None] = mapped_column(ForeignKey("inference_results.result_id"), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_uri: Mapped[str | None] = mapped_column(String, nullable=True)
    inspection_file_uri: Mapped[str | None] = mapped_column(String, nullable=True)
    inspection_file_name: Mapped[str | None] = mapped_column(String, nullable=True)
    agent_advice: Mapped[str | None] = mapped_column(Text, nullable=True)
    overall_status: Mapped[str] = mapped_column(String, nullable=False)
    handle_status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    inspected_at: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)

    inspector: Mapped[User] = relationship(back_populates="inspection_records")
    device: Mapped[Device] = relationship(back_populates="inspection_records")
    node: Mapped[EdgeNode] = relationship(back_populates="inspection_records")
    inference_result: Mapped[InferenceResult | None] = relationship(back_populates="inspection_records")
    alarm_events: Mapped[list["AlarmEvent"]] = relationship(back_populates="inspection_record")


# ──────────────────────────── 9. alarm_events (D7 从 alerts 改名+扩展) ──

class AlarmEvent(Base):
    __tablename__ = "alarm_events"

    alarm_id: Mapped[str] = mapped_column(String, primary_key=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.device_id"), nullable=False)
    result_id: Mapped[str | None] = mapped_column(ForeignKey("inference_results.result_id"), nullable=True)
    record_id: Mapped[str | None] = mapped_column(ForeignKey("inspection_records.record_id"), nullable=True)
    alarm_type: Mapped[str] = mapped_column(String, nullable=False)
    alarm_level: Mapped[str] = mapped_column(String, nullable=False)
    alarm_status: Mapped[str] = mapped_column(String, nullable=False, default="open")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_uri: Mapped[str | None] = mapped_column(String, nullable=True)
    alarm_time: Mapped[str] = mapped_column(String, nullable=False)
    resolved_time: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)

    device: Mapped[Device] = relationship(back_populates="alarm_events")
    inference_result: Mapped[InferenceResult | None] = relationship(back_populates="alarm_events")
    inspection_record: Mapped[InspectionRecord | None] = relationship(back_populates="alarm_events")
    knowledge: Mapped[list["InspectionKnowledge"]] = relationship(back_populates="alarm_event_kr")


# ──────────────────────────── 10. inspection_knowledge (D8) ────────────

class InspectionKnowledge(Base):
    __tablename__ = "inspection_knowledge"

    knowledge_id: Mapped[str] = mapped_column(String, primary_key=True)
    device_id: Mapped[str | None] = mapped_column(ForeignKey("devices.device_id"), nullable=True)
    device_type: Mapped[str | None] = mapped_column(String, nullable=True)
    knowledge_type: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[str | None] = mapped_column(String, nullable=True)
    source: Mapped[str] = mapped_column(String, nullable=False)
    alarm_id: Mapped[str | None] = mapped_column(ForeignKey("alarm_events.alarm_id"), nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)

    device_kr: Mapped[Device | None] = relationship(back_populates="knowledge")
    alarm_event_kr: Mapped[AlarmEvent | None] = relationship(back_populates="knowledge")


# ──────────────────────────── 11. edge_commands (云端命令下发) ───────────

class EdgeCommand(Base):
    __tablename__ = "edge_commands"

    command_id: Mapped[str] = mapped_column(String, primary_key=True)
    node_id: Mapped[str] = mapped_column(ForeignKey("edge_nodes.node_id"), nullable=False)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.device_id"), nullable=False)
    command_type: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    dispatched_at: Mapped[str | None] = mapped_column(String, nullable=True)
    finished_at: Mapped[str | None] = mapped_column(String, nullable=True)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    edge_node: Mapped[EdgeNode] = relationship(back_populates="edge_commands")
    device: Mapped[Device] = relationship(back_populates="edge_commands")


# ──────────────────────────── 12. operation_logs (新建) ──────────────────

class OperationLog(Base):
    __tablename__ = "operation_logs"

    log_id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    operation_type: Mapped[str] = mapped_column(String, nullable=False)
    target_type: Mapped[str | None] = mapped_column(String, nullable=True)
    target_id: Mapped[str | None] = mapped_column(String, nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String, nullable=True)
    operation_time: Mapped[str] = mapped_column(String, nullable=False)

    user: Mapped[User] = relationship(back_populates="operation_logs")


# ──────────────────────────── 13. reports (D7 扩展) ─────────────────────

class Report(Base):
    __tablename__ = "reports"

    report_id: Mapped[str] = mapped_column(String, primary_key=True)
    start_time: Mapped[str] = mapped_column(String, nullable=False)
    end_time: Mapped[str] = mapped_column(String, nullable=False)
    device_id: Mapped[str | None] = mapped_column(ForeignKey("devices.device_id"), nullable=True)
    format: Mapped[str] = mapped_column(String, nullable=False, default="html")
    file_uri: Mapped[str] = mapped_column(String, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    generated_by: Mapped[str | None] = mapped_column(ForeignKey("users.user_id"), nullable=True)
    generated_at: Mapped[str] = mapped_column(String, nullable=False)

    generated_by_user: Mapped[User | None] = relationship(back_populates="reports")
