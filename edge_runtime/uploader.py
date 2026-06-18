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

    # ── P4 additions ─────────────────────────────────────────

    def fetch_deployment_config(self) -> Dict[str, Any]:
        """Pull latest model version and inference config from cloud."""
        return self._get_json(f"/api/edge/deployment-config?node_id={self.config.node_id}")

    def upload_detection_data(
        self,
        image_uri: str,
        device_id: Optional[str] = None,
        temperature: Optional[float] = None,
        voltage: Optional[float] = None,
        current: Optional[float] = None,
        meter_value: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Upload raw sensor/detection metadata to cloud."""
        payload = {
            "device_id": device_id or self.config.device_id,
            "node_id": self.config.node_id,
            "image_uri": image_uri,
            "temperature": temperature,
            "voltage": voltage,
            "current": current,
            "meter_value": meter_value,
            "collect_time": now_text(),
        }
        return self._post_json("/api/edge/detection-data", payload)["data"]

    def fetch_commands(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Claim pending cloud commands for this edge node."""
        data = self._get_json(f"/api/edge/commands?node_id={self.config.node_id}&limit={limit}")
        if isinstance(data, list):
            return data
        return data.get("items", [])

    def ack_command(
        self,
        command_id: str,
        status: str,
        result: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Report command execution state back to cloud."""
        payload: Dict[str, Any] = {"status": status}
        if result is not None:
            payload["result"] = result
        if error_message:
            payload["error_message"] = error_message
        return self._post_json(f"/api/edge/commands/{command_id}/ack", payload)["data"]

    def download_model(self, model_id: str) -> Path:
        """Download a model file from cloud to local runtime dir."""
        target = self.config.runtime_dir / f"{model_id}.om"
        with httpx.Client(timeout=120.0, follow_redirects=True) as client:
            response = client.get(
                f"{self.base_url}/api/models/{model_id}/file",
                headers=self.headers,
            )
            response.raise_for_status()
            target.write_bytes(response.content)
        print(f"model downloaded: {target} ({target.stat().st_size} bytes)")
        return target

    # ── helpers ───────────────────────────────────────────────

    def _get_json(self, path: str) -> Dict[str, Any]:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            response = client.get(f"{self.base_url}{path}", headers=self.headers)
            response.raise_for_status()
            body = response.json()
        return body.get("data", body)

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
