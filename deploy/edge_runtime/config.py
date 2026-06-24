from dataclasses import dataclass
import os
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class EdgeConfig:
    cloud_base_url: str
    node_id: str
    device_id: str
    model_version: str
    runtime_dir: Path
    image_source: Optional[str]
    use_camera: bool
    camera_index: int
    frame_width: int
    frame_height: int
    acl_device_id: int
    inference_mode: str
    fallback_to_mock: bool
    model_path: str
    class_names_path: str
    confidence_threshold: float
    iou_threshold: float
    inspect_interval_seconds: float
    heartbeat_interval_seconds: float


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_config() -> EdgeConfig:
    runtime_dir = Path(os.getenv("EDGE_RUNTIME_DIR", "./edge_runtime_data")).resolve()
    runtime_dir.mkdir(parents=True, exist_ok=True)
    image_source = os.getenv("EDGE_IMAGE_SOURCE")
    return EdgeConfig(
        cloud_base_url=os.getenv("CLOUD_BASE_URL", "https://manila-landing-try.ngrok-free.dev").rstrip("/"),
        node_id=os.getenv("EDGE_NODE_ID", "atlas_01"),
        device_id=os.getenv("EDGE_DEVICE_ID", "cabinet_01"),
        model_version=os.getenv("EDGE_MODEL_VERSION", "yolov5s-power-v1"),
        runtime_dir=runtime_dir,
        image_source=image_source if image_source else None,
        use_camera=_bool_env("EDGE_USE_CAMERA", False),
        camera_index=int(os.getenv("EDGE_CAMERA_INDEX", "0")),
        frame_width=int(os.getenv("EDGE_FRAME_WIDTH", "640")),
        frame_height=int(os.getenv("EDGE_FRAME_HEIGHT", "480")),
        acl_device_id=int(os.getenv("EDGE_ACL_DEVICE_ID", "0")),
        inference_mode=os.getenv("EDGE_INFERENCE_MODE", "mock").lower(),
        fallback_to_mock=_bool_env("EDGE_FALLBACK_TO_MOCK", True),
        model_path=os.getenv("EDGE_MODEL_PATH", "./model/best.om"),
        class_names_path=os.getenv("EDGE_CLASS_NAMES_PATH", "./model/label.names"),
        confidence_threshold=float(os.getenv("EDGE_CONF_THRESHOLD", "0.25")),
        iou_threshold=float(os.getenv("EDGE_IOU_THRESHOLD", "0.45")),
        inspect_interval_seconds=float(os.getenv("EDGE_INSPECT_INTERVAL_SECONDS", "30")),
        heartbeat_interval_seconds=float(os.getenv("EDGE_HEARTBEAT_INTERVAL_SECONDS", "10")),
    )
