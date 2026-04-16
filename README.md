# JmpConsole - Multi-UART Console Driver

A Jumpstarter driver for managing multiple serial (UART) connections with an aggregated console view.

## Why?

When working with multi-core SoCs or devices with multiple serial ports, you need to:
- View logs from all UARTs simultaneously to see what's happening across all cores
- Switch between UARTs for interactive debugging on specific cores
- Monitor boot sequences and debug issues across multiple serial connections

JmpConsole gives you an aggregated view of all UARTs with prefixes like `[core0]`, `[core1]`, and lets you switch to individual UARTs for interactive commands.

## Installation

```bash
pip install -e .
```

## Configuration

Add to your Jumpstarter YAML configuration:

```yaml
exporter:
  drivers:
    my_device:
      type: jumpstarter_jmp_console.driver.JmpConsole
      children:
        core0:
          type: PySerial
          url: "/dev/ttyUSB0"
          baudrate: 115200
        core1:
          type: PySerial
          url: "/dev/ttyUSB1"
          baudrate: 115200
```

Optional: Add custom key bindings for commands:

```yaml
exporter:
  drivers:
    my_device:
      type: jumpstarter_jmp_console.driver.JmpConsole
      commands:
        reboot:
          # CTRL+R
          key: "\x12"
          command: power cycle --wait 1 
      children:
        core0:
          type: PySerial
          url: "/dev/ttyUSB0"
          baudrate: 115200
        power:
          type: jumpstarter_driver_power.driver.MockPower
```

## Usage

### Start the Console

```bash
j my_device console
```

### Aggregated Mode (Default)

View all UARTs simultaneously with prefixes:

```
*** Aggregated view (2 UARTs) ***
[core0] Booting core 0...
[core1] Booting core 1...
[core0] Core 0 ready
[core1] Core 1 ready
```

This mode is read-only and perfect for monitoring.

### Interactive Mode

Switch to a specific UART for read/write access:

- Press `Alt+1` to switch to first UART
- Press `Alt+2` to switch to second UART
- Press `Alt+0` to return to aggregated view

In interactive mode, you can type commands directly:

```
*** Interactive mode: core0 ***
> status
Core status: Running
```

### Exit

Press `Ctrl+B` three times to exit the console.

## License

Apache-2.0
