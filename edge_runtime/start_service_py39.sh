#!/usr/bin/env bash
set -e

export CLOUD_BASE_URL="${CLOUD_BASE_URL:-https://manila-landing-try.ngrok-free.dev}"
export EDGE_NODE_ID="${EDGE_NODE_ID:-atlas_01}"
export EDGE_DEVICE_ID="${EDGE_DEVICE_ID:-cabinet_01}"
export EDGE_MODEL_VERSION="${EDGE_MODEL_VERSION:-yolov5s-power-v1}"

# First run should use mock inference to verify cloud upload.
export EDGE_INFERENCE_MODE="${EDGE_INFERENCE_MODE:-mock}"

# Enable these after /dev/video0 is verified.
export EDGE_USE_CAMERA="${EDGE_USE_CAMERA:-0}"
export EDGE_CAMERA_INDEX="${EDGE_CAMERA_INDEX:-0}"
export EDGE_FRAME_WIDTH="${EDGE_FRAME_WIDTH:-640}"
export EDGE_FRAME_HEIGHT="${EDGE_FRAME_HEIGHT:-480}"

export EDGE_SERVICE_HOST="${EDGE_SERVICE_HOST:-0.0.0.0}"
export EDGE_SERVICE_PORT="${EDGE_SERVICE_PORT:-9000}"

python3.9 -m edge_runtime.service
