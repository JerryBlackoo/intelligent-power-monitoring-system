from pathlib import Path
import json
import os
import subprocess
import sys

from edge_runtime.config import load_config
from edge_runtime.uploader import CloudUploader
from edge_runtime.time_utils import now_text


PROJECT_DIR = "/home/HwHiAiUser/intelligent-power-monitoring-system-new"

DEVICE_MODEL = f"{PROJECT_DIR}/models/device_detect_best.om"
DEVICE_LABELS = f"{PROJECT_DIR}/models/device_detect.names"

STATE_MODEL = f"{PROJECT_DIR}/models/state_defect_best.om"
STATE_LABELS = f"{PROJECT_DIR}/models/state_defect.names"

RUN_SINGLE = f"{PROJECT_DIR}/run_single_model_json.py"


def run_model(model_path, label_path, image_path):
    env = os.environ.copy()
    env["EDGE_CONFIDENCE_THRESHOLD"] = "0.01"
    env["EDGE_IOU_THRESHOLD"] = "0.45"

    cmd = [
        sys.executable,
        RUN_SINGLE,
        model_path,
        label_path,
        image_path,
    ]

    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )

    if proc.returncode != 0:
        print(proc.stderr)
        print(proc.stdout)
        raise RuntimeError("模型推理失败")

    # stdout 里可能混有 warning，取最后一行 JSON
    lines = [x.strip() for x in proc.stdout.splitlines() if x.strip()]
    json_line = lines[-1]
    return json.loads(json_line)


def normalize_for_cloud(detections):
    cleaned = []

    for d in detections:
        conf = float(d.get("confidence", 0))
        conf = max(0.0, min(1.0, conf))

        cleaned.append({
            "label": str(d.get("label", "unknown")),
            "confidence": conf,
            "bbox": d.get("bbox", [0, 0, 0, 0]),
            "status": d.get("status", "normal"),
            "description": d.get("description") or f"检测到 {d.get('label', 'unknown')}",
        })

    return cleaned


def main():
    if len(sys.argv) < 2:
        print("用法: python dual_model_upload_image.py 图片路径 [设备ID]")
        sys.exit(1)

    image_path = str(Path(sys.argv[1]).resolve())
    device_id = sys.argv[2] if len(sys.argv) >= 3 else "cabinet_01"

    if not Path(image_path).is_file():
        raise FileNotFoundError(image_path)

    print()
    print("==================================================")
    print("        双模型本地图片推理 + 云端上传")
    print("==================================================")
    print("图片:", image_path)
    print("设备:", device_id)
    print("==================================================")

    print()
    print("[1/4] 模型1：设备检测")
    device_result = run_model(DEVICE_MODEL, DEVICE_LABELS, image_path)
    device_dets = device_result.get("detections", [])
    device_dets = normalize_for_cloud(device_dets)

    for d in device_dets:
        print(f"- device: {d['label']} | {d['confidence']:.4f} | {d['bbox']}")

    print()
    print("[2/4] 模型2：状态/缺陷检测")
    state_result = run_model(STATE_MODEL, STATE_LABELS, image_path)
    state_dets = state_result.get("detections", [])
    state_dets = normalize_for_cloud(state_dets)

    for d in state_dets:
        print(f"- state : {d['label']} | {d['confidence']:.4f} | {d['status']} | {d['bbox']}")

    print()
    print("[3/4] 合并检测结果")

    merged = []

    for d in device_dets:
        item = dict(d)
        item["description"] = f"设备检测：{d['label']}"
        merged.append(item)

    for d in state_dets:
        item = dict(d)
        item["description"] = f"状态检测：{d['label']}"
        merged.append(item)

    print("合并后检测数量:", len(merged))

    print()
    print("[4/4] 上传云端")

    os.environ["CLOUD_BASE_URL"] = os.environ.get(
        "CLOUD_BASE_URL",
        "https://manila-landing-try.ngrok-free.dev"
    )
    os.environ["EDGE_NODE_ID"] = os.environ.get("EDGE_NODE_ID", "atlas_01")
    os.environ["EDGE_DEVICE_ID"] = device_id
    os.environ["EDGE_MODEL_VERSION"] = "dual-device-state-v1"
    os.environ["MODEL_VERSION"] = "dual-device-state-v1"

    config = load_config()
    uploader = CloudUploader(config)

    captured_at = now_text()
    evidence = uploader.upload_evidence(Path(image_path), captured_at)
    image_uri = evidence["image_uri"]

    cloud_result = uploader.upload_inference(
        image_uri=image_uri,
        captured_at=captured_at,
        detections=merged,
        device_id=device_id,
    )

    print()
    print("✅ 上传成功")
    print("Record ID :", cloud_result.get("record_id"))
    print("云端状态  :", cloud_result.get("overall_status"))
    print("告警数    :", cloud_result.get("alert_count"))
    print("图片URI   :", image_uri)

    print()
    print("【最终检测结果】")
    for i, d in enumerate(merged, 1):
        print(f"{i}. {d['label']} | {d['confidence']:.4f} | {d['status']} | {d['bbox']}")

    print("==================================================")


if __name__ == "__main__":
    main()
