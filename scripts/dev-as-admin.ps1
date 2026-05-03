# 以管理员身份在新 PowerShell 窗口中启动 `npm run dev`（解决 PostMessage 等对游戏窗口拒绝访问）。
# 用法: npm run dev:admin
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$rootEscaped = $root -replace "'", "''"
$inner = "Set-Location -LiteralPath '$rootEscaped'; npm run dev:inner"
Start-Process powershell.exe -Verb RunAs -ArgumentList @(
    "-NoExit",
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-Command", $inner
)
