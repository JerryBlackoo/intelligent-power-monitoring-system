#!/usr/bin/env bash
set -e

DEVICE_ID=${1:-cabinet_01}

PROJECT_DIR=/home/HwHiAiUser/intelligent-power-monitoring-system-new
VENV_DIR=/home/HwHiAiUser/intelligent-power-monitoring-system/venv-edge
IMAGE_DIR=${PROJECT_DIR}/camera_images

mkdir -p ${IMAGE_DIR}

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
IMAGE_FILE=${IMAGE_DIR}/dual_camera_${TIMESTAMP}.jpg

cd ${PROJECT_DIR}

echo
echo "=================================================="
echo "        双模型摄像头巡检"
echo "=================================================="
echo "设备ID     : ${DEVICE_ID}"
echo "摄像头     : /dev/video0"
echo "拍照时间   : $(date '+%Y-%m-%d %H:%M:%S')"
echo "=================================================="
echo

echo "[1/3] 摄像头拍照..."

fswebcam \
  -d /dev/video0 \
  -r 1280x720 \
  --no-banner \
  ${IMAGE_FILE} >/dev/null 2>&1

if [ ! -f "${IMAGE_FILE}" ]; then
    echo "❌ 拍照失败"
    exit 1
fi

echo "✅ 拍照成功"
echo "图片路径: ${IMAGE_FILE}"

echo
echo "[2/3] 加载环境..."

source ${VENV_DIR}/bin/activate
source /usr/local/Ascend/ascend-toolkit/set_env.sh

echo
echo "[3/3] 双模型推理并上传云端..."

python dual_model_upload_image.py ${IMAGE_FILE} ${DEVICE_ID}

echo
echo "=================================================="
echo "双模型摄像头巡检完成"
echo "=================================================="
