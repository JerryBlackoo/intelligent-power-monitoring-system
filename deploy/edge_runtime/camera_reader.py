from dataclasses import dataclass
from pathlib import Path
import shutil
from time import time

from edge_runtime.config import EdgeConfig
from edge_runtime.time_utils import now_text, timestamp_slug


_FALLBACK_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000002000000020802000000fdd49a"
    "730000001649444154789c63646060f8cf80c0c0400c0c0cff03000e8102fe"
    "a759b7cb0000000049454e44ae426082"
)


@dataclass(frozen=True)
class CaptureResult:
    image_path: Path
    captured_at: str


class CameraReader:
    def __init__(self, config: EdgeConfig):
        self.config = config

    def capture(self) -> CaptureResult:
        captured_at = now_text()
        target = self.config.runtime_dir / f"capture_{timestamp_slug(captured_at)}.jpg"

        if self.config.image_source:
            source = Path(self.config.image_source).expanduser().resolve()
            if not source.is_file():
                raise RuntimeError(f"EDGE_IMAGE_SOURCE does not exist: {source}")
            suffix = source.suffix.lower() or ".jpg"
            target = target.with_suffix(suffix)
            shutil.copyfile(source, target)
            return CaptureResult(target, captured_at)

        if self.config.use_camera:
            return self._capture_from_camera(target, captured_at)

        target = target.with_suffix(".png")
        target.write_bytes(_FALLBACK_PNG)
        return CaptureResult(target, captured_at)

    def _capture_from_camera(self, target: Path, captured_at: str) -> CaptureResult:
        try:
            import cv2
        except ImportError as exc:
            raise RuntimeError("OpenCV is required for camera capture") from exc

        cap = cv2.VideoCapture(self.config.camera_index)
        try:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.frame_width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.frame_height)
            ok, frame = cap.read()
            if not ok or frame is None:
                raise RuntimeError("camera unavailable or returned empty frame")
            if not cv2.imwrite(str(target), frame):
                raise RuntimeError(f"failed to save captured frame: {target}")
            return CaptureResult(target, captured_at)
        finally:
            cap.release()
