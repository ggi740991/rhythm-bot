"""
ScreenCapture - mss 기반 고속 화면 캡처 모듈
lock 최소화로 최대 속도 확보
"""

import time
import numpy as np

try:
    import mss
except ImportError:
    mss = None


class ScreenCapture:
    """고속 화면 캡처"""

    def __init__(self):
        self._sct = None
        self._fps = 0.0
        self._frame_count = 0
        self._fps_timer = time.time()
        self._last_frame = None

    def start(self) -> None:
        if self._sct is None:
            self._sct = mss.mss()
        self._fps_timer = time.time()
        self._frame_count = 0

    def stop(self) -> None:
        if self._sct is not None:
            try:
                self._sct.close()
            except Exception:
                pass
            self._sct = None

    def capture(self, region: dict) -> np.ndarray:
        """지정된 영역을 캡처하여 BGR numpy 배열로 반환"""
        if self._sct is None:
            self._sct = mss.mss()

        monitor = {
            "left": region.get("x", 0),
            "top": region.get("y", 0),
            "width": region.get("width", 800),
            "height": region.get("height", 600),
        }

        try:
            screenshot = self._sct.grab(monitor)
            # BGRA -> BGR (numpy slice, no copy)
            frame = np.asarray(screenshot)[:, :, :3]
            self._last_frame = frame
            self._update_fps()
            return frame
        except Exception:
            return np.zeros(
                (region.get("height", 600), region.get("width", 800), 3),
                dtype=np.uint8,
            )

    def _update_fps(self) -> None:
        self._frame_count += 1
        elapsed = time.time() - self._fps_timer
        if elapsed >= 1.0:
            self._fps = self._frame_count / elapsed
            self._frame_count = 0
            self._fps_timer = time.time()

    @property
    def fps(self) -> float:
        return self._fps

    @property
    def last_frame(self) -> np.ndarray:
        return self._last_frame

    def get_screen_size(self) -> tuple:
        if self._sct is None:
            self._sct = mss.mss()
        mon = self._sct.monitors[0]
        return mon["width"], mon["height"]
