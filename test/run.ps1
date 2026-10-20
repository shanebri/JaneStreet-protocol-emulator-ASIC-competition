# Use the optional project-local test tools, or installed Python/Icarus on PATH.
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$localPython = Join-Path $projectRoot '.tools\venv\Scripts\python.exe'
$dependencyBin = Join-Path $projectRoot '.tools\mingw64\bin'
$localSimulator = Join-Path $projectRoot '.tools\icarus12\mingw64\bin'
if (!(Test-Path "$localSimulator/iverilog.exe")) { $localSimulator = $dependencyBin }
$savedPath = $env:PATH
Push-Location $projectRoot
try {
    if (Test-Path -LiteralPath (Join-Path $localSimulator 'iverilog.exe')) {
        $env:PATH = $localSimulator + ';' + $dependencyBin + ';' + $env:PATH
    }
    $testPython = if (Test-Path -LiteralPath $localPython) { $localPython } else { 'python' }
    & $testPython (Join-Path $PSScriptRoot 'run.py')
    if ($LASTEXITCODE -ne 0) { throw "RTL regression failed (exit $LASTEXITCODE)" }
} finally {
    $env:PATH = $savedPath
    Pop-Location
}
