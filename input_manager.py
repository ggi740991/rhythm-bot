"""
InputManager - 자동 키 입력 모듈
레인별 키 입력, 롱노트 지원, debounce 처리, 중복 입력 방지
"""

import time
import threading
from typing import List, Dict, Optional

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
    """자동 키 입력 관리자"""

    def __init__(self):
        self._lock = threading.Lock()
        # 레인별 마지막 입력 시간 (debounce용)
        self._last_press_time: Dict[int, float] = {}
        # 레인별 현재 눌린 상태 (롱노트용)
        self._key_held: Dict[int, bool] = {}
        # 레인별 키 바인딩
        self._key_bindings: List[str] = []
        # debounce 시간 (초)
        self._debounce_sec: float = 0.05
        # 입력 딜레이 (초)
        self._input_delay_sec: float = 0.0
        # 현재 입력 중인 레인 목록
        self._active_lanes: List[int] = []
        # 입력 방식 선택 (keyboard 또는 pyautogui)
        self._use_keyboard_lib = keyboard is not None
        # 실행 중 플래그
        self._running = False

    def configure(
        self,
        key_bindings: List[str],
        debounce_ms: int = 50,
        input_delay_ms: int = 0,
    ) -> None:
        """
        입력 설정 구성

        Args:
            key_bindings: 레인별 키 바인딩 리스트
            debounce_ms: debounce 시간 (밀리초)
            input_delay_ms: 입력 딜레이 (밀리초)
        """
        with self._lock:
            self._key_bindings = list(key_bindings)
            self._debounce_sec = debounce_ms / 1000.0
            self._input_delay_sec = input_delay_ms / 1000.0
            # 상태 초기화
            for i in range(len(key_bindings)):
                self._last_press_time.setdefault(i, 0.0)
                self._key_held.setdefault(i, False)

    def start(self) -> None:
        """입력 관리자 시작"""
        with self._lock:
            self._running = True
            self._active_lanes = []

    def stop(self) -> None:
        """입력 관리자 정지 - 모든 눌린 키 해제"""
        with self._lock:
            self._running = False
            # 모든 키 해제
            for lane_idx, held in self._key_held.items():
                if held and lane_idx < len(self._key_bindings):
                    self._release_key(self._key_bindings[lane_idx])
            self._key_held.clear()
            self._active_lanes = []

    def press_lane(self, lane_idx: int, is_long_note: bool = False) -> bool:
        """
        특정 레인의 키를 입력

        Args:
            lane_idx: 레인 인덱스
            is_long_note: 롱노트 여부 (True면 키를 누른 상태 유지)

        Returns:
            실제 입력이 발생했으면 True
        """
        with self._lock:
            if not self._running:
                return False

            if lane_idx >= len(self._key_bindings):
                return False

            current_time = time.time()

            # debounce 확인 (중복 입력 방지)
            last_time = self._last_press_time.get(lane_idx, 0.0)
            if current_time - last_time < self._debounce_sec:
                return False

            # 이미 눌린 상태면 무시 (롱노트 중복 방지)
            if self._key_held.get(lane_idx, False) and is_long_note:
                return False

            key = self._key_bindings[lane_idx]

            # 입력 딜레이 적용
            if self._input_delay_sec > 0:
                time.sleep(self._input_delay_sec)

            if is_long_note:
                # 롱노트: 키를 누른 상태로 유지
                self._press_key(key)
                self._key_held[lane_idx] = True
            else:
                # 일반 노트: 짧은 탭
                self._tap_key(key)

            self._last_press_time[lane_idx] = current_time

            # 활성 레인 업데이트
            if lane_idx not in self._active_lanes:
                self._active_lanes.append(lane_idx)

            return True

    def release_lane(self, lane_idx: int) -> None:
        """
        롱노트 종료 시 키 해제

        Args:
            lane_idx: 레인 인덱스
        """
        with self._lock:
            if lane_idx >= len(self._key_bindings):
                return
            if self._key_held.get(lane_idx, False):
                key = self._key_bindings[lane_idx]
                self._release_key(key)
                self._key_held[lane_idx] = False

            if lane_idx in self._active_lanes:
                self._active_lanes.remove(lane_idx)

    def _tap_key(self, key: str) -> None:
        """키를 한번 짧게 누르기 (내부용)"""
        try:
            if self._use_keyboard_lib:
                keyboard.press_and_release(key)
            elif pyautogui is not None:
                pyautogui.press(key)
        except Exception:
            pass

    def _press_key(self, key: str) -> None:
        """키를 누른 상태로 유지 (내부용)"""
        try:
            if self._use_keyboard_lib:
                keyboard.press(key)
            elif pyautogui is not None:
                pyautogui.keyDown(key)
        except Exception:
            pass

    def _release_key(self, key: str) -> None:
        """키를 해제 (내부용)"""
        try:
            if self._use_keyboard_lib:
                keyboard.release(key)
            elif pyautogui is not None:
                pyautogui.keyUp(key)
        except Exception:
            pass

    @property
    def active_lanes(self) -> List[int]:
        """현재 입력 중인 레인 목록"""
        with self._lock:
            return list(self._active_lanes)

    @property
    def key_bindings(self) -> List[str]:
        """현재 키 바인딩"""
        with self._lock:
            return list(self._key_bindings)
