"""Terminal console UI for multi-UART management with mode switching."""

import sys
import termios
import tty
import shutil
from collections import deque
from contextlib import contextmanager

from anyio import create_task_group, to_thread
from anyio.streams.file import FileReadStream, FileWriteStream

from jumpstarter.client import DriverClient


class ConsoleExit(Exception):
    """Signal to exit the console loop cleanly."""


class Console:
    """Multi-UART terminal console with aggregated and interactive modes.

    Manages multiple serial connections in a single terminal window using
    ANSI escape sequences and raw terminal mode. Supports switching between
    an aggregated view (all UARTs displayed with prefixes, read-only) and
    a single-UART interactive view.

    Keyboard shortcuts:
        Alt+0       : Switch to aggregated view
        Alt+1-9     : Switch to UART by index (1-based)
        Ctrl+B x3   : Exit console
    """

    def __init__(self, cli: DriverClient, serial_clients: dict[str, DriverClient], key_bindings_commands: dict | None = None):
        """Initialize the console.

        Args:
            cli: The top-level driver client, used to access child drivers
                 when executing key-bound commands.
            serial_clients: dict mapping UART names to PySerialClient instances.
            key_bindings_commands: dict mapping key bytes to command argument lists.
        """
        self.cli = cli
        self.serial_clients = serial_clients
        self.streams: dict = {}
        self.current_serial = None
        # Raw byte chunks per UART — replayed as-is when switching to a single UART.
        self.char_history: dict[str, deque[bytes]] = {name: deque(maxlen=10000) for name in serial_clients}
        # Formatted lines shared across all UARTs — replayed in aggregated view.
        self.line_history: deque[bytes] = deque(maxlen=1000)
        self.key_bindings_commands = key_bindings_commands if key_bindings_commands is not None else {}

    def run(self):
        """Start the console in raw terminal mode.

        Blocks until the user exits with Ctrl+B x3 or an error occurs.
        Spawns one reader task per UART plus a stdin routing task, all
        running concurrently inside a task group.

        Raises:
            ValueError: If no serial clients are configured.
        """
        if not self.serial_clients:
            raise ValueError("At least one serial client is required to run the console.")
        with self.setraw():
            async def _run_all():
                try:
                    async with create_task_group() as tg:
                        for name in self.serial_clients:
                            tg.start_soon(self.__run, name)
                        tg.start_soon(self.__stdin_to_serial)
                        await self.__setup_terminal()
                except* ConsoleExit:
                    pass

            list(self.serial_clients.values())[0].portal.call(_run_all)

    @contextmanager
    def setraw(self):
        """Context manager: switch the terminal to raw mode.

        Saves the current terminal settings, switches to raw mode for
        character-by-character input, and restores the original settings
        on exit. Also resets the scroll region and clears the screen when
        exiting so the terminal is left in a usable state.
        """
        original = termios.tcgetattr(sys.stdin.fileno())
        try:
            tty.setraw(sys.stdin.fileno())
            yield
        finally:
            # Reset scroll region and cursor before restoring terminal
            sys.stdout.buffer.write(b"\x1b[r\x1b[2J\x1b[H")
            sys.stdout.buffer.flush()
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, original)

    async def __run(self, name):
        """Open a streaming connection to a single UART and start its reader.

        Args:
            name: UART identifier used as a key in serial_clients.
        """
        async with self.serial_clients[name].stream_async(method="connect") as stream:
            self.streams[name] = stream
            try:
                async with create_task_group() as tg:
                    tg.start_soon(self.__serial_to_stdout, stream, name)
            finally:
                self.streams.pop(name, None)

    async def __serial_to_stdout(self, stream, name):
        """Stream data from a UART to stdout.

        In aggregated mode, buffers incoming bytes until a newline is found,
        then formats the completed line with the UART name as a prefix and
        writes it to stdout and the shared line history. In single-UART mode,
        forwards raw bytes immediately for interactive echo.

        Args:
            stream: The async stream for the UART connection.
            name: UART identifier used for formatting and history lookup.
        """
        stdout = FileWriteStream(sys.stdout.buffer)
        line_buffer = b""
        while True:
            data = await stream.receive()

            # Always record raw bytes for single-UART replay.
            self.char_history[name].append(data)

            # Build complete lines for the shared aggregated history.
            line_buffer += data
            while b"\n" in line_buffer:
                line, line_buffer = line_buffer.split(b"\n", 1)
                formatted = f"{name}: ".encode() + line.rstrip(b"\r") + b"\r\n"
                self.line_history.append(formatted)
                if self.current_serial is None:
                    await stdout.send(formatted)
                    sys.stdout.flush()

            # In single-UART mode forward raw bytes immediately for echo.
            if self.current_serial == name:
                await stdout.send(data)
                sys.stdout.flush()

    async def __clear_screen(self):
        """Clear the terminal screen and move the cursor to the top-left."""
        sys.stdout.buffer.write(b"\x1b[2J\x1b[H")  # clear screen, cursor to top
        sys.stdout.buffer.flush()

    async def __setup_terminal(self):
        """Configure the terminal scroll region and show the initial status bar.

        Reserves the bottom row of the terminal for the status bar by setting
        the VT100 scroll region to all rows except the last, then clears the
        screen and renders the status bar.
        """
        _, rows = shutil.get_terminal_size()
        # Set scroll region to all lines except the last
        sys.stdout.buffer.write(f"\x1b[1;{rows - 1}r".encode())
        # Clear screen
        sys.stdout.buffer.write(b"\x1b[2J\x1b[H")
        sys.stdout.buffer.flush()
        await self.__show_status_bar()

    async def __show_status_bar(self):
        """Render the status bar on the last row of the terminal.

        Saves the cursor position, moves to the last row, clears the line,
        prints the current mode and available shortcuts, then restores the
        cursor so normal output is not displaced.
        """
        _, rows = shutil.get_terminal_size()
        if self.current_serial is None:
            label = "All UARTs"
        else:
            label = self.current_serial

        status = f"[ {label} | Alt+0: All | Alt+1-9: Select | Ctrl+B x3: Exit ]"
        # Save cursor, move to last line, clear it, print, restore cursor
        sys.stdout.buffer.write(
            f"\x1b[s\x1b[{rows};1H\x1b[2K{status}\x1b[u".encode()
        )
        sys.stdout.buffer.flush()

    async def __handle_alt_key(self, key: bytes):
        """Handle an Alt+key press to switch UART views.

        Alt+0 returns to the aggregated view and replays the formatted line
        history. Alt+1-9 switches to the UART at that 1-based index and
        replays its raw byte history.

        Args:
            key: The character following the ESC prefix (single byte).
        """
        stdout = FileWriteStream(sys.stdout.buffer)

        if key == b"0":
            self.current_serial = None
            await self.__clear_screen()
            for line in self.line_history:
                await stdout.send(line)
            await self.__show_status_bar()
            sys.stdout.flush()

        elif key in b"123456789":
            index = int(key.decode()) - 1
            if index < len(self.serial_clients):
                self.current_serial = list(self.serial_clients.keys())[index]
                await self.__clear_screen()
                for chunk in self.char_history[self.current_serial]:
                    await stdout.send(chunk)
                await self.__show_status_bar()
                sys.stdout.flush()
            else:
                await stdout.send(f"\r\n*** No UART at index {index + 1} ***\r\n".encode())
                sys.stdout.flush()

    async def __handle_command_key(self, key: bytes):
        """Execute a bound command if the key has a configured keybinding.

        Looks up the key in the keybinding map and, if found, invokes the
        corresponding CLI command on the appropriate child driver.

        Args:
            key: The pressed key byte.

        Returns:
            True if a command was executed, False if no binding matched.
        """
        if key in self.key_bindings_commands:
            command = self.key_bindings_commands[key]
            domain = command[0]
            args = command[1:]
            await to_thread.run_sync(lambda: self.cli.children[domain].cli().main(args, standalone_mode=False))
            return True
        return False

    async def __stdin_to_serial(self):
        """Read stdin and route input to the active UART or handle control keys.

        Processes one byte at a time:
        - ESC byte: sets a flag to treat the next byte as an Alt+key sequence
        - Alt+key: delegates to __handle_alt_key for view switching
        - Bound key: executes the configured keybinding command
        - Ctrl+B x3: raises ConsoleExit to terminate the console
        - Any other byte: forwarded to the currently selected UART stream
        """
        stdin = FileReadStream(sys.stdin.buffer)
        ctrl_b_count = 0
        escape_pending = False
        while True:
            data = await stdin.receive(max_bytes=1)
            if not data:
                continue

            # Detect ESC prefix for Alt+key
            if data == b"\x1b":
                escape_pending = True
                continue

            if escape_pending:
                escape_pending = False
                await self.__handle_alt_key(data)
                continue

            if data == b"\x02":  # Ctrl-B
                ctrl_b_count += 1
                if ctrl_b_count == 3:
                    raise ConsoleExit
                continue

            ctrl_b_count = 0

            if await self.__handle_command_key(data):
                continue

            if self.current_serial and self.current_serial in self.streams:
                await self.streams[self.current_serial].send(data)
