"""
NoteDetector - HSV 색상 기반 노트 감지 모듈
전체 프레임에서 contour를 먼저 찾고, x좌표 기반으로 레인에 배정
"""

import threading
from typing import List, Dict, Optional
import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None


class DetectedNote:
    """감지된 노트 정보"""
    __slots__ = ('lane', 'x', 'y', 'w', 'h', 'center_y', 'top', 'bottom', 'is_long')

    def __init__(self, lane: int, x: int, y: int, w: int, h: int, center_y: int):
        self.lane = lane
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self.center_y = center_y
        self.top = y
        self.bottom = y + h
        self.is_long = h > w * 1.2 and h > 30

    def __repr__(self) -> str:
        return f"Note(L{self.lane} y={self.center_y}{' LONG' if self.is_long else ''})"


class NoteDetector:
    """HSV 색상 기반 노트 감지기"""

    def __init__(self):
        self._lock = threading.Lock()
        self._detected_notes: List[DetectedNote] = []
        self._debug_frame: Optional[np.ndarray] = None
        self._kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)) if cv2 else None

    def detect(
        self,
        frame: np.ndarray,
        lane_count: int,
        hsv_lower: List[int],
        hsv_upper: List[int],
        min_note_size: int = 10,
        judge_line_y: int = 0,
        exclude_rect: Optional[dict] = None,
        build_debug: bool = False,
    ) -> List[DetectedNote]:
        """
        프레임에서 노트를 감지 (속도 최적화)
        build_debug=True일 때만 디버그 프레임 생성 (CPU 절약)
        """
        if frame is None or frame.size == 0:
            return []

        h, w = frame.shape[:2]

        # HSV 마스크 생성
        try:
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            mask = cv2.inRange(hsv, np.array(hsv_lower, np.uint8), np.array(hsv_upper, np.uint8))

            # 가벼운 노이즈 제거 (CLOSE만 - OPEN보다 빠름)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, self._kernel)

            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        except Exception:
            contours = []

        # 레인 경계
        lane_width = w / max(lane_count, 1)
        min_note_w = max(min_note_size, int(lane_width * 0.15))
        max_note_w = lane_width * 1.8

        # 콤보 제외 영역 미리 계산
        has_exclude = False
        ex, ey, ew, eh = 0, 0, 0, 0
        if exclude_rect:
            ex = exclude_rect.get("x", 0)
            ey = exclude_rect.get("y", 0)
            ew = exclude_rect.get("width", 0)
            eh = exclude_rect.get("height", 0)
            has_exclude = ew > 0 and eh > 0

        # contour → 노트 변환
        notes: List[DetectedNote] = []
        judge_cutoff = judge_line_y + 15 if judge_line_y > 0 else h

        for contour in contours:
            bx, by, bw, bh = cv2.boundingRect(contour)

            if bw < min_note_w or bh < 4 or bw > max_note_w:
                continue
            if by > judge_cutoff:
                continue
            if has_exclude:
                cx = bx + bw * 0.5
                cy = by + bh * 0.5
                if ex <= cx <= ex + ew and ey <= cy <= ey + eh:
                    continue

            # 레인 배정 (나눗셈으로 바로 계산)
            lane = int((bx + bw * 0.5) / lane_width)
            lane = max(0, min(lane, lane_count - 1))

            notes.append(DetectedNote(
                lane=lane, x=bx, y=by, w=bw, h=bh,
                center_y=by + bh // 2,
            ))

        # 디버그 프레임 (미리보기 열려있을 때만)
        if build_debug:
            debug_frame = frame.copy()
            # 레인 구분선
            for i in range(1, lane_count):
                lx = int(i * lane_width)
                cv2.line(debug_frame, (lx, 0), (lx, h), (0, 255, 255), 1)

            # 노트 박스
            for note in notes:
                color = (255, 165, 0) if note.is_long else (0, 255, 0)
                cv2.rectangle(debug_frame, (note.x, note.y),
                              (note.x + note.w, note.y + note.h), color, 2)

            # 판정선 + 판정 영역
            if judge_line_y > 0:
                ht = judge_line_y - 50
                hb = judge_line_y + 15
                overlay = debug_frame.copy()
                cv2.rectangle(overlay, (0, ht), (w, hb), (0, 100, 255), -1)
                cv2.addWeighted(overlay, 0.2, debug_frame, 0.8, 0, debug_frame)
                cv2.line(debug_frame, (0, judge_line_y), (w, judge_line_y), (0, 0, 255), 2)
                cv2.putText(debug_frame, "JUDGE", (5, judge_line_y - 5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)

            # 콤보 제외 영역
            if has_exclude:
                cv2.rectangle(debug_frame, (ex, ey), (ex + ew, ey + eh), (0, 165, 255), 2)

            with self._lock:
                self._debug_frame = debug_frame
        else:
            with self._lock:
                self._detected_notes = notes

        return notes

    @property
    def debug_frame(self) -> Optional[np.ndarray]:
        with self._lock:
            return self._debug_frame
