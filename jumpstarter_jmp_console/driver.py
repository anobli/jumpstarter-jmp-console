"""Multi-UART console driver for Jumpstarter."""

from dataclasses import dataclass, field

from jumpstarter.common.exceptions import ConfigurationError
from jumpstarter.driver import Driver, export
from jumpstarter_driver_pyserial.driver import PySerial


@dataclass(kw_only=True)
class JmpConsole(Driver):
    """Multi-UART console driver with aggregated view.

    Manages multiple PySerial child drivers and provides an aggregated
    console view with UART prefixes, interactive mode for individual
    UART access, and key-binding based command execution.

    Attributes:
        commands: Keybinding command mappings. Each entry maps a name to
                  a dict with "key" (single char) and "command" (space-separated
                  shell arguments) fields.
    """

    commands: dict[str, dict[str, str]] = field(default_factory=dict)

    def __post_init__(self):
        """Initialize child PySerial drivers for each UART."""
        if hasattr(super(), "__post_init__"):
            super().__post_init__()

    @classmethod
    def client(cls) -> str:
        """Return the client class path."""
        return "jumpstarter_jmp_console.client.JmpConsoleClient"

    @export
    def get_commands(self) -> dict[str, dict[str, str]]:
        """Return the available commands and their configurations."""
        return self.commands
