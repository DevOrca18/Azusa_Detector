param(
    [string]$OutputDirectory = (Join-Path $PSScriptRoot 'release'),
    [string]$WorkDirectory = (Join-Path $PSScriptRoot 'build')
)
$ErrorActionPreference = 'Stop'
$buildPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$buildSound = Join-Path $PSScriptRoot 'alert.wav'
$buildDigits = Join-Path $PSScriptRoot 'assets\digits'
$buildArtwork = Join-Path $PSScriptRoot 'assets\ui'
$buildSamples = Join-Path $PSScriptRoot 'assets\samples'
$previousBuildCache = $env:PYINSTALLER_CONFIG_DIR
$env:PYINSTALLER_CONFIG_DIR = Join-Path ([System.IO.Path]::GetFullPath($WorkDirectory)) 'cache'
if (-not (Test-Path -LiteralPath $buildPython)) {
    throw 'Create .venv and install requirements-build.txt first (see README.md).'
}
Push-Location $PSScriptRoot
try {
    & $buildPython -m PyInstaller --noconfirm --clean --onefile --windowed --noupx `
        --name AzusaDetector --distpath $OutputDirectory --workpath $WorkDirectory `
        --specpath $WorkDirectory --add-data "${buildSound}:." --add-data "${buildDigits}:assets/digits" --add-data "${buildArtwork}:assets/ui" --add-data "${buildSamples}:assets/samples" `
        --collect-all ttkthemes --exclude-module pytest --exclude-module pytesseract main.py
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed: $LASTEXITCODE" }
}
finally {
    Pop-Location
    $env:PYINSTALLER_CONFIG_DIR = $previousBuildCache
}
