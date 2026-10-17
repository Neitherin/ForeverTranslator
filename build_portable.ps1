param()

$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "Chybí .venv. Nejdřív spusťte .\setup_translation.ps1."
}

$requiredModels = @(
    "models\opus-mt-en-cs-int8\model.bin",
    "models\opus-mt-cs-en-int8\model.bin"
)
foreach ($relativePath in $requiredModels) {
    if (-not (Test-Path -LiteralPath (Join-Path $projectRoot $relativePath))) {
        throw "Chybí překladový model: $relativePath. Spusťte .\setup_translation.ps1."
    }
}

& $venvPython -m pip install --disable-pip-version-check -r (Join-Path $projectRoot "requirements-build.txt")
if ($LASTEXITCODE -ne 0) { throw "Instalace build nástrojů selhala." }

& $venvPython -m PyInstaller --noconfirm --clean (Join-Path $projectRoot "ForeverTranslator.spec")
if ($LASTEXITCODE -ne 0) { throw "Sestavení aplikace selhalo." }

$outputDirectory = Join-Path $projectRoot "dist\ForeverTranslator"
Copy-Item -LiteralPath (Join-Path $projectRoot "README.md") -Destination $outputDirectory -Force
Copy-Item -LiteralPath (Join-Path $projectRoot "THIRD_PARTY_NOTICES.md") -Destination $outputDirectory -Force

$archive = Join-Path $projectRoot "dist\ForeverTranslator-Windows-x64.zip"
if (Test-Path -LiteralPath $archive) {
    Remove-Item -LiteralPath $archive -Force
}
Compress-Archive -Path (Join-Path $outputDirectory "*") -DestinationPath $archive -CompressionLevel Optimal
Write-Host "DONE: $archive"
