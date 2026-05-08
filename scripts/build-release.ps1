# Frontend build, PyInstaller (windowed + icon); Inno installer if ISCC exists, else portable zip.
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $root

$pkgPath = Join-Path $root "package.json"
$pkgRaw = Get-Content $pkgPath -Encoding UTF8 -Raw
$pkg = $pkgRaw | ConvertFrom-Json
$ver = [string]$pkg.version
if ([string]::IsNullOrWhiteSpace($ver)) {
    Write-Error "package.json: missing version"
}
$appName = [string]$pkg.appDisplayName
if ([string]::IsNullOrWhiteSpace($appName)) {
    Write-Error "package.json: missing appDisplayName (e.g. 异环钓鱼工具)"
}

New-Item -ItemType Directory -Force -Path (Join-Path $root "release") | Out-Null
$staleDefines = Join-Path $root "release\build-inno-defines.iss"
if (Test-Path $staleDefines) {
    Remove-Item -Force $staleDefines
}

Write-Host "== 1/6 frontend: pnpm install + build ==" -ForegroundColor Cyan
pnpm --dir frontend install
pnpm --dir frontend build

$venvPy = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    Write-Error "Missing venv at $venvPy. Run: python -m venv .venv ; .\.venv\Scripts\pip install -r python\requirements-build.txt"
}

Write-Host "== 2/6 pip install (build deps) ==" -ForegroundColor Cyan
& $venvPy -m pip install -r (Join-Path $root "python\requirements-build.txt")

$iconPng = Join-Path $root "icon.png"
if (-not (Test-Path $iconPng)) {
    Write-Error "Missing icon.png at repo root"
}
Write-Host "== 3/6 PNG -> ICO ==" -ForegroundColor Cyan
& $venvPy (Join-Path $root "scripts\png-to-ico.py") $iconPng (Join-Path $root "release\app-icon.ico")

$env:YH_FISH_EXE_BASENAME = $appName
$distpath = Join-Path $root "release\app"
$workpath = Join-Path $root "release\pyinstaller-work"
$spec = Join-Path $root "yh-fish.spec"

if (Test-Path $distpath) {
    Remove-Item -Recurse -Force $distpath
}

Write-Host "== 4/6 PyInstaller ==" -ForegroundColor Cyan
& $venvPy -m PyInstaller --clean -y --noconfirm --distpath $distpath --workpath $workpath $spec

$outDir = Join-Path $distpath $appName
$feDist = Join-Path $root "frontend\dist"
$targetFe = Join-Path $outDir "frontend\dist"
if (-not (Test-Path $feDist)) {
    Write-Error "Missing frontend dist: $feDist (frontend build failed)."
}
Write-Host "== 5/6 copy frontend/dist -> $targetFe ==" -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path (Split-Path $targetFe -Parent) | Out-Null
if (Test-Path $targetFe) { Remove-Item -Recurse -Force $targetFe }
Copy-Item -Path $feDist -Destination $targetFe -Recurse -Force

function Resolve-IsccPath {
    if ($env:ISCC -and (Test-Path $env:ISCC)) { return $env:ISCC }
    $cmd = Get-Command "iscc.exe" -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -and (Test-Path $cmd.Source)) { return $cmd.Source }
    foreach ($base in @(${env:ProgramFiles(x86)}, $env:ProgramFiles, ${env:LocalAppData})) {
        if (-not $base) { continue }
        $p = Join-Path $base "Inno Setup 6\ISCC.exe"
        if (Test-Path $p) { return $p }
    }
    return $null
}

function Invoke-CompressArchiveWithRetry {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$DestinationPath,
        [int]$MaxAttempts = 5,
        [int]$DelaySeconds = 2
    )

    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        try {
            Compress-Archive -Path $Path -DestinationPath $DestinationPath
            return
        } catch {
            if ($attempt -eq $MaxAttempts) {
                Write-Error "Portable zip failed after $MaxAttempts attempts. Close any running $appName.exe window and retry. Last error: $($_.Exception.Message)"
            }

            Write-Warning "Portable zip attempt $attempt/$MaxAttempts failed: $($_.Exception.Message)"
            Start-Sleep -Seconds $DelaySeconds
        }
    }
}

$iscc = Resolve-IsccPath

if ($iscc) {
    Write-Host "== 6/6 Inno Setup ($iscc) ==" -ForegroundColor Cyan
    $iss = Join-Path $root "yi-huan-fish-installer.iss"
    $buildDirMacro = "release/app/$appName"
    & $iscc "/DMyAppVersion=$ver" "/DMyAppName=$appName" "/DMyAppBuildDir=$buildDirMacro" $iss
    $setupOut = Join-Path $root "release\$appName-$ver-setup.exe"
    Write-Host "Done: $setupOut" -ForegroundColor Green
} else {
    Write-Host "== 6/6 Inno Setup skipped (no ISCC.exe). Portable zip instead. ==" -ForegroundColor Yellow
    Write-Host "Optional: install Inno Setup 6 and add to PATH, or set env ISCC to ISCC.exe full path." -ForegroundColor DarkYellow
    $zipOut = Join-Path $root "release\$appName-$ver-portable.zip"
    if (Test-Path $zipOut) { Remove-Item -Force $zipOut }
    Invoke-CompressArchiveWithRetry -Path $outDir -DestinationPath $zipOut
    Write-Host "Done: $zipOut (extract and run $appName.exe)" -ForegroundColor Green
}
