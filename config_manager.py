"""
ConfigManager - JSON 기반 설정 관리 모듈
모든 설정값을 JSON 파일로 저장/로드하며, GUI에서 변경 가능하도록 설계됨
"""

import json
import os
import threading
from typing import Any, Dict


# 기본 설정값 정의
DEFAULT_CONFIG: Dict[str, Any] = {
    # 캡처 영역 설정 (x, y, width, height)
    "capture_region": {"x": 0, "y": 0, "width": 800, "height": 600},
    # 레인 개수
    "lane_count": 4,
    # 레인별 키 바인딩
    "key_bindings": ["d", "f", "j", "k"],
    # HSV 범위 설정 (노트 색상 감지용)
    "hsv_lower": [0, 0, 200],
    "hsv_upper": [180, 50, 255],
    # 판정선 위치 (캡처 영역 내 상대 위치, 0.0~1.0 비율)
    "judge_line_ratio": 0.85,
    # 판정 범위 (픽셀 단위)
    "perfect_range": 10,
    "great_range": 25,
    "good_range": 40,
    # 입력 딜레이 (ms)
    "input_delay_ms": 0,
    # debounce 시간 (ms)
    "debounce_ms": 50,
    # 노트 최소 크기 (픽셀)
    "min_note_size": 10,
    # 디버그 모드
    "debug_mode": False,
    # 그레이스케일 최적화
    "use_grayscale": False,
    # 프레임 스킵
    "frame_skip": 0,
    # 오버레이 모드
    "overlay_mode": False,
    # 항상 위 창
    "always_on_top": False,
    # 다크모드
    "dark_mode": True,
    # 투명도 (오버레이용)
    "overlay_alpha": 0.7,
    # 노트 속도 보정 계수
    "speed_correction": 1.0,
    # 롱노트 지원
    "long_note_enabled": True,
    # 노트별 캡처 설정 (개별 노트/레일 캡처용)
    "note_capture_regions": [],
    "rail_capture_regions": [],
    # 자동 캘리브레이션 사용
    "auto_calibration": False,
    # 로그 출력
    "show_log": True,
}

# 설정 파일 경로
CONFIG_FILE = "rhythm_bot_config.json"


class ConfigManager:
    """JSON 기반 설정 관리자 - 스레드 안전하게 설정을 읽고 쓸 수 있음"""

    def __init__(self, config_path: str = CONFIG_FILE):
        self._config_path = config_path
        self._config: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self._load()

    def _load(self) -> None:
        """설정 파일에서 값을 로드, 없으면 기본값 사용"""
        with self._lock:
            self._config = dict(DEFAULT_CONFIG)
            if os.path.exists(self._config_path):
                try:
                    with open(self._config_path, "r", encoding="utf-8") as f:
                        saved = json.load(f)
                    self._config.update(saved)
                except (json.JSONDecodeError, IOError):
                    pass  # 파일 손상 시 기본값 유지

    def save(self) -> None:
        """현재 설정을 JSON 파일로 저장"""
        with self._lock:
            try:
                with open(self._config_path, "w", encoding="utf-8") as f:
                    json.dump(self._config, f, indent=2, ensure_ascii=False)
            except IOError:
                pass

    def get(self, key: str, default: Any = None) -> Any:
        """설정값 읽기"""
        with self._lock:
            return self._config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """설정값 변경"""
        with self._lock:
            self._config[key] = value

    def get_all(self) -> Dict[str, Any]:
        """전체 설정 사본 반환"""
        with self._lock:
            return dict(self._config)

    def reset(self) -> None:
        """기본값으로 초기화"""
        with self._lock:
            self._config = dict(DEFAULT_CONFIG)
