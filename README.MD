```
$env:POWER_MCP_ALLOWED_HOSTS = ""
$env:POWER_MCP_ALLOWED_ORIGINS = ""
$env:POWER_AGENT_API_KEY="" 
>> $env:POWER_AGENT_BASE_URL=""
>> $env:POWER_AGENT_MODEL=""
.\.venv\Scripts\python.exe -m uvicorn app.controller:app --host 127.0.0.1 --port 8000
```
