"""
NoteDetector - HSV 색상 기반 노트 감지 모듈
전체 프레임에서 contour를 먼저 찾고, x좌표 기반으로 레인에 배정
롱노트: 바운딩 박스가 판정선을 걸치는지로 판단
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

    def __init__(self, lane: int, x: int, y: int, w: int, h: int, center_y: int):
        self.lane = lane
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self.center_y = center_y
        # 바운딩 박스 상하단
        self.top = y
        self.bottom = y + h
        # 롱노트 여부 (높이가 넓이의 1.5배 이상이면 롱노트)
        self.is_long = h > w * 1.5 and h > 40

    def crosses_line(self, line_y: int, margin: int = 0) -> bool:
        """이 노트의 바운딩 박스가 판정선을 걸치는지 확인"""
        return self.top - margin <= line_y <= self.bottom + margin

    def __repr__(self) -> str:
        long_str = " LONG" if self.is_long else ""
        return f"Note(L{self.lane} y={self.center_y}{long_str})"


class NoteDetector:
    """HSV 색상 기반 노트 감지기 - 전체 프레임 감지 후 레인 배정"""

    def __init__(self):
        self._lock = threading.Lock()
        self._detected_notes: List[DetectedNote] = []
        self._debug_frame: Optional[np.ndarray] = None

    def detect(
        self,
        frame: np.ndarray,
        lane_count: int,
        hsv_lower: List[int],
        hsv_upper: List[int],
        min_note_size: int = 10,
        use_grayscale: bool = False,
        judge_line_y: int = 0,
        note_capture_regions: Optional[List[dict]] = None,
        rail_capture_regions: Optional[List[dict]] = None,
        ignore_below_judge: bool = True,
    ) -> List[DetectedNote]:
        """
        프레임에서 노트를 감지
        방식: 전체 프레임에서 HSV 마스크 → contour 검출 → x좌표로 레인 배정
        """
        if frame is None or frame.size == 0:
            return []

        h, w = frame.shape[:2]
        debug_frame = frame.copy()

        # 전체 프레임에서 HSV 마스크 생성
        try:
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            lower = np.array(hsv_lower, dtype=np.uint8)
            upper = np.array(hsv_upper, dtype=np.uint8)
            mask = cv2.inRange(hsv, lower, upper)

            # 노이즈 제거
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

            # 모든 contour 검출
            contours, _ = cv2.findContours(
                mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
        except Exception:
            contours = []

        # 레인 경계 계산
        lane_width = w / max(lane_count, 1)
        lane_boundaries = []
        for i in range(lane_count):
            x_start = i * lane_width
            x_end = (i + 1) * lane_width
            lane_boundaries.append((x_start, x_end))

        # contour → 노트 변환, x 중심으로 레인 배정
        notes: List[DetectedNote] = []
        for contour in contours:
            bx, by, bw, bh = cv2.boundingRect(contour)

            # 최소 크기 필터
            if bw < min_note_size:
                continue
            if bh < 3:
                continue

            # 판정선 아래에 있는 노트는 무시 (콤보/이펙트 필터)
            note_bottom = by + bh
            if ignore_below_judge and judge_line_y > 0:
                # 노트 전체가 판정선 아래면 무시 (콤보, 이펙트 등)
                if by > judge_line_y + 10:
                    continue

            # 노트의 x 중심으로 레인 결정
            note_center_x = bx + bw / 2
            assigned_lane = -1
            for lane_idx, (lx_start, lx_end) in enumerate(lane_boundaries):
                if lx_start <= note_center_x < lx_end:
                    assigned_lane = lane_idx
                    break

            # 어느 레인에도 안 들어가면 가장 가까운 레인에 배정
            if assigned_lane < 0:
                min_dist = float("inf")
                for lane_idx, (lx_start, lx_end) in enumerate(lane_boundaries):
                    lane_center = (lx_start + lx_end) / 2
                    dist = abs(note_center_x - lane_center)
                    if dist < min_dist:
                        min_dist = dist
                        assigned_lane = lane_idx

            center_y = by + bh // 2
            note = DetectedNote(
                lane=assigned_lane,
                x=bx, y=by, w=bw, h=bh,
                center_y=center_y,
            )
            notes.append(note)

        # 판정선 아래 영역 어둡게 표시 (필터링된 영역 시각화)
        if judge_line_y > 0:
            overlay = debug_frame.copy()
            cv2.rectangle(overlay, (0, judge_line_y + 10), (w, h), (0, 0, 0), -1)
            cv2.addWeighted(overlay, 0.4, debug_frame, 0.6, 0, debug_frame)

        # 디버그 프레임 그리기
        # 레인 구분선
        for i in range(1, lane_count):
            lx = int(i * lane_width)
            cv2.line(debug_frame, (lx, 0), (lx, h), (0, 255, 255), 1)

        # 레인 번호 표시
        for i in range(lane_count):
            lx = int(i * lane_width + lane_width / 2) - 5
            cv2.putText(debug_frame, f"L{i}", (lx, 15),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)

        # 감지된 노트 박스
        for note in notes:
            if note.is_long:
                color = (255, 165, 0)  # 주황: 롱노트
            else:
                color = (0, 255, 0)  # 초록: 일반 노트
            cv2.rectangle(debug_frame, (note.x, note.y),
                          (note.x + note.w, note.y + note.h), color, 2)
            label = f"L{note.lane}"
            if note.is_long:
                label += " LONG"
            cv2.putText(debug_frame, label, (note.x, note.y - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, color, 1)

        # 판정선
        if judge_line_y > 0:
            cv2.line(debug_frame, (0, judge_line_y), (w, judge_line_y),
                     (0, 0, 255), 2)
            cv2.putText(debug_frame, "JUDGE", (5, judge_line_y - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)

        with self._lock:
            self._detected_notes = notes
            self._debug_frame = debug_frame

        return notes

    @property
    def debug_frame(self) -> Optional[np.ndarray]:
        with self._lock:
            return self._debug_frame

    @property
    def detected_count(self) -> int:
        with self._lock:
            return len(self._detected_notes)

    def get_notes_near_judge(
        self,
        notes: List[DetectedNote],
        judge_line_y: int,
        perfect_range: int,
        great_range: int,
        good_range: int,
    ) -> Dict[str, List[DetectedNote]]:
        """
        판정선 근처 노트를 등급별로 분류
        롱노트는 바운딩 박스가 판정선을 걸치면 바로 판정
        """
        result: Dict[str, List[DetectedNote]] = {
            "perfect": [],
            "great": [],
            "good": [],
        }

        for note in notes:
            if note.is_long:
                # 롱노트: 바운딩 박스가 판정선을 걸치면 perfect
                if note.crosses_line(judge_line_y, margin=good_range):
                    result["perfect"].append(note)
            else:
                # 일반 노트: center_y 기준 거리
                distance = abs(note.center_y - judge_line_y)
                if distance <= perfect_range:
                    result["perfect"].append(note)
                elif distance <= great_range:
                    result["great"].append(note)
                elif distance <= good_range:
                    result["good"].append(note)

        return result

    def get_lanes_with_long_notes_at_judge(
        self,
        notes: List[DetectedNote],
        judge_line_y: int,
        margin: int = 10,
    ) -> set:
        """
        판정선을 걸치는 롱노트가 있는 레인 목록 반환
        (키를 계속 누르고 있어야 하는 레인)
        """
        lanes = set()
        for note in notes:
            if note.is_long and note.crosses_line(judge_line_y, margin=margin):
                lanes.add(note.lane)
        return lanes
