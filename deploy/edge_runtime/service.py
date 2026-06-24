import os
from typing import Any, Dict, Optional

from fastapi import Body, FastAPI, HTTPException
from pydantic import BaseModel

from edge_runtime.camera_reader import CameraReader
from edge_runtime.config import load_config
from edge_runtime.inference_engine import build_inference_engine
from edge_runtime.pipeline import InspectionPipeline
from edge_runtime.uploader import CloudUploader


class InspectRequest(BaseModel):
    device_id: Optional[str] = None
    source: Optional[str] = "api"


config = load_config()
camera = CameraReader(config)
inference = build_inference_engine(config)
uploader = CloudUploader(config)
pipeline = InspectionPipeline(config, camera, inference, uploader)

app = FastAPI(title="Atlas Edge Runtime", version="2.0.0")


@app.get("/health")
def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "node_id": config.node_id,
        "model_version": config.model_version,
        "cloud_base_url": config.cloud_base_url,
        "inference_mode": config.inference_mode,
        "use_camera": config.use_camera,
        "camera_index": config.camera_index,
    }


@app.post("/heartbeat")
def heartbeat() -> Dict[str, Any]:
    try:
        return {"status": "ok", "data": uploader.post_heartbeat()}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"heartbeat upload failed: {exc}")


@app.post("/inspect")
def inspect(payload: Optional[InspectRequest] = Body(default=None)) -> Dict[str, Any]:
    request = payload or InspectRequest()
    try:
        result = pipeline.run_once(device_id=request.device_id)
        return {"status": "ok", "source": request.source, "data": result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"inspection failed: {exc}")


def main() -> None:
    import uvicorn

    host = os.getenv("EDGE_SERVICE_HOST", "0.0.0.0")
    port = int(os.getenv("EDGE_SERVICE_PORT", "9000"))
    uvicorn.run("edge_runtime.service:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
