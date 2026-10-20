$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$dependencyBin = Join-Path $projectRoot '.tools\mingw64\bin'
$localBin = Join-Path $projectRoot '.tools\icarus12\mingw64\bin'
if (!(Test-Path "$localBin/iverilog.exe")) { $localBin = $dependencyBin }
$iverilog = if (Test-Path "$localBin\iverilog.exe") { "$localBin\iverilog.exe" } else { 'iverilog' }
$vvp = if (Test-Path "$localBin\vvp.exe") { "$localBin\vvp.exe" } else { 'vvp' }
$savedPath = $env:PATH
if (Test-Path "$localBin\iverilog.exe") { $env:PATH = "$localBin;$dependencyBin;$env:PATH" }
Push-Location $projectRoot
try {
    New-Item -ItemType Directory -Force -Path fpga/build | Out-Null
    $sources = @(Get-Content info.yaml | Where-Object { $_ -match '^    - "(.+)"' } | ForEach-Object { 'src/' + $Matches[1] })
    $sources += @('fpga/byte_nibble_host.sv', 'fpga/arty_demo.sv', 'fpga/tb_arty_demo.sv')
    & $iverilog -g2012 -Wall -Wno-timescale -s tb_arty_demo -o fpga/build/arty_demo.vvp @sources
    if ($LASTEXITCODE -ne 0) { throw 'Arty demo compilation failed' }
    & $vvp fpga/build/arty_demo.vvp
    if ($LASTEXITCODE -ne 0) { throw 'Arty demo simulation failed' }
} finally {
    $env:PATH = $savedPath
    Pop-Location
}
