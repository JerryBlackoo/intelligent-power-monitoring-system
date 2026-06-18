# Atlas Edge Runtime

开发板端运行模块，负责摄像头采集、推理和上传到云端。

## Python 3.9 开发板服务

Atlas 开发板环境如果是 Python 3.9，请使用开发板端最小依赖：

```bash
cd intelligent-power-monitoring-system
python3.9 -m pip install -r edge_runtime/requirements-py39.txt
```

如果要使用 USB 摄像头，先在开发板上确认设备节点：

```bash
lsusb
ls -l /dev/video*
v4l2-ctl --list-formats-ext -d /dev/video0
```

摄像头采集依赖 OpenCV。Atlas/aarch64 环境优先使用系统包：

```bash
apt-get update
apt-get install -y python3-opencv v4l-utils
```

启动开发板端 FastAPI 服务：

```bash
bash edge_runtime/start_service_py39.sh
```

也可以直接启动：

```bash
export CLOUD_BASE_URL=https://manila-landing-try.ngrok-free.dev
export EDGE_INFERENCE_MODE=mock
python3.9 -m edge_runtime.service
```

服务接口：

| 接口 | 方法 | 说明 |
| --- | --- | --- |
| `/health` | GET | 查看开发板端服务、节点编号、推理模式、摄像头配置 |
| `/heartbeat` | POST | 主动向云端上报一次心跳 |
| `/inspect` | POST | 触发一次采集、推理、证据图上传和推理 JSON 上传 |

## Mock 联调

```bash
cd intelligent-power-monitoring-system
export CLOUD_BASE_URL=https://manila-landing-try.ngrok-free.dev
export EDGE_NODE_ID=atlas_01
export EDGE_DEVICE_ID=cabinet_01
export EDGE_MODEL_VERSION=yolov5s-power-v1
export EDGE_INFERENCE_MODE=mock
python -m uvicorn edge_runtime.service:app --host 0.0.0.0 --port 9000
```

触发一次巡检：

```bash
curl -X POST http://127.0.0.1:9000/inspect \
  -H "Content-Type: application/json" \
  -d '{"device_id":"cabinet_01"}'
```

## 摄像头采集

```bash
export EDGE_USE_CAMERA=1
export EDGE_CAMERA_INDEX=0
```

如果摄像头不稳定，可以使用本地图片兜底：

```bash
export EDGE_IMAGE_SOURCE=/path/to/test.jpg
```

## OM 推理

第一轮建议默认用 mock 推理打通云端链路。开发板 CANN 环境准备好后：

```bash
export EDGE_INFERENCE_MODE=acl
export EDGE_ACL_DEVICE_ID=0
export EDGE_MODEL_PATH=/path/to/best.om
export EDGE_CLASS_NAMES_PATH=/path/to/label.names
```

`AclOmInferenceEngine` 会在 Atlas 环境中懒加载 `acl`，执行 OM 模型并做基础 YOLO 后处理。
