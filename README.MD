$env:POWER_MCP_ALLOWED_HOSTS = "manila-landing-try.ngrok-free.dev,manila-landing-try.ngrok-free.dev:*"
$env:POWER_MCP_ALLOWED_ORIGINS = "https://manila-landing-try.ngrok-free.dev"
.\.venv\Scripts\python.exe -m uvicorn app.controller:app --host 127.0.0.1 --port 8000