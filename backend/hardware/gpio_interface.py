"""
Hardware abstraction layer for GPIO control.
Supports both mock mode (for Windows development) and real GPIO mode (for Raspberry Pi).
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional
import time
from datetime import datetime


class GPIOInterface(ABC):
    """Abstract base class for GPIO operations"""

    @abstractmethod
    def setup(self):
        """Initialize GPIO pins"""
        pass

    @abstractmethod
    def cleanup(self):
        """Cleanup GPIO resources"""
        pass

    @abstractmethod
    def set_output(self, pin: int, state: bool):
        """Set output pin state (True=HIGH, False=LOW)"""
        pass

    @abstractmethod
    def get_output(self, pin: int) -> bool:
        """Get current output pin state"""
        pass


class MockGPIO(GPIOInterface):
    """Mock GPIO for Windows development - simulates hardware behavior"""

    def __init__(self):
        self.pin_states: Dict[int, bool] = {}
        self.last_update = time.time()

    def setup(self):
        """Initialize mock GPIO"""
        print("[MOCK GPIO] Initializing mock GPIO interface")
        self.pin_states = {}

    def cleanup(self):
        """Cleanup mock GPIO"""
        print("[MOCK GPIO] Cleaning up mock GPIO")
        self.pin_states.clear()

    def set_output(self, pin: int, state: bool):
        """Set mock output pin state"""
        self.pin_states[pin] = state
        state_str = "HIGH" if state else "LOW"
        print(f"[MOCK GPIO] Pin {pin} set to {state_str}")

    def get_output(self, pin: int) -> bool:
        """Get mock output pin state"""
        return self.pin_states.get(pin, False)

    def read_input(self, pin: int) -> bool:
        """Read mock input pin state - always returns False for simulated buttons"""
        return False

    def setup_input(self, pin: int, pull_down: bool = True):
        """Setup mock input pin - no-op for mock GPIO"""
        print(f"[MOCK GPIO] Pin {pin} configured as input with pull_{'down' if pull_down else 'up'}")


class RaspberryPiGPIO(GPIOInterface):
    """Real GPIO interface for Raspberry Pi"""

    def __init__(self):
        try:
            import RPi.GPIO as GPIO
            self.GPIO = GPIO
            self.available = True
        except ImportError:
            print("[WARNING] RPi.GPIO not available. Run on Raspberry Pi or use mock mode.")
            self.GPIO = None
            self.available = False

    def setup(self):
        """Initialize Raspberry Pi GPIO"""
        if not self.available:
            raise RuntimeError("RPi.GPIO not available")

        self.GPIO.setmode(self.GPIO.BCM)
        self.GPIO.setwarnings(False)
        print("[RPi GPIO] GPIO initialized in BCM mode")

    def cleanup(self):
        """Cleanup Raspberry Pi GPIO"""
        if self.available:
            self.GPIO.cleanup()
            print("[RPi GPIO] GPIO cleanup complete")

    def set_output(self, pin: int, state: bool):
        """Set Raspberry Pi GPIO output"""
        if not self.available:
            raise RuntimeError("RPi.GPIO not available")

        self.GPIO.setup(pin, self.GPIO.OUT)
        self.GPIO.output(pin, self.GPIO.HIGH if state else self.GPIO.LOW)

    def get_output(self, pin: int) -> bool:
        """Get Raspberry Pi GPIO output state"""
        if not self.available:
            raise RuntimeError("RPi.GPIO not available")

        return self.GPIO.input(pin) == self.GPIO.HIGH

    def read_input(self, pin: int) -> bool:
        """Read Raspberry Pi GPIO input"""
        if not self.available:
            raise RuntimeError("RPi.GPIO not available")

        return self.GPIO.input(pin) == self.GPIO.HIGH

    def setup_input(self, pin: int, pull_down: bool = True):
        """Setup Raspberry Pi GPIO input pin"""
        if not self.available:
            raise RuntimeError("RPi.GPIO not available")

        pull_mode = self.GPIO.PUD_DOWN if pull_down else self.GPIO.PUD_UP
        self.GPIO.setup(pin, self.GPIO.IN, pull_up_down=pull_mode)
        print(f"[RPi GPIO] Pin {pin} configured as input with pull_{'down' if pull_down else 'up'}")


def get_gpio_interface(mode: str = "mock") -> GPIOInterface:
    """
    Factory function to get appropriate GPIO interface

    Args:
        mode: Either 'mock' for development or 'gpio' for Raspberry Pi

    Returns:
        GPIOInterface instance
    """
    if mode.lower() == "gpio":
        return RaspberryPiGPIO()
    else:
        return MockGPIO()
