"""
Main treatment process controller for IBC wastewater treatment plant - 12-Phase SBR System
Implements professor's step-feed biological nitrogen removal process
"""

import time
import yaml
import threading
from enum import Enum
from typing import Dict, Any, Optional, Callable
from datetime import datetime
from pathlib import Path

from hardware.gpio_interface import GPIOInterface, get_gpio_interface


class TreatmentPhase(Enum):
    """Treatment cycle phases - 12-phase SBR system"""
    IDLE = "idle"

    # Cycle 1
    ZULAUF_1 = "zulauf_1"
    UNBELUEFTET_1 = "unbelueftet_1"
    BELUEFTUNG_1 = "belueftung_1"

    # Cycle 2
    ZULAUF_2 = "zulauf_2"
    UNBELUEFTET_2 = "unbelueftet_2"
    BELUEFTUNG_2 = "belueftung_2"

    # Cycle 3
    ZULAUF_3 = "zulauf_3"
    UNBELUEFTET_3 = "unbelueftet_3"
    BELUEFTUNG_3 = "belueftung_3"

    # Final phases
    SEDIMENTATION = "sedimentation"
    KLARWASSERABZUG = "klarwasserabzug"
    STILLSTAND = "stillstand"

    # Special states
    EMERGENCY_STOP = "emergency_stop"
    ERROR = "error"


class AerationMode(Enum):
    """Aeration modes"""
    NONE = "none"
    CONTINUOUS = "continuous"  # Belüftung - for nitrification
    PULSE = "pulse"  # Stoßbelüftung - for mixing during denitrification


class TreatmentController:
    """
    Controls the 12-phase wastewater treatment process.
    Manages inlet pump, drain valve, and blower with two aeration modes.
    """

    def __init__(self, config_path: str, hardware_mode: str = "mock"):
        """
        Initialize treatment controller

        Args:
            config_path: Path to YAML configuration file
            hardware_mode: 'mock' for development, 'gpio' for Raspberry Pi
        """
        # Store config path for saving later
        self.config_path = config_path

        # Load configuration
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)

        # Initialize GPIO interface
        self.gpio = get_gpio_interface(hardware_mode)
        self.gpio.setup()

        # Setup water level sensor buttons as inputs
        # NOTE: Physical wiring is swapped - GPIO 23 = EMPTY, GPIO 24 = FULL
        self.gpio.setup_input(23, pull_down=True)  # Empty button - GPIO 23 (physically wired to empty sensor)
        self.gpio.setup_input(24, pull_down=True)  # Full button - GPIO 24 (physically wired to full sensor)
        print("[CONTROLLER] Water level sensor buttons configured on GPIO 23 (EMPTY) and GPIO 24 (FULL)")

        # State variables
        self.current_phase = TreatmentPhase.IDLE
        self.phase_start_time: Optional[float] = None
        self.cycle_start_time: Optional[float] = None
        self.is_running = False
        self.is_paused = False
        self.emergency_stopped = False

        # Component states (3 components matching professor's setup)
        self.component_states = {
            'inlet_pump': False,
            'drain_valve': False,
            'blower': False
        }

        # Aeration state
        self.current_aeration_mode = AerationMode.NONE
        self.aeration_thread: Optional[threading.Thread] = None
        self.aeration_stop_event = threading.Event()
        self.aeration_phase_start: Optional[float] = None

        self.last_level_read = 0.0

        # Water level button states (swapped due to physical wiring)
        self.water_full_button_pressed = False  # GPIO 24 - Tank FULL, stop inlet
        self.water_empty_button_pressed = False  # GPIO 23 - Tank EMPTY, stop drain

        # Threading
        self.control_thread: Optional[threading.Thread] = None
        self.lock = threading.Lock()

        # Event callbacks
        self.event_callbacks: Dict[str, Callable] = {}

        # Statistics
        self.stats = {
            'cycles_completed': 0,
            'total_runtime': 0,
            'errors': [],
            'last_cycle_start': None,
            'last_cycle_end': None
        }

        # Repetitions tracking
        self.total_repetitions = self.config.get('cycle_repetitions', 1)
        self.current_repetition = 0

        # Build phase sequence dynamically based on num_cycles
        self.phase_sequence = self._build_phase_sequence()

        num_cycles = self.config.get('num_cycles', 3)
        print(f"[CONTROLLER] Initialized {num_cycles}-cycle SBR controller in {hardware_mode} mode")
        print(f"[CONTROLLER] Cycle repetitions: {self.total_repetitions}")

    def register_event_callback(self, event_type: str, callback: Callable):
        """Register callback for events (for WebSocket updates)"""
        self.event_callbacks[event_type] = callback

    def _build_phase_sequence(self) -> list:
        """Build phase sequence dynamically based on num_cycles configuration"""
        num_cycles = self.config.get('num_cycles', 3)
        sequence = []

        # Add feed cycles (Zulauf -> Unbelüftet -> Belüftung)
        # Cycles 1-3 use their specific enums
        # Cycles 4+ reuse ZULAUF_3, UNBELUEFTET_3, BELUEFTUNG_3
        for i in range(1, num_cycles + 1):
            if i == 1:
                sequence.extend([
                    TreatmentPhase.ZULAUF_1,
                    TreatmentPhase.UNBELUEFTET_1,
                    TreatmentPhase.BELUEFTUNG_1
                ])
            elif i == 2:
                sequence.extend([
                    TreatmentPhase.ZULAUF_2,
                    TreatmentPhase.UNBELUEFTET_2,
                    TreatmentPhase.BELUEFTUNG_2
                ])
            else:  # i >= 3 (cycles 3, 4, 5, ..., 9999)
                sequence.extend([
                    TreatmentPhase.ZULAUF_3,
                    TreatmentPhase.UNBELUEFTET_3,
                    TreatmentPhase.BELUEFTUNG_3
                ])

        # Always add final phases
        sequence.extend([
            TreatmentPhase.SEDIMENTATION,
            TreatmentPhase.KLARWASSERABZUG,
            TreatmentPhase.STILLSTAND
        ])

        return sequence

    def _emit_event(self, event_type: str, data: Dict[str, Any]):
        """Emit event to registered callbacks"""
        if event_type in self.event_callbacks:
            try:
                self.event_callbacks[event_type](data)
            except Exception as e:
                print(f"[CONTROLLER] Error in event callback: {e}")

    def start_cycle(self) -> bool:
        """Start a new treatment cycle"""
        with self.lock:
            if self.is_running:
                print("[CONTROLLER] Cycle already running")
                return False

            if self.emergency_stopped:
                print("[CONTROLLER] Cannot start - emergency stop active")
                return False

            self.is_running = True
            self.is_paused = False
            self.current_phase = self.phase_sequence[0]  # Start with first phase
            self.cycle_start_time = time.time()
            self.stats['last_cycle_start'] = datetime.now().isoformat()

            # Start control thread
            self.control_thread = threading.Thread(target=self._control_loop, daemon=True)
            self.control_thread.start()

            print("[CONTROLLER] 12-phase treatment cycle started")
            self._emit_event('cycle_started', {'timestamp': datetime.now().isoformat()})
            return True

    def stop_cycle(self) -> bool:
        """Stop the current treatment cycle"""
        with self.lock:
            if not self.is_running:
                print("[CONTROLLER] No cycle running")
                return False

            self.is_running = False
            self.is_paused = False

            # Stop aeration
            self._stop_aeration()

            # Turn off all components
            self._set_all_components_off()
            self.current_phase = TreatmentPhase.IDLE

            if self.cycle_start_time:
                runtime = time.time() - self.cycle_start_time
                self.stats['total_runtime'] += runtime

            self.stats['last_cycle_end'] = datetime.now().isoformat()

            print("[CONTROLLER] Treatment cycle stopped")
            self._emit_event('cycle_stopped', {'timestamp': datetime.now().isoformat()})
            return True

    def pause_cycle(self) -> bool:
        """Pause the current cycle"""
        with self.lock:
            if not self.is_running or self.is_paused:
                return False

            self.is_paused = True
            self._stop_aeration()
            self._set_all_components_off()
            print("[CONTROLLER] Cycle paused")
            self._emit_event('cycle_paused', {'timestamp': datetime.now().isoformat()})
            return True

    def resume_cycle(self) -> bool:
        """Resume a paused cycle"""
        with self.lock:
            if not self.is_running or not self.is_paused:
                return False

            self.is_paused = False
            print("[CONTROLLER] Cycle resumed")
            self._emit_event('cycle_resumed', {'timestamp': datetime.now().isoformat()})
            return True

    def emergency_stop(self):
        """Emergency stop - immediately shut down all components"""
        with self.lock:
            print("[CONTROLLER] EMERGENCY STOP ACTIVATED")
            self.emergency_stopped = True
            self.is_running = False
            self.is_paused = False
            self.current_phase = TreatmentPhase.EMERGENCY_STOP
            self._stop_aeration()
            self._set_all_components_off()
            self._emit_event('emergency_stop', {'timestamp': datetime.now().isoformat()})

    def reset_emergency_stop(self):
        """Reset emergency stop condition"""
        with self.lock:
            self.emergency_stopped = False
            self.current_phase = TreatmentPhase.IDLE
            print("[CONTROLLER] Emergency stop reset")
            self._emit_event('emergency_reset', {'timestamp': datetime.now().isoformat()})

    def set_component(self, component: str, state: bool) -> bool:
        """Manually set component state (for manual mode)"""
        with self.lock:
            if self.is_running:
                print("[CONTROLLER] Cannot manually control components while cycle is running")
                return False

            if component not in self.component_states:
                return False

            # Safety check: Read button states before allowing manual control
            if state == True:  # Only check when trying to turn ON
                # NOTE: Wiring is swapped - GPIO 24 = FULL, GPIO 23 = EMPTY
                water_full = self.gpio.read_input(24)   # GPIO 24 connected to FULL sensor
                water_empty = self.gpio.read_input(23)  # GPIO 23 connected to EMPTY sensor

                if component == 'inlet_pump' and water_full:
                    print("[WATER LEVEL] Cannot turn on inlet pump - Tank is FULL")
                    return False

                if component == 'drain_valve' and water_empty:
                    print("[WATER LEVEL] Cannot turn on drain valve - Tank is EMPTY")
                    return False

            # Get pin number from config
            pin = self._get_component_pin(component)
            if pin is None:
                return False

            self.gpio.set_output(pin, state)
            self.component_states[component] = state

            print(f"[CONTROLLER] {component} manually set to {'ON' if state else 'OFF'}")
            self._emit_event('component_changed', {
                'component': component,
                'state': state,
                'timestamp': datetime.now().isoformat()
            })
            return True

    def _control_loop(self):
        """Main control loop - executes all phases in sequence with repetitions"""
        num_phases = len(self.phase_sequence)
        print(f"[CONTROLLER] Control loop started - beginning {num_phases}-phase cycle")
        print(f"[CONTROLLER] Will repeat {self.total_repetitions} time(s)")

        try:
            # Reset repetition counter
            self.current_repetition = 0

            # Repeat the entire cycle sequence
            while self.is_running and self.current_repetition < self.total_repetitions:
                self.current_repetition += 1
                print(f"[CONTROLLER] Starting repetition {self.current_repetition}/{self.total_repetitions}")

                phase_index = 0

                while self.is_running and phase_index < len(self.phase_sequence):
                    if self.is_paused:
                        time.sleep(0.5)
                        continue

                    # Set current phase
                    self.current_phase = self.phase_sequence[phase_index]

                    # Execute phase
                    print(f"[CONTROLLER] [Rep {self.current_repetition}/{self.total_repetitions}] Phase {phase_index + 1}/{num_phases}: {self.current_phase.value}")
                    self._execute_phase(self.current_phase)

                    # Move to next phase if still running
                    if self.is_running:
                        phase_index += 1

                # Repetition complete
                if self.is_running:
                    print(f"[CONTROLLER] Repetition {self.current_repetition}/{self.total_repetitions} completed")

            # All cycles complete
            if self.is_running:
                print(f"[CONTROLLER] All {self.total_repetitions} repetition(s) completed successfully")
                self.stats['cycles_completed'] += 1
                self._emit_event('cycle_completed', {
                    'cycles_completed': self.stats['cycles_completed'],
                    'repetitions_completed': self.current_repetition,
                    'timestamp': datetime.now().isoformat()
                })
                self.stop_cycle()

        except Exception as e:
            print(f"[CONTROLLER] Error in control loop: {e}")
            self.current_phase = TreatmentPhase.ERROR
            self._stop_aeration()
            self._set_all_components_off()
            self.stats['errors'].append({
                'timestamp': datetime.now().isoformat(),
                'error': str(e)
            })

        finally:
            self._stop_aeration()
            self._set_all_components_off()
            print("[CONTROLLER] Control loop ended")

    def _execute_phase(self, phase: TreatmentPhase):
        """Execute a single phase"""
        # Get phase configuration
        phase_config = self._get_phase_config(phase)
        if not phase_config:
            print(f"[CONTROLLER] No configuration for phase {phase.value}")
            return

        # Get phase duration
        duration_param = phase_config.get('duration_param')
        phase_duration = self.config['phase_durations'].get(duration_param, 0)

        # Skip phase if duration is 0
        if phase_duration == 0:
            print(f"[CONTROLLER] Skipping phase {phase.value} (duration = 0)")
            return

        # Emit phase change event
        self._emit_event('phase_changed', {
            'phase': phase.value,
            'duration': phase_duration,
            'timestamp': datetime.now().isoformat()
        })

        # Set component states
        inlet_pump = phase_config.get('inlet_pump', False)
        drain_valve = phase_config.get('drain_valve', False)
        self._set_component_state('inlet_pump', inlet_pump)
        self._set_component_state('drain_valve', drain_valve)

        # Start aeration mode
        aeration_mode_str = phase_config.get('aeration_mode', 'none')
        if aeration_mode_str == 'continuous':
            self._start_aeration(AerationMode.CONTINUOUS)
        elif aeration_mode_str == 'pulse':
            self._start_aeration(AerationMode.PULSE)
        else:
            self._stop_aeration()

        # Wait for phase duration
        phase_start = time.time()
        self.phase_start_time = phase_start

        while self.is_running and not self.is_paused:
            # Read sensors periodically
            self._read_sensors()

            # Check safety conditions
            if not self._check_safety():
                self.emergency_stop()
                return

            # Check if phase duration elapsed
            elapsed = time.time() - phase_start
            if elapsed >= phase_duration:
                break

            time.sleep(1.0)  # Check every second

        # Stop aeration for this phase
        self._stop_aeration()

        # Turn off components (except blower which is managed by aeration thread)
        self._set_component_state('inlet_pump', False)
        self._set_component_state('drain_valve', False)

        print(f"[CONTROLLER] Phase {phase.value} completed")

    def _start_aeration(self, mode: AerationMode):
        """Start aeration in specified mode"""
        # Stop any existing aeration
        self._stop_aeration()

        if mode == AerationMode.NONE:
            return

        self.current_aeration_mode = mode
        self.aeration_stop_event.clear()
        self.aeration_phase_start = time.time()

        # Start aeration thread
        if mode == AerationMode.CONTINUOUS:
            self.aeration_thread = threading.Thread(
                target=self._continuous_aeration_loop,
                daemon=True
            )
        elif mode == AerationMode.PULSE:
            self.aeration_thread = threading.Thread(
                target=self._pulse_aeration_loop,
                daemon=True
            )

        self.aeration_thread.start()
        print(f"[CONTROLLER] Started aeration mode: {mode.value}")

    def _stop_aeration(self):
        """Stop aeration thread"""
        if self.aeration_thread and self.aeration_thread.is_alive():
            self.aeration_stop_event.set()
            self.aeration_thread.join(timeout=2.0)
            self._set_component_state('blower', False)
            self.current_aeration_mode = AerationMode.NONE
            print("[CONTROLLER] Stopped aeration")

    def _continuous_aeration_loop(self):
        """Continuous aeration pattern: ON for t_luftan → OFF for t_luftpause → repeat"""
        aeration_config = self.config['aeration']['continuous']
        t_luftan = aeration_config['t_luftan']
        t_luftpause = aeration_config['t_luftpause']

        print(f"[CONTROLLER] Continuous aeration: ON {t_luftan}s, PAUSE {t_luftpause}s")

        while not self.aeration_stop_event.is_set() and self.is_running:
            if self.is_paused:
                time.sleep(0.5)
                continue

            # Blower ON phase
            self._set_component_state('blower', True)
            self._emit_event('aeration_status', {
                'mode': 'continuous',
                'status': 'on',
                'timestamp': datetime.now().isoformat()
            })

            # Wait for ON duration
            if self._wait_interruptible(t_luftan):
                break

            # Blower OFF phase (pause)
            self._set_component_state('blower', False)
            self._emit_event('aeration_status', {
                'mode': 'continuous',
                'status': 'pause',
                'timestamp': datetime.now().isoformat()
            })

            # Wait for PAUSE duration
            if self._wait_interruptible(t_luftpause):
                break

        # Ensure blower is off when thread exits
        self._set_component_state('blower', False)

    def _pulse_aeration_loop(self):
        """Pulse aeration pattern: OFF for t_stosspause → ON for t_stossan → repeat"""
        aeration_config = self.config['aeration']['pulse']
        t_stossan = aeration_config['t_stossan']
        t_stosspause = aeration_config['t_stosspause']

        print(f"[CONTROLLER] Pulse aeration: PAUSE {t_stosspause}s, ON {t_stossan}s")

        while not self.aeration_stop_event.is_set() and self.is_running:
            if self.is_paused:
                time.sleep(0.5)
                continue

            # Blower OFF phase (pause first)
            self._set_component_state('blower', False)
            self._emit_event('aeration_status', {
                'mode': 'pulse',
                'status': 'pause',
                'timestamp': datetime.now().isoformat()
            })

            # Wait for PAUSE duration
            if self._wait_interruptible(t_stosspause):
                break

            # Blower ON phase (short pulse)
            self._set_component_state('blower', True)
            self._emit_event('aeration_status', {
                'mode': 'pulse',
                'status': 'on',
                'timestamp': datetime.now().isoformat()
            })

            # Wait for ON duration
            if self._wait_interruptible(t_stossan):
                break

        # Ensure blower is off when thread exits
        self._set_component_state('blower', False)

    def _wait_interruptible(self, duration: float) -> bool:
        """
        Wait for specified duration, but can be interrupted by stop event.
        Returns True if interrupted, False if duration elapsed normally.
        """
        elapsed = 0
        while elapsed < duration and not self.aeration_stop_event.is_set():
            time.sleep(0.5)
            elapsed += 0.5
        return self.aeration_stop_event.is_set()

    def _read_sensors(self):
        """Read all sensors"""
        current_time = time.time()

        if current_time - self.last_level_read >= 1.0:
            self.last_level_read = current_time

            # Read water level sensor buttons (swapped due to physical wiring)
            self.water_full_button_pressed = self.gpio.read_input(24)  # Full sensor - GPIO 24
            self.water_empty_button_pressed = self.gpio.read_input(23)  # Empty sensor - GPIO 23

            # Debug logging - print button states
            print(f"[WATER LEVEL DEBUG] GPIO 24 (FULL): {self.water_full_button_pressed}, GPIO 23 (EMPTY): {self.water_empty_button_pressed}")

            # DISABLED: Check and stop components based on button states
            # These buttons are causing false triggers, disabling for now
            # TODO: Fix hardware wiring or debounce logic

            # if self.water_full_button_pressed:
            #     if self.component_states.get('inlet_pump', False):
            #         print("[WATER LEVEL] FULL sensor triggered - Stopping inlet pump")
            #         self._set_component_state('inlet_pump', False)
            #         self._emit_event('water_level_alarm', {
            #             'type': 'full',
            #             'message': 'Tank FULL - inlet pump stopped',
            #             'timestamp': datetime.now().isoformat()
            #         })

            # if self.water_empty_button_pressed:
            #     if self.component_states.get('drain_valve', False):
            #         print("[WATER LEVEL] EMPTY sensor triggered - Stopping drain valve")
            #         self._set_component_state('drain_valve', False)
            #         self._emit_event('water_level_alarm', {
            #             'type': 'empty',
            #             'message': 'Tank EMPTY - drain valve stopped',
            #             'timestamp': datetime.now().isoformat()
            #         })

            self._emit_event('sensor_update', {
                'water_full': self.water_full_button_pressed,
                'water_empty': self.water_empty_button_pressed,
                'timestamp': datetime.now().isoformat()
            })

    def _check_safety(self) -> bool:
        """Check safety conditions"""
        safety = self.config['safety']

        # Check total cycle duration
        if self.cycle_start_time:
            cycle_duration = time.time() - self.cycle_start_time
            if cycle_duration > safety['max_cycle_duration']:
                print("[CONTROLLER] Maximum cycle duration exceeded")
                return False

        return True

    def _get_phase_config(self, phase: TreatmentPhase) -> Optional[Dict]:
        """Get configuration for a specific phase"""
        phase_map = {
            TreatmentPhase.ZULAUF_1: 'phase_1_zulauf_1',
            TreatmentPhase.UNBELUEFTET_1: 'phase_2_deni_1',
            TreatmentPhase.BELUEFTUNG_1: 'phase_3_nitri_1',
            TreatmentPhase.ZULAUF_2: 'phase_4_zulauf_2',
            TreatmentPhase.UNBELUEFTET_2: 'phase_5_deni_2',
            TreatmentPhase.BELUEFTUNG_2: 'phase_6_nitri_2',
            TreatmentPhase.ZULAUF_3: 'phase_7_zulauf_3',
            TreatmentPhase.UNBELUEFTET_3: 'phase_8_deni_3',
            TreatmentPhase.BELUEFTUNG_3: 'phase_9_nitri_3',
            TreatmentPhase.SEDIMENTATION: 'phase_10_sedimentation',
            TreatmentPhase.KLARWASSERABZUG: 'phase_11_klarwasserabzug',
            TreatmentPhase.STILLSTAND: 'phase_12_stillstand',
        }

        phase_key = phase_map.get(phase)
        if phase_key:
            return self.config['treatment_phases'].get(phase_key)
        return None

    def _get_component_pin(self, component: str) -> Optional[int]:
        """Get GPIO pin for a component"""
        if component == 'blower':
            return self.config['hardware']['components']['blower']['pin']
        elif component in self.config['hardware']['components']:
            return self.config['hardware']['components'][component]['pin']
        return None

    def _set_component_state(self, component: str, state: bool):
        """Internal method to set component state"""
        pin = self._get_component_pin(component)
        if pin is not None:
            self.gpio.set_output(pin, state)
            self.component_states[component] = state

    def _set_all_components_off(self):
        """Turn off all components"""
        for component in self.component_states:
            self._set_component_state(component, False)

    def get_status(self) -> Dict[str, Any]:
        """Get current system status"""
        with self.lock:
            phase_elapsed = 0
            if self.phase_start_time:
                phase_elapsed = time.time() - self.phase_start_time

            cycle_elapsed = 0
            if self.cycle_start_time:
                cycle_elapsed = time.time() - self.cycle_start_time

            # Calculate total cycle duration
            total_cycle_duration = sum(self.config['phase_durations'].values())

            return {
                'is_running': self.is_running,
                'is_paused': self.is_paused,
                'emergency_stopped': self.emergency_stopped,
                'current_phase': self.current_phase.value,
                'phase_elapsed': round(phase_elapsed, 1),
                'cycle_elapsed': round(cycle_elapsed, 1),
                'total_cycle_duration': total_cycle_duration,
                'components': self.component_states.copy(),
                'aeration_mode': self.current_aeration_mode.value,
                'num_cycles': self.config.get('num_cycles', 3),
                'cycle_repetitions': self.total_repetitions,
                'current_repetition': self.current_repetition,
                'stats': self.stats.copy(),
                'timestamp': datetime.now().isoformat()
            }

    def update_phase_durations(self, durations: Dict[str, float]) -> bool:
        """
        Update phase durations dynamically.
        Can only be updated when cycle is not running.

        Args:
            durations: Dictionary with phase duration parameters
                      e.g., {'t_z1': 600, 't_d1': 900, ...}

        Returns:
            True if update successful, False otherwise
        """
        with self.lock:
            if self.is_running:
                print("[CONTROLLER] Cannot update configuration while cycle is running")
                return False

            # Validate all keys are valid phase duration parameters
            valid_keys = {
                't_z1', 't_d1', 't_n1',
                't_z2', 't_d2', 't_n2',
                't_z3', 't_d3', 't_n3',
                't_sed', 't_abzug', 't_still'
            }

            for key in durations.keys():
                if key not in valid_keys:
                    print(f"[CONTROLLER] Invalid phase duration key: {key}")
                    return False

            # Validate all values are non-negative numbers
            for key, value in durations.items():
                try:
                    val = float(value)
                    if val < 0:
                        print(f"[CONTROLLER] Invalid value for {key}: {val} (must be >= 0)")
                        return False
                except (ValueError, TypeError):
                    print(f"[CONTROLLER] Invalid value type for {key}: {value}")
                    return False

            # Update configuration
            for key, value in durations.items():
                self.config['phase_durations'][key] = float(value)

            print(f"[CONTROLLER] Updated phase durations: {durations}")

            # Save to YAML file
            self._save_config_to_file()

            return True

    def update_aeration_settings(self, settings: Dict[str, float]) -> bool:
        """
        Update aeration settings dynamically.
        Can only be updated when cycle is not running.

        Args:
            settings: Dictionary with aeration parameters
                     e.g., {'t_luftan': 300, 't_luftpause': 180, ...}

        Returns:
            True if update successful, False otherwise
        """
        with self.lock:
            if self.is_running:
                print("[CONTROLLER] Cannot update configuration while cycle is running")
                return False

            # Update continuous aeration settings
            if 't_luftan' in settings:
                self.config['aeration']['continuous']['t_luftan'] = float(settings['t_luftan'])
            if 't_luftpause' in settings:
                self.config['aeration']['continuous']['t_luftpause'] = float(settings['t_luftpause'])

            # Update pulse aeration settings
            if 't_stossan' in settings:
                self.config['aeration']['pulse']['t_stossan'] = float(settings['t_stossan'])
            if 't_stosspause' in settings:
                self.config['aeration']['pulse']['t_stosspause'] = float(settings['t_stosspause'])

            print(f"[CONTROLLER] Updated aeration settings: {settings}")

            # Save to YAML file
            self._save_config_to_file()

            return True

    def update_num_cycles(self, num_cycles: int) -> bool:
        """
        Update the number of feed cycles.
        Can only be updated when cycle is not running.

        Args:
            num_cycles: Number of feed cycles (0-9999)

        Returns:
            True if update successful, False otherwise
        """
        with self.lock:
            if self.is_running:
                print("[CONTROLLER] Cannot update configuration while cycle is running")
                return False

            # Validate num_cycles is in valid range
            if not isinstance(num_cycles, int) or num_cycles < 0 or num_cycles > 9999:
                print(f"[CONTROLLER] Invalid num_cycles: {num_cycles} (must be 0-9999)")
                return False

            # Update configuration
            self.config['num_cycles'] = num_cycles

            # Rebuild phase sequence
            self.phase_sequence = self._build_phase_sequence()

            print(f"[CONTROLLER] Updated num_cycles to {num_cycles}")
            print(f"[CONTROLLER] Rebuilt phase sequence with {len(self.phase_sequence)} phases")

            # Save to YAML file
            self._save_config_to_file()

            return True

    def update_cycle_repetitions(self, repetitions: int) -> bool:
        """
        Update the number of cycle repetitions.
        Can only be updated when cycle is not running.

        Args:
            repetitions: Number of times to repeat the entire cycle sequence (min: 1)

        Returns:
            True if update successful, False otherwise
        """
        with self.lock:
            if self.is_running:
                print("[CONTROLLER] Cannot update configuration while cycle is running")
                return False

            # Validate repetitions is a positive integer
            if not isinstance(repetitions, int) or repetitions < 1:
                print(f"[CONTROLLER] Invalid cycle_repetitions: {repetitions} (must be >= 1)")
                return False

            # Update configuration
            self.config['cycle_repetitions'] = repetitions
            self.total_repetitions = repetitions

            print(f"[CONTROLLER] Updated cycle_repetitions to {repetitions}")

            # Save to YAML file
            self._save_config_to_file()

            return True

    def _save_config_to_file(self):
        """Save current configuration to YAML file"""
        try:
            with open(self.config_path, 'w') as f:
                yaml.dump(self.config, f, default_flow_style=False, sort_keys=False)
            print(f"[CONTROLLER] Configuration saved to {self.config_path}")
        except Exception as e:
            print(f"[CONTROLLER] Error saving configuration: {e}")

    def cleanup(self):
        """Cleanup resources"""
        self.stop_cycle()
        time.sleep(1)  # Allow threads to finish
        self.gpio.cleanup()
        print("[CONTROLLER] Cleanup complete")
