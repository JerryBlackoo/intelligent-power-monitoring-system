# intelligent-power-monitoring-system

基于 Atlas 200I DK 的电力智能监控系统。

## 后端启动

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

访问：

- API 文档：http://127.0.0.1:8000/docs
- 健康检查：http://127.0.0.1:8000/api/health

## P0 接口

- `POST /api/edge/heartbeat`
- `POST /api/edge/inference`
- `GET /api/status/latest`
- `GET /api/records`
- `GET /api/alerts/active`
- `POST /api/reports`

Atlas 未接入时，可以使用 `tests/mock_inference.json` 模拟推理上传。

## MCP 状态查询工具

本项目提供一个只读 MCP server，供其他模型或 MCP 客户端查询当前巡检系统状态。

安装依赖：

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

从项目根目录启动 stdio MCP server：

```powershell
python -m mcp_server.power_monitoring_mcp
```

现在 MCP HTTP endpoint 已经挂载到后端同一个 8000 端口。启动后端即可同时启动 API、仪表盘和 MCP：

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

HTTP MCP endpoint 为：

```text
http://127.0.0.1:8000/mcp
```

如果要用 ngrok 暴露公网 URL：

```powershell
ngrok http 8000
```

得到的公网 MCP URL 通常是：

```text
https://你的-ngrok-域名/mcp
```

暴露公网时，需要把公网域名加入 MCP Host 白名单后再启动后端。例如：

```powershell
$env:POWER_MCP_ALLOWED_HOSTS="你的-ngrok-域名"
$env:POWER_MCP_ALLOWED_ORIGINS="https://你的-ngrok-域名"
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

可用工具：

- `power_get_system_overview`：获取项目路径、数据库状态、最新边缘节点、最新巡检、活跃告警摘要、图片/报告/模型文件状态
- `power_list_records`：按时间、设备、状态分页查询巡检记录
- `power_get_record_detail`：按 `record_id` 查询单条巡检记录、检测结果和关联告警
- `power_list_alerts`：按告警等级、设备、状态分页查询告警
- `power_get_alert_detail`：按 `alert_id` 查询告警详情、维护建议和关联检测结果
- `power_get_runtime_diagnostics`：获取数据库、静态目录、模型文件和后端 API 入口诊断信息

可用资源：

- `power://overview`
- `power://api`

MCP 客户端配置示例：

```json
{
  "mcpServers": {
    "power_monitoring": {
      "command": "D:\\ACADEMIC\\By_Course\\3.大三下学期\\人工智能电力系统应用实训\\intelligent-power-monitoring-system\\.venv\\Scripts\\python.exe",
      "args": [
        "-m",
        "mcp_server.power_monitoring_mcp"
      ],
      "cwd": "D:\\ACADEMIC\\By_Course\\3.大三下学期\\人工智能电力系统应用实训\\intelligent-power-monitoring-system"
    }
  }
}
```

本 MCP server 既可以走 stdio，也可以挂载在后端 `/mcp` 路径；当前后端已挂载 `/mcp`，所以只有一个公网 URL 时直接暴露 8000 端口即可。所有工具都是只读工具，不会修改巡检数据。

可以用测试客户端验证 MCP 是否真正联通：

```powershell
python scripts/test_mcp_client.py http://127.0.0.1:8000/mcp
python scripts/test_mcp_client.py https://你的-ngrok-域名/mcp
```
