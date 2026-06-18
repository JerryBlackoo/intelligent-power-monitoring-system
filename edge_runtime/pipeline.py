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
        return {
            "captured_at": capture.captured_at,
            "local_image_path": str(capture.image_path),
            "image_uri": evidence["image_uri"],
            "detections": detections,
            "cloud_result": result,
        }
