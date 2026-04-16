"""Tests for JmpConsole driver."""

from typing import cast

from jumpstarter.common.utils import serve
from jumpstarter_driver_pyserial.driver import PySerial

from .client import JmpConsoleClient
from .driver import JmpConsole


def test_jmpconsole_creation():
    """Test that JmpConsole can be created."""
    driver = JmpConsole()

    # Verify driver is created successfully
    assert driver is not None
    assert isinstance(driver, JmpConsole)


def test_jmpconsole_with_commands():
    """Test JmpConsole with command configuration."""
    driver = JmpConsole(
        commands={
            "reboot": {"key": "r", "command": "reboot now"},
            "status": {"key": "s", "command": "status check"},
        }
    )

    # Verify commands are stored
    assert len(driver.commands) == 2
    assert "reboot" in driver.commands
    assert driver.commands["reboot"]["key"] == "r"


def test_jmpconsole_get_commands():
    """Test get_commands export method."""
    driver = JmpConsole(
        commands={
            "test": {"key": "t", "command": "test command"},
        }
    )

    commands = driver.get_commands()
    assert commands == driver.commands
    assert "test" in commands


def test_jmpconsole_with_manual_children():
    """Test JmpConsole with manually added child PySerial drivers."""
    driver = JmpConsole()

    # Manually add child drivers
    driver.children["uart0"] = PySerial(url="loop://", baudrate=115200)
    driver.children["uart1"] = PySerial(url="loop://", baudrate=115200)

    # Verify children were added
    assert "uart0" in driver.children
    assert "uart1" in driver.children
    assert len(driver.children) == 2


def test_jmpconsole_stream():
    """Test basic stream functionality with multiple UARTs."""
    driver = JmpConsole()
    driver.children["uart0"] = PySerial(url="loop://", baudrate=115200)
    driver.children["uart1"] = PySerial(url="loop://", baudrate=115200)

    with serve(driver) as client:
        client = cast(JmpConsoleClient, client)

        # Verify client has children
        assert "uart0" in client.children
        assert "uart1" in client.children

        # Test accessing individual UART
        uart0 = client.children["uart0"]
        with uart0.stream() as stream:
            stream.send(b"hello uart0\n")
            data = stream.receive()
            assert b"hello uart0" in data


def test_jmpconsole_multiple_uarts():
    """Test accessing multiple UARTs independently."""
    driver = JmpConsole()
    driver.children["core0"] = PySerial(url="loop://", baudrate=115200)
    driver.children["core1"] = PySerial(url="loop://", baudrate=115200)

    with serve(driver) as client:
        client = cast(JmpConsoleClient, client)

        # Test core0
        core0 = client.children["core0"]
        with core0.stream() as stream:
            stream.send(b"message from core0\n")
            data = stream.receive()
            assert b"message from core0" in data

        # Test core1
        core1 = client.children["core1"]
        with core1.stream() as stream:
            stream.send(b"message from core1\n")
            data = stream.receive()
            assert b"message from core1" in data


def test_jmpconsole_individual_uart_access():
    """Test accessing individual UARTs directly."""
    driver = JmpConsole()
    driver.children["uart0"] = PySerial(url="loop://", baudrate=115200)
    driver.children["uart1"] = PySerial(url="loop://", baudrate=115200)

    with serve(driver) as client:
        client = cast(JmpConsoleClient, client)

        # Access uart0 directly
        uart0 = client.children["uart0"]
        with uart0.stream() as stream:
            stream.send(b"direct message")
            data = stream.receive()
            assert b"direct" in data


def test_jmpconsole_empty():
    """Test JmpConsole with no UARTs configured."""
    driver = JmpConsole()
    assert len(driver.children) == 0


def test_jmpconsole_with_custom_baudrate():
    """Test JmpConsole with custom baudrate."""
    driver = JmpConsole()
    driver.children["uart0"] = PySerial(url="loop://", baudrate=9600)

    with serve(driver) as client:
        client = cast(JmpConsoleClient, client)

        uart0 = client.children["uart0"]
        with uart0.stream() as stream:
            stream.send(b"test")
            data = stream.receive()
            assert b"test" in data


def test_jmpconsole_with_cps_throttling():
    """Test JmpConsole with CPS throttling."""
    driver = JmpConsole()
    uart = PySerial(url="loop://", baudrate=115200)
    uart.cps = 10
    driver.children["uart0"] = uart

    with serve(driver) as client:
        client = cast(JmpConsoleClient, client)

        uart0 = client.children["uart0"]
        with uart0.stream() as stream:
            stream.send(b"test")
            data = stream.receive()
            # With throttling, we should receive at least some data
            assert len(data) > 0
            assert data[0:1] == b"t"
