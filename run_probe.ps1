param(
    [string]$LogPath,
    [switch]$Simulate,
    [switch]$FromBeginning,
    [switch]$Ocr,
    [switch]$Optical
)

$arguments = @("-m", "forever_probe")
if ($LogPath) {
    $arguments += @("--log", $LogPath)
}
if ($Simulate) {
    $arguments += "--simulate"
}
if ($FromBeginning) {
    $arguments += "--from-beginning"
}
if ($Ocr) {
    $arguments += "--ocr"
}
if ($Optical) {
    $arguments += "--optical"
}

$env:PYTHONPATH = Join-Path $PSScriptRoot "app"

if ($env:FOREVER_PROBE_PYTHON -and (Test-Path -LiteralPath $env:FOREVER_PROBE_PYTHON)) {
    & $env:FOREVER_PROBE_PYTHON @arguments
    exit $LASTEXITCODE
}

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (Test-Path -LiteralPath $venvPython) {
    & $venvPython @arguments
    exit $LASTEXITCODE
}

$launcher = Get-Command py -ErrorAction SilentlyContinue
if ($launcher) {
    & $launcher.Source -3 @arguments
    exit $LASTEXITCODE
}

$python = Get-Command python -ErrorAction SilentlyContinue
if ($python) {
    & $python.Source @arguments
    exit $LASTEXITCODE
}

throw "Python 3.11+ nebyl nalezen. Nainstalujte Python s podporou Tkinter nebo nastavte FOREVER_PROBE_PYTHON."

