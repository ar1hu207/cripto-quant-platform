# Sprint 7 - Supervisor: roda a plataforma 24/7 e REINICIA sozinho se cair.
# Uso:  powershell -ExecutionPolicy Bypass -File run_plataforma.ps1
Set-Location -Path $PSScriptRoot
Write-Host "=== Plataforma Cripto Bot - supervisor 24/7 ==="
Write-Host "UI/API em http://localhost:8000  (Ctrl+C para parar)"
while ($true) {
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] iniciando servidor..."
    python -m uvicorn api:app --host 127.0.0.1 --port 8000
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] servidor parou/caiu - reiniciando em 5s..." -ForegroundColor Yellow
    Start-Sleep -Seconds 5
}
