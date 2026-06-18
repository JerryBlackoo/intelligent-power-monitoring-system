# Atlas 边端与后端端口测试文档

本文档用于在本机验证电力智能监控系统相关服务是否正常运行，重点覆盖：

- 云端后端服务：`127.0.0.1:8000`
- Atlas 边端服务：`127.0.0.1:8001`
- MCP HTTP 入口：`127.0.0.1:8000/mcp`
- 可选独立 MCP HTTP 服务：`127.0.0.1:8010`

## 1. 测试前准备

在 PowerShell 中进入项目根目录：

```powershell
cd D:\ACADEMIC\By_Course\3.大三下学期\人工智能电力系统应用实训\intelligent-power-monitoring-system
```

创建并启用虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

如果已经创建过 `.venv`，只需要执行：

```powershell
.\.venv\Scripts\Activate.ps1
```

## 2. 启动云端后端服务 8000

打开第一个 PowerShell 窗口：

```powershell
cd D:\ACADEMIC\By_Course\3.大三下学期\人工智能电力系统应用实训\intelligent-power-monitoring-system
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

预期现象：

- 终端出现 `Uvicorn running on http://127.0.0.1:8000`
- 浏览器可打开 `http://127.0.0.1:8000/dashboard`
- API 文档可打开 `http://127.0.0.1:8000/docs`

## 3. 启动 Atlas 边端服务 8001

打开第二个 PowerShell 窗口：

```powershell
cd D:\ACADEMIC\By_Course\3.大三下学期\人工智能电力系统应用实训\intelligent-power-monitoring-system
.\.venv\Scripts\Activate.ps1

$env:CLOUD_BASE_URL="http://127.0.0.1:8000"
$env:EDGE_NODE_ID="atlas_01"
$env:EDGE_DEVICE_ID="cabinet_01"
$env:EDGE_MODEL_VERSION="yolov5s-power-v1"
$env:EDGE_INFERENCE_MODE="mock"
$env:EDGE_USE_CAMERA="0"

uvicorn edge_runtime.service:app --host 127.0.0.1 --port 8001
```

预期现象：

- 终端出现 `Uvicorn running on http://127.0.0.1:8001`
- `EDGE_INFERENCE_MODE=mock` 时，不依赖 Atlas ACL、OM 模型或摄像头
- 边端 `/inspect` 会使用内置兜底图片和 mock 检测结果打通上传链路

## 4. 端口连通性检查

打开第三个 PowerShell 窗口执行：

```powershell
Test-NetConnection 127.0.0.1 -Port 8000
Test-NetConnection 127.0.0.1 -Port 8001
```

预期结果：

```text
TcpTestSucceeded : True
```

如果 `TcpTestSucceeded` 为 `False`，说明对应端口服务没有启动成功，或端口被防火墙/其他程序影响。

## 5. 云端后端接口测试

健康检查：

```powershell
curl http://127.0.0.1:8000/api/health
```

预期返回：

```json
{"code":200,"message":"success","data":{"status":"ok"}}
```

仪表盘页面：

```powershell
curl http://127.0.0.1:8000/dashboard
```

预期结果：

- HTTP 状态码为 `200`
- 返回 HTML 中包含 `电力智能巡检工作台`

最新状态接口：

```powershell
curl http://127.0.0.1:8000/api/status/latest
```

预期结果：

- HTTP 状态码为 `200`
- 返回 JSON 中包含 `edge_node`、`latest_record`、`summary`

## 6. Atlas 边端接口测试

边端健康检查：

```powershell
curl http://127.0.0.1:8001/health
```

预期返回字段：

```json
{
  "status": "ok",
  "node_id": "atlas_01",
  "model_version": "yolov5s-power-v1",
  "cloud_base_url": "http://127.0.0.1:8000",
  "inference_mode": "mock",
  "use_camera": false,
  "camera_index": 0
}
```

边端主动上报心跳：

```powershell
curl -X POST http://127.0.0.1:8001/heartbeat
```

预期结果：

- HTTP 状态码为 `200`
- 返回 JSON 中包含 `"status":"ok"`
- 云端后端收到 `/api/edge/heartbeat`

触发一次巡检：

```powershell
curl -X POST http://127.0.0.1:8001/inspect `
  -H "Content-Type: application/json" `
  -d '{"device_id":"cabinet_01"}'
```

预期结果：

- HTTP 状态码为 `200`
- 返回 JSON 中包含：
  - `captured_at`
  - `local_image_path`
  - `image_uri`
  - `detections`
  - `cloud_result`
- `cloud_result.alert_count` 通常为 `1`
- `image_uri` 类似 `/images/atlas_01_20260618000000.png`

## 7. 巡检闭环验证

执行边端 `/inspect` 后，再检查云端最新状态：

```powershell
curl http://127.0.0.1:8000/api/status/latest
```

预期结果：

- `edge_node.node_id` 为 `atlas_01`
- `latest_record.device_id` 为 `cabinet_01`
- `latest_record.overall_status` 为 `warning`
- `latest_record.detections` 中包含 `red_indicator`
- `summary.warning_count` 大于或等于 `1`

查询活跃告警：

```powershell
curl http://127.0.0.1:8000/api/alerts/active
```

预期结果：

- HTTP 状态码为 `200`
- 返回数组中至少有一条告警
- 告警字段包含 `alert_id`、`level`、`description`、`status`

## 8. MCP HTTP 入口测试

当前 MCP HTTP endpoint 挂载在后端同一个 8000 端口：

```text
http://127.0.0.1:8000/mcp
```

先检查 8000 端口已开启：

```powershell
Test-NetConnection 127.0.0.1 -Port 8000
```

再发送 MCP initialize 请求：

```powershell
$body = @{
  jsonrpc = "2.0"
  id = 1
  method = "initialize"
  params = @{
    protocolVersion = "2025-06-18"
    capabilities = @{}
    clientInfo = @{
      name = "local-port-test"
      version = "1.0.0"
    }
  }
} | ConvertTo-Json -Depth 10

Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/mcp" `
  -Method Post `
  -ContentType "application/json" `
  -Headers @{ Accept = "application/json, text/event-stream" } `
  -Body $body
```

预期结果：

- HTTP 请求成功
- 返回内容包含 `protocolVersion`、`serverInfo` 或 `capabilities`

如果这里只想确认 `/mcp` 路由存在，也可以执行：

```powershell
curl -i http://127.0.0.1:8000/mcp
```

说明：

- `GET /mcp` 不一定返回业务 JSON
- MCP Streamable HTTP 通常需要用 `POST` JSON-RPC 请求测试

## 9. 可选：独立 MCP HTTP 服务 8010

一般不需要单独启动 8010，因为后端已经挂载 `/mcp`。如果需要验证独立 MCP HTTP 传输，打开新的 PowerShell：

```powershell
cd D:\ACADEMIC\By_Course\3.大三下学期\人工智能电力系统应用实训\intelligent-power-monitoring-system
.\.venv\Scripts\Activate.ps1

$env:POWER_MCP_TRANSPORT="http"
$env:POWER_MCP_HOST="127.0.0.1"
$env:POWER_MCP_PORT="8010"
$env:POWER_MCP_PATH="/mcp"

python -m mcp_server.power_monitoring_mcp
```

端口检查：

```powershell
Test-NetConnection 127.0.0.1 -Port 8010
```

预期结果：

```text
TcpTestSucceeded : True
```

独立 MCP endpoint：

```text
http://127.0.0.1:8010/mcp
```

## 10. 一键冒烟测试命令

在 8000 和 8001 都已启动后，可执行：

```powershell
$backend = Invoke-RestMethod http://127.0.0.1:8000/api/health
$edge = Invoke-RestMethod http://127.0.0.1:8001/health
$heartbeat = Invoke-RestMethod -Method Post http://127.0.0.1:8001/heartbeat
$inspect = Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8001/inspect `
  -ContentType "application/json" `
  -Body '{"device_id":"cabinet_01"}'
$latest = Invoke-RestMethod http://127.0.0.1:8000/api/status/latest
$alerts = Invoke-RestMethod http://127.0.0.1:8000/api/alerts/active

[PSCustomObject]@{
  BackendHealth = $backend.data.status
  EdgeHealth = $edge.status
  EdgeMode = $edge.inference_mode
  Heartbeat = $heartbeat.status
  Inspect = $inspect.status
  LatestStatus = $latest.data.latest_record.overall_status
  ActiveAlertCount = $alerts.data.Count
}
```

预期输出示例：

```text
BackendHealth   : ok
EdgeHealth      : ok
EdgeMode        : mock
Heartbeat       : ok
Inspect         : ok
LatestStatus    : warning
ActiveAlertCount: 1
```

## 11. 常见问题排查

### 8000 启动失败

检查是否已有程序占用 8000：

```powershell
netstat -ano | findstr :8000
```

处理方式：

- 关闭占用端口的程序
- 或改用其他端口启动后端，并同步修改 `CLOUD_BASE_URL`

### 8001 启动失败

检查是否已有程序占用 8001：

```powershell
netstat -ano | findstr :8001
```

如果边端服务启动时报依赖错误，重新安装依赖：

```powershell
pip install -r requirements.txt
```

### `/inspect` 返回 500

优先检查：

- `CLOUD_BASE_URL` 是否为 `http://127.0.0.1:8000`
- 云端后端 8000 是否正在运行
- 是否使用了 `EDGE_INFERENCE_MODE=mock`
- 如果使用摄像头，`EDGE_USE_CAMERA=1` 时 OpenCV 和摄像头设备是否可用

### ACL/OM 推理不可用

本机 Windows 测试建议使用：

```powershell
$env:EDGE_INFERENCE_MODE="mock"
```

Atlas 开发板实机再切换：

```bash
export EDGE_INFERENCE_MODE=acl
export EDGE_MODEL_PATH=/path/to/best.om
export EDGE_CLASS_NAMES_PATH=/path/to/label.names
```

### MCP 请求失败

检查：

- 后端是否已启动在 8000
- 请求地址是否为 `http://127.0.0.1:8000/mcp`
- `Accept` 请求头是否包含 `application/json, text/event-stream`
- 如果公网访问，是否设置了 `POWER_MCP_ALLOWED_HOSTS` 和 `POWER_MCP_ALLOWED_ORIGINS`

## 12. 测试通过标准

满足以下条件即可认为本机服务端口运行正常：

- `Test-NetConnection 127.0.0.1 -Port 8000` 返回 `True`
- `Test-NetConnection 127.0.0.1 -Port 8001` 返回 `True`
- `GET /api/health` 返回 `status=ok`
- `GET /health` 返回边端 `status=ok`
- `POST /heartbeat` 返回成功
- `POST /inspect` 返回成功，并生成 `image_uri` 与 `cloud_result`
- `GET /api/status/latest` 能看到最新巡检记录
- `GET /api/alerts/active` 能看到 mock 告警
- `POST /mcp` initialize 请求能得到 MCP 响应
