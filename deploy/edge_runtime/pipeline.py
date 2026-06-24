from typing import Any, Dict, Optional

from edge_runtime.camera_reader import CameraReader
from edge_runtime.config import EdgeConfig
from edge_runtime.inference_engine import InferenceEngine
from edge_runtime.uploader import CloudUploader


class InspectionPipeline:
    def __init__(
        self,
        config: EdgeConfig,
        camera: CameraReader,
        inference: InferenceEngine,
        uploader: CloudUploader,
    ):
        self.config = config
        self.camera = camera
        self.inference = inference
        self.uploader = uploader

    def sync_deployment_config(self) -> bool:
        """Check cloud for latest model version. Returns True if config changed."""
        try:
            cfg = self.uploader.fetch_deployment_config()
            remote_version = cfg.get("model_version")
            if remote_version and remote_version != self.config.model_version:
                print(f"model version update: {self.config.model_version} → {remote_version}")
                return True
        except Exception as exc:
            print(f"deployment config fetch failed: {exc}")
        return False

    def run_once(self, device_id: Optional[str] = None) -> Dict[str, Any]:
        capture = self.camera.capture()
        detections = self.inference.infer(capture.image_path)
        evidence = self.uploader.upload_evidence(capture.image_path, capture.captured_at)
        result = self.uploader.upload_inference(
            image_uri=evidence["image_uri"],
            captured_at=capture.captured_at,
            detections=detections,
            device_id=device_id or self.config.device_id,
        )

        # P4: dual upload — also send raw detection data
        detection_data = {
            "image_uri": evidence["image_uri"],
            "device_id": device_id or self.config.device_id,
        }
        try:
            self.uploader.upload_detection_data(**detection_data)
        except Exception as exc:
            print(f"detection data upload failed (non-fatal): {exc}")

        return {
            "captured_at": capture.captured_at,
            "local_image_path": str(capture.image_path),
            "image_uri": evidence["image_uri"],
            "detections": detections,
            "cloud_result": result,
        }
