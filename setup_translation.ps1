param()

$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
$venvDirectory = Join-Path $projectRoot ".venv"
$venvPython = Join-Path $venvDirectory "Scripts\python.exe"
$models = @(
    @{
        Name = "Helsinki-NLP/opus-mt-en-cs"
        Directory = Join-Path $projectRoot "models\opus-mt-en-cs-int8"
    },
    @{
        Name = "Helsinki-NLP/opus-mt-cs-en"
        Directory = Join-Path $projectRoot "models\opus-mt-cs-en-int8"
    }
)

function New-ProbeVirtualEnvironment {
    if ($env:FOREVER_PROBE_PYTHON -and (Test-Path -LiteralPath $env:FOREVER_PROBE_PYTHON)) {
        & $env:FOREVER_PROBE_PYTHON -m venv $venvDirectory
        return
    }
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher) {
        & $launcher.Source -3 -m venv $venvDirectory
        if ($LASTEXITCODE -eq 0 -and (Test-Path -LiteralPath $venvPython)) {
            return
        }
    }
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python -and $python.Source -notlike "*\WindowsApps\*") {
        & $python.Source -m venv $venvDirectory
        if ($LASTEXITCODE -eq 0 -and (Test-Path -LiteralPath $venvPython)) {
            return
        }
    }
    $epicRoot = Join-Path $env:ProgramFiles "Epic Games"
    if (Test-Path -LiteralPath $epicRoot) {
        $embeddedPythons = Get-ChildItem -Path $epicRoot -Filter python.exe -Recurse -ErrorAction SilentlyContinue
        foreach ($candidate in $embeddedPythons) {
            & $candidate.FullName -c "import tkinter, venv" 2>$null
            if ($LASTEXITCODE -ne 0) { continue }
            & $candidate.FullName -m venv $venvDirectory
            if ($LASTEXITCODE -eq 0 -and (Test-Path -LiteralPath $venvPython)) {
                return
            }
        }
    }
    throw "Python 3.11+ was not found. Install Python or set FOREVER_PROBE_PYTHON."
}

if (Test-Path -LiteralPath $venvPython) {
    & $venvPython -m pip --version *> $null
    if ($LASTEXITCODE -ne 0) {
        Remove-Item -LiteralPath $venvDirectory -Recurse -Force
    }
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host "Creating local Python environment .venv..."
    New-ProbeVirtualEnvironment
}

Write-Host "Installing runtime libraries..."
& $venvPython -m pip install --disable-pip-version-check "ctranslate2==4.8.3" "sentencepiece==0.2.1"
if ($LASTEXITCODE -ne 0) { throw "Runtime library installation failed." }

$missingModels = @($models | Where-Object {
    -not (Test-Path -LiteralPath (Join-Path $_.Directory "model.bin"))
})

if ($missingModels.Count -gt 0) {
    Write-Host "Installing temporary tools for the official model conversion..."
    & $venvPython -m pip install --disable-pip-version-check "transformers[torch]>=4.44,<5"
    if ($LASTEXITCODE -ne 0) { throw "Model conversion tool installation failed." }

    $converter = Join-Path $venvDirectory "Scripts\ct2-transformers-converter.exe"
    foreach ($model in $missingModels) {
        New-Item -ItemType Directory -Force -Path $model.Directory | Out-Null
        Write-Host "Downloading $($model.Name) and converting it to CPU INT8..."
        & $converter `
            --model $model.Name `
            --output_dir $model.Directory `
            --quantization int8 `
            --copy_files source.spm target.spm `
            --force
        if ($LASTEXITCODE -ne 0) { throw "Model download or conversion failed: $($model.Name)" }
    }

    Write-Host "Removing large libraries that were only needed for conversion..."
    & $venvPython -m pip uninstall -y torch transformers tokenizers safetensors huggingface-hub
}

foreach ($model in $models) {
    foreach ($name in @("model.bin", "source.spm", "target.spm")) {
        $path = Join-Path $model.Directory $name
        if (-not (Test-Path -LiteralPath $path)) {
            throw "The model is incomplete. Missing file: $path"
        }
    }
}

Write-Host ""
Write-Host "DONE - offline EN-to-CZ and CZ-to-EN models are ready."
Write-Host "Run: .\run_probe.ps1 -Optical"
