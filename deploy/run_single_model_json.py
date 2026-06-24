from pathlib import Path
import os
import sys
import json

from edge_runtime.config import load_config
from edge_runtime.inference_engine import AclOmInferenceEngine

if len(sys.argv) < 4:
    print(json.dumps({
        "status": "error",
        "message": "usage: python run_single_model_json.py model.om labels.names image.jpg"
    }, ensure_ascii=False))
    sys.exit(1)

model_path = sys.argv[1]
label_path = sys.argv[2]
image_path = sys.argv[3]

os.environ["EDGE_MODEL_PATH"] = model_path
os.environ["EDGE_CLASS_NAMES_PATH"] = label_path
os.environ["EDGE_ACL_DEVICE_ID"] = "0"
os.environ["EDGE_CONFIDENCE_THRESHOLD"] = os.environ.get("EDGE_CONFIDENCE_THRESHOLD", "0.01")
os.environ["EDGE_IOU_THRESHOLD"] = os.environ.get("EDGE_IOU_THRESHOLD", "0.45")

config = load_config()
engine = None

try:
    engine = AclOmInferenceEngine(config)
    detections = engine.infer(Path(image_path))

    print(json.dumps({
        "status": "ok",
        "model": model_path,
        "image": image_path,
        "detections": detections
    }, ensure_ascii=False))

except Exception as e:
    print(json.dumps({
        "status": "error",
        "message": str(e),
        "model": model_path,
        "image": image_path
    }, ensure_ascii=False))
    sys.exit(1)

finally:
    if engine is not None:
        engine.close()
