# 开发板模型部署与推理说明

本目录用于将训练/转换后的 Ascend `.om` 模型部署到 Atlas 开发板，在开发板侧完成图像采集、模型推理、结果合并和云端上传。当前目录同时提供两种运行方式：

- 外层脚本：面向实际巡检的双模型摄像头抓拍、推理和上传。
- `edge_runtime/`：面向服务化部署的 FastAPI 接口和后台轮询运行时。

## 目录结构

| 路径 | 说明 |
| --- | --- |
| `models/device_detect_best.om` | 设备检测模型，Ascend OM 格式。 |
| `models/device_detect.names` | 设备检测类别：`insulator`、`air_switch`、`distribution_cabinet`、`photovoltaic_panel`。 |
| `models/state_defect_best.om` | 状态/缺陷检测模型，Ascend OM 格式。 |
| `models/state_defect.names` | 状态/缺陷检测类别，如绝缘子破损、配电柜状态、光伏板缺陷等。 |
| `run_single_model_json.py` | 单个 OM 模型推理入口，输出 JSON，便于单模型调试。 |
| `dual_model_upload_image.py` | 对一张本地图片依次运行设备检测模型和状态/缺陷模型，合并结果并上传云端。 |
| `dual_model_camera_inspect.sh` | 使用 `/dev/video0` 抓拍一张图片，然后执行双模型推理和上传。 |
| `dual_model_camera_loop.sh` | 按固定时间间隔循环执行摄像头巡检。 |
| `stop_service.sh` | 停止 `uvicorn` 或 `edge_runtime.service` 相关进程。 |
| `edge_runtime/` | 开发板端 Python 运行时，包含采集、推理、上传、服务接口和后台轮询逻辑。 |
| `edge_runtime/inference_engine.py.bak` | 推理引擎备份文件，不是默认运行入口。 |
| `edge_runtime/__pycache__/` | Python 运行缓存，可忽略，不需要手工维护。 |

## 部署位置

外层脚本中的默认开发板路径是：

```bash
/home/HwHiAiUser/intelligent-power-monitoring-system-new
```

建议将 `deploy` 目录中的内容复制到该目录下，使文件布局如下：

```text
/home/HwHiAiUser/intelligent-power-monitoring-system-new/
├── run_single_model_json.py
├── dual_model_upload_image.py
├── dual_model_camera_inspect.sh
├── dual_model_camera_loop.sh
├── stop_service.sh
├── models/
└── edge_runtime/
```

如果开发板上的实际路径不同，需要同步修改以下脚本中的 `PROJECT_DIR`：

- `dual_model_upload_image.py`
- `dual_model_camera_inspect.sh`
- `dual_model_camera_loop.sh`

`dual_model_camera_inspect.sh` 还默认使用虚拟环境：

```bash
/home/HwHiAiUser/intelligent-power-monitoring-system/venv-edge
```

如虚拟环境路径不同，需要修改脚本中的 `VENV_DIR`。

## 环境准备

开发板需具备 Ascend CANN/ACL 运行环境、Python 3.9、OpenCV/NumPy，以及摄像头采集工具。

```bash
cd /home/HwHiAiUser/intelligent-power-monitoring-system-new

python3.9 -m venv /home/HwHiAiUser/intelligent-power-monitoring-system/venv-edge
source /home/HwHiAiUser/intelligent-power-monitoring-system/venv-edge/bin/activate

python3.9 -m pip install -r edge_runtime/requirements-py39.txt

sudo apt-get update
sudo apt-get install -y python3-opencv v4l-utils fswebcam
```

运行 ACL/OM 推理前加载 Ascend 环境：

```bash
source /usr/local/Ascend/ascend-toolkit/set_env.sh
```

确认摄像头节点：

```bash
lsusb
ls -l /dev/video*
v4l2-ctl --list-formats-ext -d /dev/video0
```

## 快速验证

### 1. 单模型推理

使用设备检测模型：

```bash
source /home/HwHiAiUser/intelligent-power-monitoring-system/venv-edge/bin/activate
source /usr/local/Ascend/ascend-toolkit/set_env.sh

python run_single_model_json.py \
  models/device_detect_best.om \
  models/device_detect.names \
  /path/to/test.jpg
```

使用状态/缺陷检测模型：

```bash
python run_single_model_json.py \
  models/state_defect_best.om \
  models/state_defect.names \
  /path/to/test.jpg
```

输出格式示例：

```json
{
  "status": "ok",
  "model": "models/device_detect_best.om",
  "image": "/path/to/test.jpg",
  "detections": []
}
```

### 2. 本地图片双模型推理并上传

```bash
export CLOUD_BASE_URL="https://manila-landing-try.ngrok-free.dev"
export EDGE_NODE_ID="atlas_01"

python dual_model_upload_image.py /path/to/test.jpg cabinet_01
```

流程：

1. 调用 `run_single_model_json.py` 运行设备检测模型。
2. 调用 `run_single_model_json.py` 运行状态/缺陷检测模型。
3. 将两组检测结果合并。
4. 通过 `edge_runtime.uploader.CloudUploader` 上传证据图片和推理 JSON。

### 3. 摄像头单次巡检

```bash
bash dual_model_camera_inspect.sh cabinet_01
```

该脚本会使用 `fswebcam` 从 `/dev/video0` 抓拍，图片保存到：

```bash
/home/HwHiAiUser/intelligent-power-monitoring-system-new/camera_images
```

随后自动加载虚拟环境和 Ascend 环境，并执行双模型推理上传。

### 4. 摄像头循环巡检

```bash
bash dual_model_camera_loop.sh cabinet_01 10
```

参数说明：

- 第一个参数：设备 ID，默认 `cabinet_01`。
- 第二个参数：巡检间隔秒数，默认 `10`。

## `edge_runtime` 服务化运行

`edge_runtime/` 提供了另一套服务化运行方式，适合由云端或上位系统主动触发巡检。

### 运行 FastAPI 服务

首次联调建议先使用 mock 推理，确认云端链路可用：

```bash
cd /home/HwHiAiUser/intelligent-power-monitoring-system-new

export CLOUD_BASE_URL="https://manila-landing-try.ngrok-free.dev"
export EDGE_NODE_ID="atlas_01"
export EDGE_DEVICE_ID="cabinet_01"
export EDGE_MODEL_VERSION="yolov5s-power-v1"
export EDGE_INFERENCE_MODE="mock"

bash edge_runtime/start_service_py39.sh
```

接口：

| 接口 | 方法 | 说明 |
| --- | --- | --- |
| `/health` | GET | 查看节点编号、模型版本、推理模式和摄像头配置。 |
| `/heartbeat` | POST | 主动向云端上报一次心跳。 |
| `/inspect` | POST | 触发一次采集、推理、证据图上传和推理结果上传。 |

触发一次巡检：

```bash
curl -X POST http://127.0.0.1:9000/inspect \
  -H "Content-Type: application/json" \
  -d '{"device_id":"cabinet_01"}'
```

### 使用 OM 模型推理

```bash
export EDGE_INFERENCE_MODE="acl"
export EDGE_ACL_DEVICE_ID="0"
export EDGE_MODEL_PATH="models/device_detect_best.om"
export EDGE_CLASS_NAMES_PATH="models/device_detect.names"
export EDGE_CONF_THRESHOLD="0.25"
export EDGE_IOU_THRESHOLD="0.45"

python3.9 -m edge_runtime.service
```

`AclOmInferenceEngine` 会加载 `acl`、OpenCV 和 NumPy，执行 OM 模型，并进行基础 YOLO 后处理和 NMS。

### 后台轮询模式

如果希望开发板持续运行，可使用：

```bash
python3.9 -m edge_runtime.run_loop
```

`run_loop.py` 会循环执行：

- 定期向云端发送心跳。
- 从云端拉取待执行命令。
- 处理 `start_inspection` 命令。
- 定期同步部署配置。
- 按 `EDGE_INSPECT_INTERVAL_SECONDS` 自动巡检。

## 主要环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `CLOUD_BASE_URL` | `https://manila-landing-try.ngrok-free.dev` | 云端服务地址。 |
| `EDGE_NODE_ID` | `atlas_01` | 开发板节点 ID。 |
| `EDGE_DEVICE_ID` | `cabinet_01` | 默认巡检设备 ID。 |
| `EDGE_MODEL_VERSION` | `yolov5s-power-v1` | 上报到云端的模型版本。 |
| `EDGE_RUNTIME_DIR` | `./edge_runtime_data` | 运行时图片、下载模型等临时数据目录。 |
| `EDGE_IMAGE_SOURCE` | 空 | 指定本地图片作为采集输入，适合无摄像头调试。 |
| `EDGE_USE_CAMERA` | `false` | 是否使用 OpenCV 摄像头采集。 |
| `EDGE_CAMERA_INDEX` | `0` | OpenCV 摄像头序号。 |
| `EDGE_FRAME_WIDTH` | `640` | OpenCV 采集宽度。 |
| `EDGE_FRAME_HEIGHT` | `480` | OpenCV 采集高度。 |
| `EDGE_INFERENCE_MODE` | `mock` | 推理模式，`mock` 或 `acl`。 |
| `EDGE_FALLBACK_TO_MOCK` | `true` | ACL 初始化失败时是否回退 mock。 |
| `EDGE_ACL_DEVICE_ID` | `0` | Ascend 设备 ID。 |
| `EDGE_MODEL_PATH` | `./model/best.om` | 服务化运行时加载的 OM 模型路径。 |
| `EDGE_CLASS_NAMES_PATH` | `./model/label.names` | 服务化运行时加载的类别文件路径。 |
| `EDGE_CONF_THRESHOLD` | `0.25` | 置信度阈值。 |
| `EDGE_IOU_THRESHOLD` | `0.45` | NMS IOU 阈值。 |
| `EDGE_INSPECT_INTERVAL_SECONDS` | `30` | 后台自动巡检间隔。 |
| `EDGE_HEARTBEAT_INTERVAL_SECONDS` | `10` | 心跳上报间隔。 |
| `EDGE_SERVICE_HOST` | `0.0.0.0` | FastAPI 服务监听地址。 |
| `EDGE_SERVICE_PORT` | `9000` | FastAPI 服务端口。 |

## 云端交互

`CloudUploader` 会访问以下云端接口：

| 云端接口 | 说明 |
| --- | --- |
| `POST /api/edge/heartbeat` | 上报节点心跳。 |
| `POST /api/edge/evidence` | 上传巡检证据图片。 |
| `POST /api/edge/inference` | 上传推理结果。 |
| `POST /api/edge/detection-data` | 上传原始检测/采集数据，失败不影响主流程。 |
| `GET /api/edge/deployment-config` | 拉取部署配置和模型版本。 |
| `GET /api/edge/commands` | 拉取云端下发命令。 |
| `POST /api/edge/commands/{command_id}/ack` | 回传命令执行结果。 |
| `GET /api/models/{model_id}/file` | 下载模型文件到本地运行目录。 |

## 停止服务

```bash
bash stop_service.sh
```

该脚本会停止 `uvicorn` 和 `edge_runtime.service` 相关进程。

## 常见问题

### 找不到模型文件

确认 `.om` 和 `.names` 是否位于脚本配置的 `PROJECT_DIR/models/` 下。外层双模型脚本使用固定路径，目录变化后需要修改 `PROJECT_DIR`。

### `ImportError: ACL mode requires CANN acl, OpenCV and NumPy`

确认已加载 Ascend 环境，并且开发板 Python 环境中可以导入 `acl`、`cv2`、`numpy`：

```bash
source /usr/local/Ascend/ascend-toolkit/set_env.sh
python3.9 -c "import acl, cv2, numpy; print('ok')"
```

### 摄像头拍照失败

确认 `/dev/video0` 存在且当前用户有访问权限：

```bash
ls -l /dev/video0
fswebcam -d /dev/video0 -r 1280x720 --no-banner test.jpg
```

如果摄像头暂不可用，可以先用本地图片验证：

```bash
python dual_model_upload_image.py /path/to/test.jpg cabinet_01
```

### 云端上传失败

确认 `CLOUD_BASE_URL` 可访问，并检查云端服务是否提供 `/api/edge/evidence` 和 `/api/edge/inference` 等接口。当前上传器会自动添加 `ngrok-skip-browser-warning: true` 请求头，适配 ngrok 测试地址。

### 推理结果为空

可以降低服务化运行时阈值再测试：

```bash
export EDGE_CONF_THRESHOLD="0.01"
export EDGE_IOU_THRESHOLD="0.45"
```

同时确认 `.names` 文件类别数量与 `.om` 模型输出类别一致。
