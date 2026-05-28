"""
InputManager - 동시 키 입력 지원 모듈
여러 레인의 키를 동시에 누를 수 있도록 ctypes 기반 직접 입력 사용
Windows: SendInput API / Linux: keyboard 라이브러리
"""

import time
import platform
import threading
from typing import List, Dict, Set

# Windows에서 ctypes로 직접 키 입력 (가장 빠름, 동시 입력 가능)
_IS_WINDOWS = platform.system() == "Windows"

if _IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)

    INPUT_KEYBOARD = 1
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_SCANCODE = 0x0008

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class INPUT(ctypes.Structure):
        class _INPUT(ctypes.Union):
            _fields_ = [("ki", KEYBDINPUT)]
        _fields_ = [
            ("type", wintypes.DWORD),
            ("_input", _INPUT),
        ]

    # 가상 키코드 매핑
    VK_MAP = {
        "a": 0x41, "b": 0x42, "c": 0x43, "d": 0x44, "e": 0x45,
        "f": 0x46, "g": 0x47, "h": 0x48, "i": 0x49, "j": 0x4A,
        "k": 0x4B, "l": 0x4C, "m": 0x4D, "n": 0x4E, "o": 0x4F,
        "p": 0x50, "q": 0x51, "r": 0x52, "s": 0x53, "t": 0x54,
        "u": 0x55, "v": 0x56, "w": 0x57, "x": 0x58, "y": 0x59,
        "z": 0x5A,
        "0": 0x30, "1": 0x31, "2": 0x32, "3": 0x33, "4": 0x34,
        "5": 0x35, "6": 0x36, "7": 0x37, "8": 0x38, "9": 0x39,
        "space": 0x20, "enter": 0x0D, "shift": 0x10, "ctrl": 0x11,
        "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    }

    def _send_input(*inputs):
        """SendInput API로 여러 키를 한 번에 전송"""
        n = len(inputs)
        arr = (INPUT * n)(*inputs)
        user32.SendInput(n, arr, ctypes.sizeof(INPUT))

    def _make_key_input(vk: int, flags: int = 0) -> INPUT:
        """키 입력 구조체 생성"""
        inp = INPUT()
        inp.type = INPUT_KEYBOARD
        inp._input.ki.wVk = vk
        inp._input.ki.dwFlags = flags
        return inp

else:
    # Linux/Mac: keyboard 또는 pyautogui 사용
    try:
        import keyboard as _keyboard
    except ImportError:
        _keyboard = None
    try:
        import pyautogui
        pyautogui.FAILSAFE = False
        pyautogui.PAUSE = 0
    except ImportError:
        pyautogui = None


class InputManager:
    """동시 키 입력을 지원하는 입력 관리자"""

    def __init__(self):
        # 레인별 상태 (lock-free 접근용 - 레인별 독립)
        self._key_bindings: List[str] = []
        self._last_press_time: Dict[int, float] = {}
        self._key_held: Dict[int, bool] = {}
        self._debounce_sec: float = 0.015
        self._input_delay_sec: float = 0.0
        self._active_lanes: Set[int] = set()
        self._running = False
        self._lock = threading.Lock()

    def configure(self, key_bindings: List[str], debounce_ms: int = 15,
                  input_delay_ms: int = 0) -> None:
        self._key_bindings = list(key_bindings)
        self._debounce_sec = debounce_ms / 1000.0
        self._input_delay_sec = input_delay_ms / 1000.0
        for i in range(len(key_bindings)):
            self._last_press_time[i] = 0.0
            self._key_held[i] = False

    def start(self) -> None:
        self._running = True
        self._active_lanes = set()

    def stop(self) -> None:
        self._running = False
        # 모든 키 해제
        for lane_idx in range(len(self._key_bindings)):
            if self._key_held.get(lane_idx, False):
                self._do_release(self._key_bindings[lane_idx])
                self._key_held[lane_idx] = False
        self._active_lanes = set()

    def press_lanes_batch(self, lanes: Set[int], long_lanes: Set[int]) -> None:
        """
        여러 레인의 키를 동시에 입력 (핵심 메서드)

        Args:
            lanes: 입력할 레인 인덱스 집합 (일반 노트)
            long_lanes: 롱노트로 누르고 있을 레인 인덱스 집합
        """
        if not self._running:
            return

        current_time = time.time()

        if _IS_WINDOWS:
            # Windows: SendInput으로 모든 키를 한 번에 전송
            inputs = []
            for lane in lanes | long_lanes:
                if lane >= len(self._key_bindings):
                    continue

                # debounce 체크
                if current_time - self._last_press_time.get(lane, 0.0) < self._debounce_sec:
                    continue

                # 이미 누르고 있는 롱노트면 스킵
                if lane in long_lanes and self._key_held.get(lane, False):
                    continue

                key = self._key_bindings[lane]
                vk = VK_MAP.get(key.lower(), 0)
                if vk == 0:
                    continue

                if lane in long_lanes:
                    # 롱노트: 누르기만
                    inputs.append(_make_key_input(vk, 0))
                    self._key_held[lane] = True
                else:
                    # 일반 노트: 누르기 + 떼기
                    inputs.append(_make_key_input(vk, 0))
                    inputs.append(_make_key_input(vk, KEYEVENTF_KEYUP))

                self._last_press_time[lane] = current_time
                self._active_lanes.add(lane)

            if inputs:
                _send_input(*inputs)
        else:
            # Linux/Mac: 개별 처리 (가능한 빠르게)
            for lane in lanes | long_lanes:
                if lane >= len(self._key_bindings):
                    continue
                if current_time - self._last_press_time.get(lane, 0.0) < self._debounce_sec:
                    continue
                if lane in long_lanes and self._key_held.get(lane, False):
                    continue

                key = self._key_bindings[lane]
                if lane in long_lanes:
                    self._do_press(key)
                    self._key_held[lane] = True
                else:
                    self._do_tap(key)

                self._last_press_time[lane] = current_time
                self._active_lanes.add(lane)

    def press_lane(self, lane_idx: int, is_long_note: bool = False) -> bool:
        """단일 레인 입력 (하위 호환)"""
        if not self._running or lane_idx >= len(self._key_bindings):
            return False

        current_time = time.time()
        if current_time - self._last_press_time.get(lane_idx, 0.0) < self._debounce_sec:
            return False
        if is_long_note and self._key_held.get(lane_idx, False):
            return False

        key = self._key_bindings[lane_idx]
        if is_long_note:
            self._do_press(key)
            self._key_held[lane_idx] = True
        else:
            self._do_tap(key)

        self._last_press_time[lane_idx] = current_time
        self._active_lanes.add(lane_idx)
        return True

    def release_lane(self, lane_idx: int) -> None:
        if lane_idx >= len(self._key_bindings):
            return
        if self._key_held.get(lane_idx, False):
            self._do_release(self._key_bindings[lane_idx])
            self._key_held[lane_idx] = False
        self._active_lanes.discard(lane_idx)

    def release_lanes_batch(self, lanes: Set[int]) -> None:
        """여러 레인 키를 동시 해제"""
        if _IS_WINDOWS:
            inputs = []
            for lane in lanes:
                if lane >= len(self._key_bindings):
                    continue
                if not self._key_held.get(lane, False):
                    continue
                key = self._key_bindings[lane]
                vk = VK_MAP.get(key.lower(), 0)
                if vk:
                    inputs.append(_make_key_input(vk, KEYEVENTF_KEYUP))
                self._key_held[lane] = False
                self._active_lanes.discard(lane)
            if inputs:
                _send_input(*inputs)
        else:
            for lane in lanes:
                self.release_lane(lane)

    # ─── 내부 키 입력 (Linux/Mac) ───

    def _do_tap(self, key: str) -> None:
        try:
            if _IS_WINDOWS:
                vk = VK_MAP.get(key.lower(), 0)
                if vk:
                    _send_input(
                        _make_key_input(vk, 0),
                        _make_key_input(vk, KEYEVENTF_KEYUP),
                    )
            elif _keyboard is not None:
                _keyboard.press_and_release(key)
            elif pyautogui is not None:
                pyautogui.press(key)
        except Exception:
            pass

    def _do_press(self, key: str) -> None:
        try:
            if _IS_WINDOWS:
                vk = VK_MAP.get(key.lower(), 0)
                if vk:
                    _send_input(_make_key_input(vk, 0))
            elif _keyboard is not None:
                _keyboard.press(key)
            elif pyautogui is not None:
                pyautogui.keyDown(key)
        except Exception:
            pass

    def _do_release(self, key: str) -> None:
        try:
            if _IS_WINDOWS:
                vk = VK_MAP.get(key.lower(), 0)
                if vk:
                    _send_input(_make_key_input(vk, KEYEVENTF_KEYUP))
            elif _keyboard is not None:
                _keyboard.release(key)
            elif pyautogui is not None:
                pyautogui.keyUp(key)
        except Exception:
            pass

    @property
    def active_lanes(self) -> List[int]:
        return list(self._active_lanes)

    @property
    def key_bindings(self) -> List[str]:
        return list(self._key_bindings)
