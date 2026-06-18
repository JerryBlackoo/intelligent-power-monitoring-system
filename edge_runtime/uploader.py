from pathlib import Path
import socket
from typing import Any, Dict, List, Optional

import httpx

from edge_runtime.config import EdgeConfig
from edge_runtime.time_utils import now_text


class CloudUploader:
    def __init__(self, config: EdgeConfig):
        self.config = config
        self.base_url = config.cloud_base_url
        self.headers = {"ngrok-skip-browser-warning": "true"}

    def post_heartbeat(self, status: str = "online") -> Dict[str, Any]:
        payload = {
            "node_id": self.config.node_id,
            "ip": self._local_ip(),
            "status": status,
            "model_version": self.config.model_version,
            "timestamp": now_text(),
        }
        return self._post_json("/api/edge/heartbeat", payload)

    def upload_evidence(
        self,
        image_path: Path,
        captured_at: str,
        record_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        with image_path.open("rb") as f:
            files = {"file": (image_path.name, f, self._content_type(image_path))}
            data = {
                "node_id": self.config.node_id,
                "captured_at": captured_at,
            }
            if record_id:
                data["record_id"] = record_id
            with httpx.Client(timeout=30.0, follow_redirects=True) as client:
                response = client.post(
                    f"{self.base_url}/api/edge/evidence",
                    data=data,
                    files=files,
                    headers=self.headers,
                )
                response.raise_for_status()
                body = response.json()
        return body["data"]

    def upload_inference(
        self,
        image_uri: str,
        captured_at: str,
        detections: List[Dict[str, Any]],
        device_id: Optional[str] = None,
        record_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload = {
            "record_id": record_id,
            "node_id": self.config.node_id,
            "device_id": device_id or self.config.device_id,
            "captured_at": captured_at,
            "image_uri": image_uri,
            "model_version": self.config.model_version,
            "detections": detections,
        }
        if record_id is None:
            payload.pop("record_id")
        return self._post_json("/api/edge/inference", payload)["data"]

    def _post_json(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            response = client.post(f"{self.base_url}{path}", json=payload, headers=self.headers)
            response.raise_for_status()
            return response.json()

    @staticmethod
    def _content_type(path: Path) -> str:
        suffix = path.suffix.lower()
        if suffix == ".png":
            return "image/png"
        if suffix == ".bmp":
            return "image/bmp"
        if suffix == ".webp":
            return "image/webp"
        return "image/jpeg"

    @staticmethod
    def _local_ip() -> str:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect(("8.8.8.8", 80))
                return sock.getsockname()[0]
        except OSError:
            return "127.0.0.1"
