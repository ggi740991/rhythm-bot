"""
InputManager - keyboard 라이브러리 기반 키 입력
keyboard.press() / keyboard.release()로 직접 입력
(키 테스트에서 작동 확인된 방식)
"""

import time
import threading
from typing import List, Dict, Set

try:
    import keyboard
except ImportError:
    keyboard = None

try:
    import pyautogui
    pyautogui.FAILSAFE = False
    pyautogui.PAUSE = 0
except ImportError:
    pyautogui = None


class InputManager:
    """keyboard 라이브러리 기반 입력 관리자"""

    def __init__(self):
        self._key_bindings: List[str] = []
        self._last_press_time: Dict[int, float] = {}
        self._key_held: Dict[int, bool] = {}
        self._debounce_sec: float = 0.008
        self._active_lanes: Set[int] = set()
        self._running = False
        self._press_count = 0

    def configure(self, key_bindings: List[str], debounce_ms: int = 8,
                  input_delay_ms: int = 0) -> None:
        self._key_bindings = list(key_bindings)
        self._debounce_sec = debounce_ms / 1000.0
        for i in range(len(key_bindings)):
            self._last_press_time[i] = 0.0
            self._key_held[i] = False

    def start(self) -> None:
        self._running = True
        self._active_lanes = set()
        self._press_count = 0

    def stop(self) -> None:
        self._running = False
        for lane_idx in range(len(self._key_bindings)):
            if self._key_held.get(lane_idx, False):
                self._release_key(self._key_bindings[lane_idx])
                self._key_held[lane_idx] = False
        self._active_lanes = set()

    def press_lanes_batch(self, lanes: Set[int], long_lanes: Set[int]) -> None:
        """여러 레인의 키를 동시에 입력 (동타 지원)"""
        if not self._running:
            return

        now = time.perf_counter()
        tap_lanes: List[int] = []

        for lane in lanes | long_lanes:
            if lane >= len(self._key_bindings):
                continue
            if now - self._last_press_time.get(lane, 0.0) < self._debounce_sec:
                continue
            if lane in long_lanes and self._key_held.get(lane, False):
                continue

            key = self._key_bindings[lane]

            # 모든 키를 먼저 누름 (동시 입력)
            self._press_key(key)
            self._last_press_time[lane] = now
            self._active_lanes.add(lane)
            self._press_count += 1

            if lane in long_lanes:
                self._key_held[lane] = True
            else:
                tap_lanes.append(lane)

        # 짧은 노트 키: 잠시 유지 후 해제 (게임이 동시 입력으로 인식하도록)
        if tap_lanes:
            time.sleep(0.008)
            for lane in tap_lanes:
                self._release_key(self._key_bindings[lane])

    def release_lanes_batch(self, lanes: Set[int]) -> None:
        """여러 레인 키를 해제"""
        for lane in lanes:
            if lane >= len(self._key_bindings):
                continue
            if not self._key_held.get(lane, False):
                continue
            self._release_key(self._key_bindings[lane])
            self._key_held[lane] = False
            self._active_lanes.discard(lane)

    def release_lane(self, lane_idx: int) -> None:
        if lane_idx >= len(self._key_bindings):
            return
        if self._key_held.get(lane_idx, False):
            self._release_key(self._key_bindings[lane_idx])
            self._key_held[lane_idx] = False
        self._active_lanes.discard(lane_idx)

    # ─── 내부 키 입력 (keyboard 라이브러리 사용) ───

    def _tap_key(self, key: str) -> None:
        """키 누르고 바로 떼기"""
        try:
            if keyboard is not None:
                keyboard.press(key)
                keyboard.release(key)
            elif pyautogui is not None:
                pyautogui.press(key)
        except Exception:
            pass

    def _press_key(self, key: str) -> None:
        """키 누르기 (유지)"""
        try:
            if keyboard is not None:
                keyboard.press(key)
            elif pyautogui is not None:
                pyautogui.keyDown(key)
        except Exception:
            pass

    def _release_key(self, key: str) -> None:
        """키 해제"""
        try:
            if keyboard is not None:
                keyboard.release(key)
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

    @property
    def press_count(self) -> int:
        return self._press_count
