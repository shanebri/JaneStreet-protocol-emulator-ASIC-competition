# Simulation only. Does not invoke Vivado or program hardware.
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$savedPath = $env:PATH
Push-Location $projectRoot
try {
    $localBin = Join-Path $projectRoot '.tools\icarus12\mingw64\bin'
    $dependencyBin = Join-Path $projectRoot '.tools\mingw64\bin'
    if (Test-Path -LiteralPath (Join-Path $localBin 'iverilog.exe')) {
        $env:PATH = "$localBin;$dependencyBin;$env:PATH"
    } elseif (Test-Path -LiteralPath (Join-Path $dependencyBin 'iverilog.exe')) {
        $env:PATH = "$dependencyBin;$env:PATH"
    }
    New-Item -ItemType Directory -Force -Path fpga/build | Out-Null
    $sources = @(Get-Content info.yaml | Where-Object { $_ -match '^    - "(.+)"' } | ForEach-Object { 'src/' + $Matches[1] })
    $sources += @('fpga/byte_nibble_host.sv', 'fpga/arty_spi_test_host.sv', 'fpga/spi_test_uart_tx.sv', 'fpga/tb_arty_spi_test.sv')
    & iverilog -g2012 -Wall -Wno-timescale -s tb_arty_spi_test -o fpga/build/arty_spi_test.vvp @sources
    if ($LASTEXITCODE -ne 0) { throw 'SPI test compilation failed' }
    & vvp fpga/build/arty_spi_test.vvp
    if ($LASTEXITCODE -ne 0) { throw 'SPI test simulation failed' }
} finally {
    $env:PATH = $savedPath
    Pop-Location
}
