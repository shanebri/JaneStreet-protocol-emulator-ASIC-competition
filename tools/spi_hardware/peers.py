"""Supported Nano SPI peers share the same ARM/RX/DONE protocol."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NANO_PEERS = {
    'nano33ble': dict(cs_pin='D10', sketch=ROOT/'tools/spi_hardware/nano_spi_slave/nano_spi_slave.ino'),
    'nano33iot': dict(cs_pin='D8', sketch=ROOT/'tools/spi_hardware/nano33iot_spi_slave/nano33iot_spi_slave.ino'),
}


def nano_peer(fixture):
    board = fixture.get('nano_board', 'nano33ble')
    if board not in NANO_PEERS:
        raise ValueError('nano_board must be nano33ble or nano33iot')
    return NANO_PEERS[board]
