"""
ScreenCapture - mss 기반 고속 화면 캡처 모듈
ROI(관심 영역)만 캡처하여 성능 최적화
"""

import time
import threading
import numpy as np

try:
    import mss
    import mss.tools
except ImportError:
    mss = None

try:
    import cv2
except ImportError:
    cv2 = None


class ScreenCapture:
    """고속 화면 캡처 - mss 라이브러리 사용"""

    def __init__(self):
        self._sct = None
        self._lock = threading.Lock()
        self._fps = 0.0
        self._frame_count = 0
        self._fps_timer = time.time()
        self._last_frame = None
        self._running = False

    def start(self) -> None:
        """캡처 세션 시작"""
        with self._lock:
            if self._sct is None:
                self._sct = mss.mss()
            self._running = True
            self._fps_timer = time.time()
            self._frame_count = 0

    def stop(self) -> None:
        """캡처 세션 종료"""
        with self._lock:
            self._running = False
            if self._sct is not None:
                try:
                    self._sct.close()
                except Exception:
                    pass
                self._sct = None

    def capture(self, region: dict) -> np.ndarray:
        """
        지정된 영역을 캡처하여 numpy 배열(BGR)로 반환

        Args:
            region: {"x": int, "y": int, "width": int, "height": int}

        Returns:
            np.ndarray: BGR 이미지 (OpenCV 형식)
        """
        with self._lock:
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
                frame = np.array(screenshot, dtype=np.uint8)
                # BGRA -> BGR 변환
                frame = frame[:, :, :3]
                self._last_frame = frame
                self._update_fps()
                return frame
            except Exception:
                # 캡처 실패 시 빈 프레임 반환
                return np.zeros(
                    (region.get("height", 600), region.get("width", 800), 3),
                    dtype=np.uint8,
                )

    def capture_sub_region(self, base_region: dict, sub_region: dict) -> np.ndarray:
        """
        기본 캡처 영역 내에서 하위 영역만 추출 (노트/레일 개별 캡처용)

        Args:
            base_region: 기본 캡처 영역
            sub_region: 하위 영역 (기본 영역 내 상대 좌표)

        Returns:
            np.ndarray: BGR 이미지
        """
        abs_region = {
            "x": base_region["x"] + sub_region.get("x", 0),
            "y": base_region["y"] + sub_region.get("y", 0),
            "width": sub_region.get("width", 100),
            "height": sub_region.get("height", 100),
        }
        return self.capture(abs_region)

    def _update_fps(self) -> None:
        """FPS 계산 (내부용)"""
        self._frame_count += 1
        elapsed = time.time() - self._fps_timer
        if elapsed >= 1.0:
            self._fps = self._frame_count / elapsed
            self._frame_count = 0
            self._fps_timer = time.time()

    @property
    def fps(self) -> float:
        """현재 FPS 반환"""
        return self._fps

    @property
    def last_frame(self) -> np.ndarray:
        """마지막 캡처 프레임 반환"""
        return self._last_frame

    def get_screen_size(self) -> tuple:
        """전체 화면 크기 반환"""
        with self._lock:
            if self._sct is None:
                self._sct = mss.mss()
            mon = self._sct.monitors[0]
            return mon["width"], mon["height"]
