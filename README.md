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
