#!/bin/bash

DEVICE_ID=${1:-cabinet_01}
INTERVAL=${2:-10}

PROJECT_DIR=/home/HwHiAiUser/intelligent-power-monitoring-system-new

cd ${PROJECT_DIR}

source /home/HwHiAiUser/intelligent-power-monitoring-system/venv-edge/bin/activate
source /usr/local/Ascend/ascend-toolkit/set_env.sh

echo "======================================"
echo " 双模型实时巡检"
echo "======================================"
echo "设备ID : ${DEVICE_ID}"
echo "间隔   : ${INTERVAL}s"
echo "======================================"

COUNT=0

while true
do
    COUNT=$((COUNT+1))

    echo
    echo "========== 第 ${COUNT} 次巡检 =========="
    echo "时间: $(date '+%Y-%m-%d %H:%M:%S')"

    ./dual_model_camera_inspect.sh ${DEVICE_ID}

    echo
    echo "等待 ${INTERVAL} 秒..."
    sleep ${INTERVAL}
done
