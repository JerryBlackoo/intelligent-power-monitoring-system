#!/usr/bin/env bash
pkill -9 -f uvicorn || true
pkill -9 -f edge_runtime.service || true
echo "service stopped"
