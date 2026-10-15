$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$localBin = Join-Path $projectRoot '.tools\mingw64\bin'
$iverilog = if (Test-Path "$localBin\iverilog.exe") { "$localBin\iverilog.exe" } else { 'iverilog' }
$vvp = if (Test-Path "$localBin\vvp.exe") { "$localBin\vvp.exe" } else { 'vvp' }
$savedPath = $env:PATH
if (Test-Path "$localBin\iverilog.exe") { $env:PATH = "$localBin;$env:PATH" }
Push-Location $projectRoot
try {
    New-Item -ItemType Directory -Force -Path fpga/build | Out-Null
    $sources = @('src/project.sv', 'src/host_interface.sv', 'src/protocol_core.sv',
        'src/pio_fifo.sv', 'src/execution_unit.sv', 'src/frontend/pc.sv',
        'src/frontend/instruction_fetch.sv', 'src/frontend/decoder.sv',
        'fpga/arty_demo.sv', 'fpga/tb_arty_demo.sv')
    & $iverilog -g2012 -Wall -Wno-timescale -s tb_arty_demo -o fpga/build/arty_demo.vvp @sources
    if ($LASTEXITCODE -ne 0) { throw 'Arty demo compilation failed' }
    & $vvp fpga/build/arty_demo.vvp
    if ($LASTEXITCODE -ne 0) { throw 'Arty demo simulation failed' }
} finally {
    $env:PATH = $savedPath
    Pop-Location
}
