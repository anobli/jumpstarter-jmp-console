"""Client for JmpConsole driver."""

from dataclasses import dataclass

from jumpstarter.client import DriverClient
from jumpstarter.client.decorators import driver_click_group
from jumpstarter_driver_pyserial.client import PySerialClient

from .console import Console


@dataclass(kw_only=True)
class JmpConsoleClient(DriverClient):
    """Client for multi-UART console driver.

    Provides:
    - Aggregated console with mode switching
    - Access to individual UART clients via self.children
    """

    def cli(self):
        """Create Click CLI for this driver."""

        @driver_click_group(self)
        def base():
            """Multi-UART console driver."""
            pass

        @base.command()
        def console():
            """Start multi-UART console with mode switching.

            The console provides two modes:

            \b
            - AGGREGATED: View all UARTs with name prefixes (read-only, default)
            - INTERACTIVE: Select a specific UART for read/write

            \b
            Keyboard shortcuts:
              Alt+0       : Return to aggregated view (all UARTs)
              Alt+1-9     : Switch to UART by index
              Ctrl+B x3   : Exit console

            Example use case: SoC with two UARTs (one per core), view logs from
            both cores simultaneously and trigger reboot commands.
            """
            serial_clients = get_serial_clients(self)
            key_bindings_commands = get_key_bindings_commands()
            console = Console(self, serial_clients, key_bindings_commands)
            console.run()

        def get_key_bindings_commands():
            """Retrieve key-binding to command mappings from the driver.

            Returns:
                dict mapping key bytes to command argument lists
            """
            key_bindings_commands = {}
            commands = self.call("get_commands")
            for name in commands:
                key = commands[name].get("key")
                command = commands[name].get("command")
                key_bindings_commands[key.encode()] = command.split()
            return key_bindings_commands

        def get_serial_clients(client):
            """Extract PySerialClient children from the driver client.

            Args:
                client: The driver client to inspect

            Returns:
                dict mapping UART names to PySerialClient instances
            """
            serial_clients = {}
            for child in client.children:
                if isinstance(client.children[child], PySerialClient):
                    serial_clients[child] = client.children[child]

            return serial_clients

        return base
