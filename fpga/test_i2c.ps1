$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$savedPath = $env:PATH
Push-Location $root
try {
    $env:PATH = "$root/.tools/icarus12/mingw64/bin;$root/.tools/mingw64/bin;$env:PATH"
    New-Item -ItemType Directory -Force fpga/build | Out-Null
    # Compile the actual submission manifest, then the FPGA-only boundary.
    $sources = @(Get-Content info.yaml | Where-Object { $_ -match '^    - "(.+)"' } | ForEach-Object { 'src/' + $Matches[1] })
    $sources += @('fpga/byte_nibble_host.sv','fpga/arty_i2c_bridge.sv','fpga/tb_arty_i2c_bridge.sv')
    & iverilog -g2012 -Wall -Wno-timescale -s tb_arty_i2c_bridge -o fpga/build/i2c.vvp @sources
    if ($LASTEXITCODE -ne 0) { throw 'I2C FPGA compile failed' }
    & vvp fpga/build/i2c.vvp
    if ($LASTEXITCODE -ne 0) { throw 'I2C FPGA simulation failed' }
} finally {
    $env:PATH = $savedPath
    Pop-Location
}
