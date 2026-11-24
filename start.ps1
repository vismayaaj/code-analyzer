$root = $PSScriptRoot

# Backend (API) in its own window
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root\backend'; .\venv\Scripts\Activate.ps1; uvicorn app.main:app --reload --port 8001"

# Frontend (page) in its own window
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root\frontend'; npm run dev"

# Give them a few seconds to start, then open the dashboard
Start-Sleep -Seconds 6
Start-Process "http://localhost:5173"