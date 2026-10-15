$ErrorActionPreference = 'Stop'
$desktopPath = [Environment]::GetFolderPath('Desktop')
$linkPath = Join-Path $desktopPath '京东推广工作台.lnk'
if (Test-Path -LiteralPath $linkPath) { throw '桌面已有同名快捷方式，未覆盖。' }
$shellObject = New-Object -ComObject WScript.Shell
$shortcut = $shellObject.CreateShortcut($linkPath)
$shortcut.TargetPath = (Get-Command powershell.exe).Source
$shortcut.Arguments = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + (Join-Path $PSScriptRoot '启动工作台.ps1') + '"'
$shortcut.WorkingDirectory = $PSScriptRoot
$shortcut.Description = '启动本机京东推广工作台'
$shortcut.Save()
