param(
    [switch]$SkipInstaller,
    [string]$PythonExecutable = "python"
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$specPath = Join-Path $PSScriptRoot "VibeGap.spec"
$distPath = Join-Path $repoRoot "dist"
$version = (& $PythonExecutable -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])").Trim()

function Write-Checksums([string[]]$Paths) {
    $lines = foreach ($path in $Paths) {
        $item = Get-Item -LiteralPath $path
        $hash = (Get-FileHash -LiteralPath $item.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        "$hash  $($item.Name)"
    }
    $checksumPath = Join-Path $distPath "SHA256SUMS.txt"
    $lines | Set-Content -LiteralPath $checksumPath -Encoding ascii
    Write-Output "Built checksums: $checksumPath"
}

Push-Location $repoRoot
try {
    & $PythonExecutable (Join-Path $repoRoot "scripts\fetch_dicts.py")
    if ($LASTEXITCODE -ne 0) { throw "Dictionary fetch failed with exit code $LASTEXITCODE" }

    & $PythonExecutable -m PyInstaller --noconfirm --clean $specPath
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }

    $portable = Join-Path $distPath "VibeGap-$version-portable.zip"
    if (Test-Path -LiteralPath $portable) { Remove-Item -LiteralPath $portable -Force }
    Compress-Archive -Path (Join-Path $distPath "VibeGap\*") -DestinationPath $portable

    if ($SkipInstaller) {
        Write-Checksums @($portable)
        Write-Output "Built portable bundle: $portable"
        return
    }

    $isccCommand = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    $isccPath = if ($isccCommand) { $isccCommand.Source } else { $null }
    if (-not $isccPath) {
        $knownPaths = @(
            (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
            "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
            "C:\Program Files\Inno Setup 6\ISCC.exe"
        )
        $isccPath = $knownPaths | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    }
    if (-not $isccPath) { throw "Inno Setup 6 was not found; rerun with -SkipInstaller for a portable build." }
    & $isccPath "/DAppVersion=$version" (Join-Path $PSScriptRoot "installer.iss")
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed with exit code $LASTEXITCODE" }
    $installer = Join-Path $distPath "installer\VibeGap-$version-Setup.exe"
    Write-Checksums @($portable, $installer)
    Write-Output "Built installer: $installer"
} finally {
    Pop-Location
}
