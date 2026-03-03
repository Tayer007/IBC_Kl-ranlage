"""
Hardware abstraction layer for GPIO control.
Supports both mock mode (for Windows development) and real GPIO mode (for Raspberry Pi).
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional
import time
import random
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

    @abstractmethod
    def read_distance(self, trigger_pin: int, echo_pin: int) -> float:
        """Read distance from ultrasonic sensor (in cm)"""
        pass


class MockGPIO(GPIOInterface):
    """Mock GPIO for Windows development - simulates hardware behavior"""

    def __init__(self):
        self.pin_states: Dict[int, bool] = {}
        self.simulated_water_level = 100.0  # cm from sensor (starts at low level - ready to fill)
        self.pump_running_time = 0.0
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
        old_state = self.pin_states.get(pin, False)
        self.pin_states[pin] = state

        # Simulate water level changes based on pump states
        self._update_simulation()

        state_str = "HIGH" if state else "LOW"
        print(f"[MOCK GPIO] Pin {pin} set to {state_str}")

    def get_output(self, pin: int) -> bool:
        """Get mock output pin state"""
        return self.pin_states.get(pin, False)

    def read_distance(self, trigger_pin: int, echo_pin: int) -> float:
        """Simulate ultrasonic distance reading"""
        self._update_simulation()

        # Add some noise to simulate real sensor
        noise = random.uniform(-0.5, 0.5)
        distance = max(5.0, min(150.0, self.simulated_water_level + noise))

        print(f"[MOCK GPIO] Distance sensor reading: {distance:.2f} cm")
        return distance

    def read_input(self, pin: int) -> bool:
        """Read mock input pin state - always returns False for simulated buttons"""
        return False

    def setup_input(self, pin: int, pull_down: bool = True):
        """Setup mock input pin - no-op for mock GPIO"""
        print(f"[MOCK GPIO] Pin {pin} configured as input with pull_{'down' if pull_down else 'up'}")

    def _update_simulation(self):
        """Update simulated water level based on component states"""
        current_time = time.time()
        time_delta = current_time - self.last_update
        self.last_update = current_time

        # Simulate water level changes (simplified physics)
        # Lower sensor reading = higher water level
        # Higher sensor reading = lower water level
        fill_rate = 5.0  # cm per second decrease when filling (water rising)
        drain_rate = 4.0  # cm per second increase when draining (water falling)

        # Check component states (matching professor's GPIO pins)
        # Professor uses active-low relays: LOW=ON, HIGH=OFF
        # In our abstraction: True=ON, False=OFF (we handle relay logic in controller)
        inlet_pump_on = self.pin_states.get(22, False)  # GPIO 22 - Zulaufpumpe (inlet pump)
        drain_valve_on = self.pin_states.get(27, False)  # GPIO 27 - Ablaufventil (drain valve)

        if inlet_pump_on and not drain_valve_on:
            # Filling: water level rises, sensor reading decreases
            self.simulated_water_level -= fill_rate * time_delta
        elif drain_valve_on and not inlet_pump_on:
            # Draining: water level falls, sensor reading increases
            self.simulated_water_level += drain_rate * time_delta

        # Keep within realistic bounds (sensor range: 5-150cm)
        self.simulated_water_level = max(15.0, min(145.0, self.simulated_water_level))


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

    def read_distance(self, trigger_pin: int, echo_pin: int) -> float:
        """Read distance from HC-SR04 ultrasonic sensor"""
        if not self.available:
            raise RuntimeError("RPi.GPIO not available")

        # Setup pins
        self.GPIO.setup(trigger_pin, self.GPIO.OUT)
        self.GPIO.setup(echo_pin, self.GPIO.IN)

        # Send trigger pulse
        self.GPIO.output(trigger_pin, False)
        time.sleep(0.00001)
        self.GPIO.output(trigger_pin, True)
        time.sleep(0.00001)
        self.GPIO.output(trigger_pin, False)

        # Wait for echo
        timeout = time.time() + 0.1  # 100ms timeout

        while self.GPIO.input(echo_pin) == 0:
            pulse_start = time.time()
            if pulse_start > timeout:
                return -1.0  # Timeout error

        while self.GPIO.input(echo_pin) == 1:
            pulse_end = time.time()
            if pulse_end > timeout:
                return -1.0  # Timeout error

        # Calculate distance
        pulse_duration = pulse_end - pulse_start
        distance = pulse_duration * 17150  # Speed of sound: 343m/s
        distance = round(distance, 2)

        return distance

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
