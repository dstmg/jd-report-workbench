$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (Get-Command uv -ErrorAction SilentlyContinue) { & uv venv --python 3.12 .venv }
elseif (Get-Command py -ErrorAction SilentlyContinue) { & py -3 -m venv .venv }
elseif (Get-Command python -ErrorAction SilentlyContinue) { & python -m venv .venv }
else { throw '请先安装 Python 3.12 或更新版本，再重新运行。' }
if ($LASTEXITCODE -ne 0) { throw '创建虚拟环境失败' }
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (Get-Command uv -ErrorAction SilentlyContinue) { & uv pip install --python $pythonPath -r (Join-Path $PSScriptRoot 'requirements.txt') }
else { & $pythonPath -m pip install -r (Join-Path $PSScriptRoot 'requirements.txt') }
if ($LASTEXITCODE -ne 0) { throw '依赖安装失败，请检查网络后重试。' }
Write-Host '安装完成。运行 启动工作台.ps1；在数据管理中填写账户并人工登录。'
