"""
NoteDetector - HSV 색상 기반 노트 감지 모듈
lane별 독립 감지, contour 기반 판별, 최소 크기 필터링
"""

import threading
from typing import List, Tuple, Dict, Optional
import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None


class DetectedNote:
    """감지된 노트 정보를 담는 클래스"""

    def __init__(self, lane: int, x: int, y: int, w: int, h: int, center_y: int):
        self.lane = lane        # 해당 레인 번호
        self.x = x              # 노트 바운딩 박스 x
        self.y = y              # 노트 바운딩 박스 y
        self.w = w              # 노트 너비
        self.h = h              # 노트 높이
        self.center_y = center_y  # 노트 중심 y좌표 (판정에 사용)

    def __repr__(self) -> str:
        return f"Note(lane={self.lane}, y={self.center_y})"


class NoteDetector:
    """HSV 색상 기반 노트 감지기"""

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
    ) -> List[DetectedNote]:
        """
        프레임에서 노트를 감지

        Args:
            frame: BGR 이미지
            lane_count: 레인 개수
            hsv_lower: HSV 하한값 [H, S, V]
            hsv_upper: HSV 상한값 [H, S, V]
            min_note_size: 최소 노트 크기 (픽셀)
            use_grayscale: 그레이스케일 최적화 사용 여부
            judge_line_y: 판정선 y좌표 (디버그용)
            note_capture_regions: 노트별 개별 캡처 영역 리스트
            rail_capture_regions: 레일별 개별 캡처 영역 리스트

        Returns:
            감지된 노트 리스트
        """
        if frame is None or frame.size == 0:
            return []

        h, w = frame.shape[:2]
        notes: List[DetectedNote] = []
        debug_frame = frame.copy() if not use_grayscale else cv2.cvtColor(
            cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR
        )

        # 레일별 개별 캡처 영역이 설정되어 있으면 해당 영역만 사용
        if rail_capture_regions and len(rail_capture_regions) == lane_count:
            for lane_idx, region in enumerate(rail_capture_regions):
                rx = max(0, region.get("x", 0))
                ry = max(0, region.get("y", 0))
                rw = min(region.get("width", w // lane_count), w - rx)
                rh = min(region.get("height", h), h - ry)
                lane_frame = frame[ry:ry + rh, rx:rx + rw]
                lane_notes = self._detect_in_region(
                    lane_frame, lane_idx, hsv_lower, hsv_upper,
                    min_note_size, rx, ry,
                    note_capture_regions
                )
                notes.extend(lane_notes)
                # 디버그 프레임에 레일 영역 표시
                cv2.rectangle(debug_frame, (rx, ry), (rx + rw, ry + rh),
                              (255, 255, 0), 1)
        else:
            # 기본: 프레임을 레인 개수로 균등 분할
            lane_width = w // max(lane_count, 1)
            for lane_idx in range(lane_count):
                x_start = lane_idx * lane_width
                x_end = x_start + lane_width if lane_idx < lane_count - 1 else w
                lane_frame = frame[:, x_start:x_end]
                lane_notes = self._detect_in_region(
                    lane_frame, lane_idx, hsv_lower, hsv_upper,
                    min_note_size, x_start, 0,
                    note_capture_regions
                )
                notes.extend(lane_notes)
                # 디버그 프레임에 레인 구분선 표시
                cv2.line(debug_frame, (x_start, 0), (x_start, h), (0, 255, 255), 1)

        # 디버그 프레임에 감지된 노트와 판정선 표시
        for note in notes:
            color = (0, 255, 0)  # 기본: 녹색
            cv2.rectangle(debug_frame, (note.x, note.y),
                          (note.x + note.w, note.y + note.h), color, 2)
            cv2.putText(debug_frame, f"L{note.lane}",
                        (note.x, note.y - 5), cv2.FONT_HERSHEY_SIMPLEX,
                        0.4, color, 1)

        # 판정선 표시
        if judge_line_y > 0:
            cv2.line(debug_frame, (0, judge_line_y), (w, judge_line_y),
                     (0, 0, 255), 2)
            cv2.putText(debug_frame, "JUDGE LINE",
                        (5, judge_line_y - 5), cv2.FONT_HERSHEY_SIMPLEX,
                        0.5, (0, 0, 255), 1)

        with self._lock:
            self._detected_notes = notes
            self._debug_frame = debug_frame

        return notes

    def _detect_in_region(
        self,
        region_frame: np.ndarray,
        lane_idx: int,
        hsv_lower: List[int],
        hsv_upper: List[int],
        min_note_size: int,
        x_offset: int = 0,
        y_offset: int = 0,
        note_capture_regions: Optional[List[dict]] = None,
    ) -> List[DetectedNote]:
        """
        특정 영역에서 노트 감지 (내부용)

        Args:
            region_frame: 레인 영역 이미지
            lane_idx: 레인 인덱스
            hsv_lower/upper: HSV 범위
            min_note_size: 최소 크기
            x_offset, y_offset: 전체 프레임 기준 오프셋
            note_capture_regions: 노트별 개별 캡처 영역

        Returns:
            해당 영역에서 감지된 노트 리스트
        """
        if region_frame is None or region_frame.size == 0:
            return []

        notes: List[DetectedNote] = []

        # 노트별 개별 캡처 영역이 있으면 해당 영역만 처리
        if note_capture_regions:
            for nr in note_capture_regions:
                if nr.get("lane", -1) == lane_idx:
                    nx = nr.get("x", 0)
                    ny = nr.get("y", 0)
                    nw = nr.get("width", region_frame.shape[1])
                    nh = nr.get("height", region_frame.shape[0])
                    rh, rw = region_frame.shape[:2]
                    nx = max(0, min(nx, rw))
                    ny = max(0, min(ny, rh))
                    nw = min(nw, rw - nx)
                    nh = min(nh, rh - ny)
                    sub = region_frame[ny:ny + nh, nx:nx + nw]
                    sub_notes = self._find_notes_hsv(
                        sub, lane_idx, hsv_lower, hsv_upper,
                        min_note_size, x_offset + nx, y_offset + ny
                    )
                    notes.extend(sub_notes)
            if notes or note_capture_regions:
                return notes

        # 전체 레인 영역에서 노트 감지
        return self._find_notes_hsv(
            region_frame, lane_idx, hsv_lower, hsv_upper,
            min_note_size, x_offset, y_offset
        )

    def _find_notes_hsv(
        self,
        frame: np.ndarray,
        lane_idx: int,
        hsv_lower: List[int],
        hsv_upper: List[int],
        min_note_size: int,
        x_offset: int,
        y_offset: int,
    ) -> List[DetectedNote]:
        """
        HSV 색상 범위와 contour를 사용하여 노트 찾기

        Args:
            frame: 대상 이미지 (BGR)
            lane_idx: 레인 번호
            hsv_lower/upper: HSV 범위
            min_note_size: 최소 크기 필터
            x_offset, y_offset: 좌표 오프셋

        Returns:
            감지된 노트 리스트
        """
        notes: List[DetectedNote] = []

        try:
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            lower = np.array(hsv_lower, dtype=np.uint8)
            upper = np.array(hsv_upper, dtype=np.uint8)
            mask = cv2.inRange(hsv, lower, upper)

            # 모폴로지 연산으로 노이즈 제거
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

            contours, _ = cv2.findContours(
                mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )

            for contour in contours:
                x, y, w, h = cv2.boundingRect(contour)
                # 최소 크기 필터링
                if w >= min_note_size and h >= min_note_size // 2:
                    center_y = y + h // 2
                    note = DetectedNote(
                        lane=lane_idx,
                        x=x + x_offset,
                        y=y + y_offset,
                        w=w,
                        h=h,
                        center_y=center_y + y_offset,
                    )
                    notes.append(note)
        except Exception:
            pass

        return notes

    @property
    def debug_frame(self) -> Optional[np.ndarray]:
        """디버그 프레임 반환 (감지 결과 시각화)"""
        with self._lock:
            return self._debug_frame

    @property
    def detected_count(self) -> int:
        """현재 감지된 노트 수"""
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
        판정선 근처의 노트를 판정 등급별로 분류

        Args:
            notes: 감지된 노트 리스트
            judge_line_y: 판정선 y좌표
            perfect_range: perfect 판정 범위 (픽셀)
            great_range: great 판정 범위
            good_range: good 판정 범위

        Returns:
            {"perfect": [...], "great": [...], "good": [...]} 형태의 딕셔너리
        """
        result: Dict[str, List[DetectedNote]] = {
            "perfect": [],
            "great": [],
            "good": [],
        }

        for note in notes:
            distance = abs(note.center_y - judge_line_y)
            if distance <= perfect_range:
                result["perfect"].append(note)
            elif distance <= great_range:
                result["great"].append(note)
            elif distance <= good_range:
                result["good"].append(note)

        return result
