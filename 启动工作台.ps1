$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw '请先按 README 安装 Python 虚拟环境和依赖。' }
$isRunning = $false
try { $response = Invoke-WebRequest 'http://127.0.0.1:5192/' -UseBasicParsing -TimeoutSec 2; $isRunning = $response.Content.Contains('<title>京东推广工作台</title>'); if (-not $isRunning) { throw '端口5192被其他服务占用' } } catch { if ($response -and -not $isRunning) { throw '端口5192被其他服务占用，请人工检查' } }
if (-not $isRunning) {
    Start-Process -FilePath $pythonPath -ArgumentList @('scripts/workbench_server.py') -WorkingDirectory $projectRoot -WindowStyle Hidden
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Milliseconds 300
        try { $response = Invoke-WebRequest 'http://127.0.0.1:5192/' -UseBasicParsing -TimeoutSec 1; $isRunning = $response.Content.Contains('<title>京东推广工作台</title>') } catch { }
        if ($isRunning) { break }
    }
    if (-not $isRunning) { throw '工作台服务启动失败，请在终端运行 scripts/workbench_server.py 查看错误' }
}
Start-Process 'http://127.0.0.1:5192/'
