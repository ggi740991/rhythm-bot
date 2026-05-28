"""
RhythmBotGUI - tkinter 기반 메인 GUI 모듈
모든 설정을 GUI에서 조정 가능, 실시간 미리보기, 다크모드, 오버레이 지원
"""

import time
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional
import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None

try:
    from PIL import Image, ImageTk
except ImportError:
    Image = None
    ImageTk = None

from config_manager import ConfigManager
from screen_capture import ScreenCapture
from note_detector import NoteDetector, DetectedNote
from input_manager import InputManager


# 다크모드 색상 테마
DARK_THEME = {
    "bg": "#1e1e1e",
    "fg": "#e0e0e0",
    "accent": "#4fc3f7",
    "button_bg": "#333333",
    "button_active": "#555555",
    "entry_bg": "#2a2a2a",
    "frame_bg": "#252525",
    "success": "#66bb6a",
    "warning": "#ffa726",
    "error": "#ef5350",
}

LIGHT_THEME = {
    "bg": "#f5f5f5",
    "fg": "#212121",
    "accent": "#1976d2",
    "button_bg": "#e0e0e0",
    "button_active": "#bdbdbd",
    "entry_bg": "#ffffff",
    "frame_bg": "#eeeeee",
    "success": "#43a047",
    "warning": "#fb8c00",
    "error": "#e53935",
}


class RhythmBotGUI:
    """리듬게임 봇 메인 GUI"""

    def __init__(self):
        # 핵심 모듈 초기화
        self.config = ConfigManager()
        self.capture = ScreenCapture()
        self.detector = NoteDetector()
        self.input_mgr = InputManager()

        # 상태 변수
        self._running = False
        self._bot_thread: Optional[threading.Thread] = None
        self._preview_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._fps_display = 0.0
        self._note_count = 0
        self._status = "대기 중"
        self._log_messages = []

        # 테마 설정
        self._theme = DARK_THEME if self.config.get("dark_mode") else LIGHT_THEME

        # GUI 생성
        self.root = tk.Tk()
        self.root.title("리듬게임 자동 봇 v1.0")
        self.root.geometry("1100x750")
        self.root.minsize(900, 600)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # 항상 위 창 설정
        if self.config.get("always_on_top"):
            self.root.attributes("-topmost", True)

        # ESC 긴급 종료 바인딩
        self.root.bind("<Escape>", lambda e: self._emergency_stop())

        # tkinter 변수
        self._init_tk_vars()

        # GUI 위젯 생성
        self._build_gui()

        # 테마 적용
        self._apply_theme()

        # 설정값을 GUI에 로드
        self._load_config_to_gui()

    def _init_tk_vars(self) -> None:
        """tkinter 변수 초기화"""
        cfg = self.config

        # 캡처 영역
        region = cfg.get("capture_region", {})
        self.var_cap_x = tk.IntVar(value=region.get("x", 0))
        self.var_cap_y = tk.IntVar(value=region.get("y", 0))
        self.var_cap_w = tk.IntVar(value=region.get("width", 800))
        self.var_cap_h = tk.IntVar(value=region.get("height", 600))

        # 레인 설정
        self.var_lane_count = tk.IntVar(value=cfg.get("lane_count", 4))

        # HSV 슬라이더
        hsv_l = cfg.get("hsv_lower", [0, 0, 200])
        hsv_u = cfg.get("hsv_upper", [180, 50, 255])
        self.var_h_low = tk.IntVar(value=hsv_l[0])
        self.var_s_low = tk.IntVar(value=hsv_l[1])
        self.var_v_low = tk.IntVar(value=hsv_l[2])
        self.var_h_high = tk.IntVar(value=hsv_u[0])
        self.var_s_high = tk.IntVar(value=hsv_u[1])
        self.var_v_high = tk.IntVar(value=hsv_u[2])

        # 판정선 위치
        self.var_judge_ratio = tk.DoubleVar(value=cfg.get("judge_line_ratio", 0.85))

        # 판정 범위
        self.var_perfect = tk.IntVar(value=cfg.get("perfect_range", 10))
        self.var_great = tk.IntVar(value=cfg.get("great_range", 25))
        self.var_good = tk.IntVar(value=cfg.get("good_range", 40))

        # 입력 딜레이
        self.var_delay = tk.IntVar(value=cfg.get("input_delay_ms", 0))
        self.var_debounce = tk.IntVar(value=cfg.get("debounce_ms", 50))

        # 노트 크기
        self.var_min_note = tk.IntVar(value=cfg.get("min_note_size", 10))

        # 옵션
        self.var_debug = tk.BooleanVar(value=cfg.get("debug_mode", False))
        self.var_grayscale = tk.BooleanVar(value=cfg.get("use_grayscale", False))
        self.var_frame_skip = tk.IntVar(value=cfg.get("frame_skip", 0))
        self.var_overlay = tk.BooleanVar(value=cfg.get("overlay_mode", False))
        self.var_always_top = tk.BooleanVar(value=cfg.get("always_on_top", False))
        self.var_dark_mode = tk.BooleanVar(value=cfg.get("dark_mode", True))
        self.var_long_note = tk.BooleanVar(value=cfg.get("long_note_enabled", True))
        self.var_auto_cal = tk.BooleanVar(value=cfg.get("auto_calibration", False))
        self.var_show_log = tk.BooleanVar(value=cfg.get("show_log", True))
        self.var_speed_corr = tk.DoubleVar(value=cfg.get("speed_correction", 1.0))

        # 키 바인딩 (문자열)
        bindings = cfg.get("key_bindings", ["d", "f", "j", "k"])
        self.var_keys = tk.StringVar(value=",".join(bindings))

    def _build_gui(self) -> None:
        """GUI 위젯 구성"""
        # 메인 프레임을 좌우로 분할
        main_frame = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, sashwidth=4)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 왼쪽: 설정 패널 (스크롤 가능)
        left_container = tk.Frame(main_frame)
        main_frame.add(left_container, width=480)

        canvas = tk.Canvas(left_container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(left_container, orient=tk.VERTICAL, command=canvas.yview)
        self.settings_frame = tk.Frame(canvas)

        self.settings_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self.settings_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 마우스 휠 스크롤
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        canvas.bind_all("<Button-4>", lambda e: canvas.yview_scroll(-1, "units"))
        canvas.bind_all("<Button-5>", lambda e: canvas.yview_scroll(1, "units"))

        # 오른쪽: 미리보기 + 로그
        right_frame = tk.Frame(main_frame)
        main_frame.add(right_frame)

        self._build_control_buttons()
        self._build_status_section()
        self._build_capture_settings()
        self._build_lane_settings()
        self._build_hsv_settings()
        self._build_judge_settings()
        self._build_input_settings()
        self._build_options()
        self._build_note_rail_capture()
        self._build_preview(right_frame)
        self._build_log(right_frame)

    def _make_label_frame(self, parent, text: str) -> tk.LabelFrame:
        """통일된 스타일의 LabelFrame 생성"""
        lf = tk.LabelFrame(parent, text=text, padx=8, pady=5)
        lf.pack(fill=tk.X, padx=5, pady=3)
        return lf

    def _build_control_buttons(self) -> None:
        """시작/정지/긴급종료 버튼"""
        frame = self._make_label_frame(self.settings_frame, "제어")

        btn_frame = tk.Frame(frame)
        btn_frame.pack(fill=tk.X)

        self.btn_start = tk.Button(
            btn_frame, text="▶ 시작", command=self._start_bot,
            width=10, height=2
        )
        self.btn_start.pack(side=tk.LEFT, padx=3, pady=3, expand=True, fill=tk.X)

        self.btn_stop = tk.Button(
            btn_frame, text="■ 정지", command=self._stop_bot,
            width=10, height=2, state=tk.DISABLED
        )
        self.btn_stop.pack(side=tk.LEFT, padx=3, pady=3, expand=True, fill=tk.X)

        self.btn_emergency = tk.Button(
            btn_frame, text="⚠ 긴급 종료 (ESC)", command=self._emergency_stop,
            width=14, height=2
        )
        self.btn_emergency.pack(side=tk.LEFT, padx=3, pady=3, expand=True, fill=tk.X)

        # 설정 저장/리셋
        btn_frame2 = tk.Frame(frame)
        btn_frame2.pack(fill=tk.X)

        tk.Button(
            btn_frame2, text="설정 저장", command=self._save_config, width=12
        ).pack(side=tk.LEFT, padx=3, pady=3, expand=True, fill=tk.X)

        tk.Button(
            btn_frame2, text="설정 초기화", command=self._reset_config, width=12
        ).pack(side=tk.LEFT, padx=3, pady=3, expand=True, fill=tk.X)

    def _build_status_section(self) -> None:
        """상태 표시 영역"""
        frame = self._make_label_frame(self.settings_frame, "상태")

        self.lbl_status = tk.Label(frame, text="상태: 대기 중", anchor="w")
        self.lbl_status.pack(fill=tk.X)

        self.lbl_fps = tk.Label(frame, text="FPS: 0", anchor="w")
        self.lbl_fps.pack(fill=tk.X)

        self.lbl_notes = tk.Label(frame, text="감지 노트: 0", anchor="w")
        self.lbl_notes.pack(fill=tk.X)

        self.lbl_active_keys = tk.Label(frame, text="입력 키: -", anchor="w")
        self.lbl_active_keys.pack(fill=tk.X)

    def _build_capture_settings(self) -> None:
        """캡처 영역 설정"""
        frame = self._make_label_frame(self.settings_frame, "캡처 영역")

        grid = tk.Frame(frame)
        grid.pack(fill=tk.X)

        labels = ["X:", "Y:", "너비:", "높이:"]
        vars_ = [self.var_cap_x, self.var_cap_y, self.var_cap_w, self.var_cap_h]

        for i, (label, var) in enumerate(zip(labels, vars_)):
            row, col = divmod(i, 2)
            tk.Label(grid, text=label, width=5).grid(row=row, column=col * 2, sticky="e", padx=2)
            tk.Entry(grid, textvariable=var, width=8).grid(row=row, column=col * 2 + 1, padx=2, pady=2)

        # 화면 영역 선택 버튼
        tk.Button(
            frame, text="화면에서 영역 선택", command=self._select_capture_region
        ).pack(pady=3)

    def _build_lane_settings(self) -> None:
        """레인 및 키 설정"""
        frame = self._make_label_frame(self.settings_frame, "레인 설정")

        row1 = tk.Frame(frame)
        row1.pack(fill=tk.X, pady=2)
        tk.Label(row1, text="레인 개수:").pack(side=tk.LEFT)
        tk.Spinbox(row1, from_=1, to=10, textvariable=self.var_lane_count, width=5).pack(side=tk.LEFT, padx=5)

        row2 = tk.Frame(frame)
        row2.pack(fill=tk.X, pady=2)
        tk.Label(row2, text="키 바인딩 (쉼표 구분):").pack(side=tk.LEFT)
        tk.Entry(row2, textvariable=self.var_keys, width=20).pack(side=tk.LEFT, padx=5)

    def _build_hsv_settings(self) -> None:
        """HSV 색상 슬라이더"""
        frame = self._make_label_frame(self.settings_frame, "HSV 노트 색상 범위")

        sliders = [
            ("H 최소", self.var_h_low, 0, 180),
            ("S 최소", self.var_s_low, 0, 255),
            ("V 최소", self.var_v_low, 0, 255),
            ("H 최대", self.var_h_high, 0, 180),
            ("S 최대", self.var_s_high, 0, 255),
            ("V 최대", self.var_v_high, 0, 255),
        ]

        for label, var, from_, to_ in sliders:
            row = tk.Frame(frame)
            row.pack(fill=tk.X, pady=1)
            tk.Label(row, text=label, width=7, anchor="e").pack(side=tk.LEFT)
            tk.Scale(row, variable=var, from_=from_, to=to_,
                     orient=tk.HORIZONTAL, length=200).pack(side=tk.LEFT, fill=tk.X, expand=True)

    def _build_judge_settings(self) -> None:
        """판정 설정"""
        frame = self._make_label_frame(self.settings_frame, "판정 설정")

        # 판정선 위치
        row1 = tk.Frame(frame)
        row1.pack(fill=tk.X, pady=2)
        tk.Label(row1, text="판정선 위치:").pack(side=tk.LEFT)
        tk.Scale(row1, variable=self.var_judge_ratio, from_=0.0, to=1.0,
                 resolution=0.01, orient=tk.HORIZONTAL, length=200).pack(
            side=tk.LEFT, fill=tk.X, expand=True)

        # 판정 범위
        ranges = [
            ("Perfect 범위:", self.var_perfect),
            ("Great 범위:", self.var_great),
            ("Good 범위:", self.var_good),
        ]
        for label, var in ranges:
            row = tk.Frame(frame)
            row.pack(fill=tk.X, pady=1)
            tk.Label(row, text=label, width=12, anchor="e").pack(side=tk.LEFT)
            tk.Scale(row, variable=var, from_=1, to=100,
                     orient=tk.HORIZONTAL, length=200).pack(
                side=tk.LEFT, fill=tk.X, expand=True)

        # 속도 보정
        row_speed = tk.Frame(frame)
        row_speed.pack(fill=tk.X, pady=1)
        tk.Label(row_speed, text="속도 보정:", width=12, anchor="e").pack(side=tk.LEFT)
        tk.Scale(row_speed, variable=self.var_speed_corr, from_=0.5, to=2.0,
                 resolution=0.05, orient=tk.HORIZONTAL, length=200).pack(
            side=tk.LEFT, fill=tk.X, expand=True)

    def _build_input_settings(self) -> None:
        """입력 설정"""
        frame = self._make_label_frame(self.settings_frame, "입력 설정")

        row1 = tk.Frame(frame)
        row1.pack(fill=tk.X, pady=2)
        tk.Label(row1, text="입력 딜레이(ms):").pack(side=tk.LEFT)
        tk.Spinbox(row1, from_=0, to=500, textvariable=self.var_delay, width=6).pack(side=tk.LEFT, padx=5)

        row2 = tk.Frame(frame)
        row2.pack(fill=tk.X, pady=2)
        tk.Label(row2, text="Debounce(ms):").pack(side=tk.LEFT)
        tk.Spinbox(row2, from_=0, to=500, textvariable=self.var_debounce, width=6).pack(side=tk.LEFT, padx=5)

        row3 = tk.Frame(frame)
        row3.pack(fill=tk.X, pady=2)
        tk.Label(row3, text="최소 노트 크기(px):").pack(side=tk.LEFT)
        tk.Spinbox(row3, from_=1, to=200, textvariable=self.var_min_note, width=6).pack(side=tk.LEFT, padx=5)

    def _build_options(self) -> None:
        """추가 옵션"""
        frame = self._make_label_frame(self.settings_frame, "옵션")

        checks = [
            ("디버그 모드", self.var_debug),
            ("그레이스케일", self.var_grayscale),
            ("오버레이 모드", self.var_overlay),
            ("항상 위", self.var_always_top),
            ("다크모드", self.var_dark_mode),
            ("롱노트 지원", self.var_long_note),
            ("자동 캘리브레이션", self.var_auto_cal),
            ("로그 표시", self.var_show_log),
        ]

        grid = tk.Frame(frame)
        grid.pack(fill=tk.X)

        for i, (text, var) in enumerate(checks):
            row, col = divmod(i, 2)
            cb = tk.Checkbutton(grid, text=text, variable=var)
            cb.grid(row=row, column=col, sticky="w", padx=5, pady=1)

        # 항상 위 토글
        self.var_always_top.trace_add("write", self._toggle_always_on_top)
        # 다크모드 토글
        self.var_dark_mode.trace_add("write", self._toggle_dark_mode)

        # 프레임 스킵
        row_fs = tk.Frame(frame)
        row_fs.pack(fill=tk.X, pady=2)
        tk.Label(row_fs, text="프레임 스킵:").pack(side=tk.LEFT)
        tk.Spinbox(row_fs, from_=0, to=10, textvariable=self.var_frame_skip, width=5).pack(side=tk.LEFT, padx=5)

    def _build_note_rail_capture(self) -> None:
        """노트/레일 개별 캡처 설정"""
        frame = self._make_label_frame(self.settings_frame, "노트/레일 개별 캡처")

        tk.Label(frame, text="각 레인별 독립 캡처 영역을 설정할 수 있습니다.",
                 wraplength=400, justify="left").pack(fill=tk.X, pady=2)

        self.btn_add_note_region = tk.Button(
            frame, text="노트 캡처 영역 추가", command=self._add_note_capture_region
        )
        self.btn_add_note_region.pack(fill=tk.X, padx=5, pady=2)

        self.btn_add_rail_region = tk.Button(
            frame, text="레일 캡처 영역 추가", command=self._add_rail_capture_region
        )
        self.btn_add_rail_region.pack(fill=tk.X, padx=5, pady=2)

        self.note_rail_list_frame = tk.Frame(frame)
        self.note_rail_list_frame.pack(fill=tk.X)
        self._refresh_note_rail_list()

    def _build_preview(self, parent: tk.Frame) -> None:
        """실시간 미리보기"""
        frame = tk.LabelFrame(parent, text="실시간 미리보기", padx=5, pady=5)
        frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=3)

        self.preview_label = tk.Label(frame, text="미리보기 없음")
        self.preview_label.pack(fill=tk.BOTH, expand=True)

    def _build_log(self, parent: tk.Frame) -> None:
        """로그 출력 영역"""
        frame = tk.LabelFrame(parent, text="로그", padx=5, pady=5)
        frame.pack(fill=tk.X, padx=5, pady=3)

        self.log_text = tk.Text(frame, height=6, state=tk.DISABLED, wrap=tk.WORD)
        self.log_text.pack(fill=tk.X)

        log_scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)

    # ───────────── 설정 저장/로드 ─────────────

    def _gui_to_config(self) -> None:
        """GUI 값을 config에 반영"""
        self.config.set("capture_region", {
            "x": self.var_cap_x.get(),
            "y": self.var_cap_y.get(),
            "width": self.var_cap_w.get(),
            "height": self.var_cap_h.get(),
        })
        self.config.set("lane_count", self.var_lane_count.get())
        self.config.set("key_bindings", [k.strip() for k in self.var_keys.get().split(",")])
        self.config.set("hsv_lower", [self.var_h_low.get(), self.var_s_low.get(), self.var_v_low.get()])
        self.config.set("hsv_upper", [self.var_h_high.get(), self.var_s_high.get(), self.var_v_high.get()])
        self.config.set("judge_line_ratio", self.var_judge_ratio.get())
        self.config.set("perfect_range", self.var_perfect.get())
        self.config.set("great_range", self.var_great.get())
        self.config.set("good_range", self.var_good.get())
        self.config.set("input_delay_ms", self.var_delay.get())
        self.config.set("debounce_ms", self.var_debounce.get())
        self.config.set("min_note_size", self.var_min_note.get())
        self.config.set("debug_mode", self.var_debug.get())
        self.config.set("use_grayscale", self.var_grayscale.get())
        self.config.set("frame_skip", self.var_frame_skip.get())
        self.config.set("overlay_mode", self.var_overlay.get())
        self.config.set("always_on_top", self.var_always_top.get())
        self.config.set("dark_mode", self.var_dark_mode.get())
        self.config.set("long_note_enabled", self.var_long_note.get())
        self.config.set("auto_calibration", self.var_auto_cal.get())
        self.config.set("show_log", self.var_show_log.get())
        self.config.set("speed_correction", self.var_speed_corr.get())

    def _load_config_to_gui(self) -> None:
        """config 값을 GUI에 반영"""
        cfg = self.config
        region = cfg.get("capture_region", {})
        self.var_cap_x.set(region.get("x", 0))
        self.var_cap_y.set(region.get("y", 0))
        self.var_cap_w.set(region.get("width", 800))
        self.var_cap_h.set(region.get("height", 600))
        self.var_lane_count.set(cfg.get("lane_count", 4))
        bindings = cfg.get("key_bindings", ["d", "f", "j", "k"])
        self.var_keys.set(",".join(bindings))

    def _save_config(self) -> None:
        """설정 저장"""
        try:
            self._gui_to_config()
            self.config.save()
            self._log("설정이 저장되었습니다.")
        except Exception as e:
            self._log(f"설정 저장 실패: {e}")

    def _reset_config(self) -> None:
        """설정 초기화"""
        if messagebox.askyesno("확인", "설정을 기본값으로 초기화하시겠습니까?"):
            self.config.reset()
            self._load_config_to_gui()
            self._log("설정이 초기화되었습니다.")

    # ───────────── 봇 시작/정지 ─────────────

    def _start_bot(self) -> None:
        """봇 시작"""
        if self._running:
            return

        try:
            self._gui_to_config()
            self._running = True
            self._stop_event.clear()
            self._status = "실행 중"

            # 캡처 시작
            self.capture.start()

            # 입력 관리자 설정
            keys = [k.strip() for k in self.var_keys.get().split(",")]
            self.input_mgr.configure(
                key_bindings=keys,
                debounce_ms=self.var_debounce.get(),
                input_delay_ms=self.var_delay.get(),
            )
            self.input_mgr.start()

            # 봇 스레드 시작
            self._bot_thread = threading.Thread(target=self._bot_loop, daemon=True)
            self._bot_thread.start()

            # 미리보기 업데이트 시작
            self._update_preview()

            # UI 상태 변경
            self.btn_start.config(state=tk.DISABLED)
            self.btn_stop.config(state=tk.NORMAL)
            self._log("봇이 시작되었습니다.")
            self._update_status()

        except Exception as e:
            self._running = False
            self._log(f"시작 실패: {e}")

    def _stop_bot(self) -> None:
        """봇 정지"""
        self._running = False
        self._stop_event.set()
        self._status = "정지됨"

        self.input_mgr.stop()
        self.capture.stop()

        self.btn_start.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        self._log("봇이 정지되었습니다.")
        self._update_status()

    def _emergency_stop(self) -> None:
        """긴급 종료"""
        self._stop_bot()
        self._log("⚠ 긴급 종료!")
        self._status = "긴급 종료"
        self._update_status()

    # ───────────── 봇 메인 루프 ─────────────

    def _bot_loop(self) -> None:
        """봇 메인 루프 (별도 스레드에서 실행)"""
        frame_count = 0
        frame_skip = self.var_frame_skip.get()

        while self._running and not self._stop_event.is_set():
            try:
                # 프레임 스킵 처리
                frame_count += 1
                if frame_skip > 0 and frame_count % (frame_skip + 1) != 0:
                    time.sleep(0.001)
                    continue

                # 화면 캡처
                region = {
                    "x": self.var_cap_x.get(),
                    "y": self.var_cap_y.get(),
                    "width": self.var_cap_w.get(),
                    "height": self.var_cap_h.get(),
                }
                frame = self.capture.capture(region)

                if frame is None or frame.size == 0:
                    time.sleep(0.01)
                    continue

                h, w = frame.shape[:2]
                judge_line_y = int(h * self.var_judge_ratio.get())

                # 속도 보정 적용
                speed_corr = self.var_speed_corr.get()
                corrected_judge_y = int(judge_line_y * speed_corr)
                corrected_judge_y = min(corrected_judge_y, h - 1)

                # 노트 감지
                notes = self.detector.detect(
                    frame=frame,
                    lane_count=self.var_lane_count.get(),
                    hsv_lower=[self.var_h_low.get(), self.var_s_low.get(), self.var_v_low.get()],
                    hsv_upper=[self.var_h_high.get(), self.var_s_high.get(), self.var_v_high.get()],
                    min_note_size=self.var_min_note.get(),
                    use_grayscale=self.var_grayscale.get(),
                    judge_line_y=judge_line_y,
                    note_capture_regions=self.config.get("note_capture_regions", []),
                    rail_capture_regions=self.config.get("rail_capture_regions", []),
                )

                self._note_count = len(notes)
                self._fps_display = self.capture.fps

                # 판정선 근처 노트에 키 입력
                judge_notes = self.detector.get_notes_near_judge(
                    notes=notes,
                    judge_line_y=corrected_judge_y,
                    perfect_range=self.var_perfect.get(),
                    great_range=self.var_great.get(),
                    good_range=self.var_good.get(),
                )

                # 입력 실행 (perfect, great, good 순서로 처리)
                pressed_lanes = set()
                for grade in ["perfect", "great", "good"]:
                    for note in judge_notes[grade]:
                        if note.lane not in pressed_lanes:
                            is_long = (
                                self.var_long_note.get()
                                and note.h > self.var_min_note.get() * 3
                            )
                            self.input_mgr.press_lane(note.lane, is_long_note=is_long)
                            pressed_lanes.add(note.lane)

                # 롱노트 해제 처리
                if self.var_long_note.get():
                    active = set(n.lane for n in notes if n.center_y >= corrected_judge_y - self.var_good.get())
                    for lane_idx in range(self.var_lane_count.get()):
                        if lane_idx not in active and lane_idx not in pressed_lanes:
                            self.input_mgr.release_lane(lane_idx)

                # CPU 사용량 제한
                time.sleep(0.001)

            except Exception as e:
                self._log(f"오류: {e}")
                time.sleep(0.1)

    # ───────────── 미리보기 업데이트 ─────────────

    def _update_preview(self) -> None:
        """미리보기 화면 업데이트 (메인 스레드에서 주기적 실행)"""
        if not self._running:
            return

        try:
            debug_frame = self.detector.debug_frame
            if debug_frame is not None and Image is not None:
                # 미리보기 크기 조정
                preview_w = self.preview_label.winfo_width()
                preview_h = self.preview_label.winfo_height()
                if preview_w > 10 and preview_h > 10:
                    frame_rgb = cv2.cvtColor(debug_frame, cv2.COLOR_BGR2RGB)
                    img = Image.fromarray(frame_rgb)
                    img = img.resize((preview_w, preview_h), Image.Resampling.NEAREST)
                    photo = ImageTk.PhotoImage(img)
                    self.preview_label.config(image=photo, text="")
                    self.preview_label._photo = photo  # 참조 유지
        except Exception:
            pass

        # 상태 업데이트
        self._update_status()

        # 주기적 호출 (약 30fps)
        if self._running:
            self.root.after(33, self._update_preview)

    def _update_status(self) -> None:
        """상태 표시 업데이트"""
        try:
            self.lbl_status.config(text=f"상태: {self._status}")
            self.lbl_fps.config(text=f"FPS: {self._fps_display:.1f}")
            self.lbl_notes.config(text=f"감지 노트: {self._note_count}")

            active = self.input_mgr.active_lanes
            keys = self.input_mgr.key_bindings
            active_str = ", ".join(
                keys[i] if i < len(keys) else "?" for i in active
            ) if active else "-"
            self.lbl_active_keys.config(text=f"입력 키: {active_str}")
        except Exception:
            pass

    # ───────────── 로그 ─────────────

    def _log(self, message: str) -> None:
        """로그 메시지 추가"""
        timestamp = time.strftime("%H:%M:%S")
        log_line = f"[{timestamp}] {message}"
        self._log_messages.append(log_line)

        # 로그 텍스트에 표시
        try:
            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, log_line + "\n")
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)

            # 최대 100줄 유지
            lines = int(self.log_text.index("end-1c").split(".")[0])
            if lines > 100:
                self.log_text.config(state=tk.NORMAL)
                self.log_text.delete("1.0", "2.0")
                self.log_text.config(state=tk.DISABLED)
        except Exception:
            pass

    # ───────────── 화면 영역 선택 ─────────────

    def _select_capture_region(self) -> None:
        """마우스로 캡처 영역 선택"""
        self._log("화면에서 영역을 드래그하여 선택하세요...")

        selector = tk.Toplevel(self.root)
        selector.attributes("-fullscreen", True)
        selector.attributes("-alpha", 0.3)
        selector.configure(bg="black")
        selector.attributes("-topmost", True)

        canvas = tk.Canvas(selector, cursor="cross", bg="black", highlightthickness=0)
        canvas.pack(fill=tk.BOTH, expand=True)

        start = {"x": 0, "y": 0}
        rect_id = [None]

        def on_press(event):
            start["x"] = event.x
            start["y"] = event.y

        def on_drag(event):
            if rect_id[0]:
                canvas.delete(rect_id[0])
            rect_id[0] = canvas.create_rectangle(
                start["x"], start["y"], event.x, event.y,
                outline="red", width=2
            )

        def on_release(event):
            x1, y1 = min(start["x"], event.x), min(start["y"], event.y)
            x2, y2 = max(start["x"], event.x), max(start["y"], event.y)
            self.var_cap_x.set(x1)
            self.var_cap_y.set(y1)
            self.var_cap_w.set(x2 - x1)
            self.var_cap_h.set(y2 - y1)
            self._log(f"영역 선택: ({x1}, {y1}) - ({x2}, {y2})")
            selector.destroy()

        canvas.bind("<ButtonPress-1>", on_press)
        canvas.bind("<B1-Motion>", on_drag)
        canvas.bind("<ButtonRelease-1>", on_release)
        selector.bind("<Escape>", lambda e: selector.destroy())

    # ───────────── 노트/레일 개별 캡처 ─────────────

    def _add_note_capture_region(self) -> None:
        """노트 캡처 영역 추가 다이얼로그"""
        self._add_capture_region_dialog("note")

    def _add_rail_capture_region(self) -> None:
        """레일 캡처 영역 추가 다이얼로그"""
        self._add_capture_region_dialog("rail")

    def _add_capture_region_dialog(self, region_type: str) -> None:
        """캡처 영역 추가 다이얼로그"""
        dialog = tk.Toplevel(self.root)
        dialog.title(f"{'노트' if region_type == 'note' else '레일'} 캡처 영역 추가")
        dialog.geometry("300x250")
        dialog.transient(self.root)

        tk.Label(dialog, text="레인 번호:").pack(pady=2)
        var_lane = tk.IntVar(value=0)
        tk.Spinbox(dialog, from_=0, to=9, textvariable=var_lane, width=5).pack()

        tk.Label(dialog, text="X 오프셋:").pack(pady=2)
        var_x = tk.IntVar(value=0)
        tk.Entry(dialog, textvariable=var_x, width=10).pack()

        tk.Label(dialog, text="Y 오프셋:").pack(pady=2)
        var_y = tk.IntVar(value=0)
        tk.Entry(dialog, textvariable=var_y, width=10).pack()

        tk.Label(dialog, text="너비:").pack(pady=2)
        var_w = tk.IntVar(value=100)
        tk.Entry(dialog, textvariable=var_w, width=10).pack()

        tk.Label(dialog, text="높이:").pack(pady=2)
        var_h = tk.IntVar(value=100)
        tk.Entry(dialog, textvariable=var_h, width=10).pack()

        def add():
            region = {
                "lane": var_lane.get(),
                "x": var_x.get(),
                "y": var_y.get(),
                "width": var_w.get(),
                "height": var_h.get(),
            }
            config_key = "note_capture_regions" if region_type == "note" else "rail_capture_regions"
            regions = self.config.get(config_key, [])
            regions.append(region)
            self.config.set(config_key, regions)
            self._refresh_note_rail_list()
            self._log(f"{'노트' if region_type == 'note' else '레일'} 캡처 영역 추가: 레인 {region['lane']}")
            dialog.destroy()

        tk.Button(dialog, text="추가", command=add).pack(pady=10)

    def _refresh_note_rail_list(self) -> None:
        """노트/레일 캡처 영역 목록 갱신"""
        for widget in self.note_rail_list_frame.winfo_children():
            widget.destroy()

        note_regions = self.config.get("note_capture_regions", [])
        rail_regions = self.config.get("rail_capture_regions", [])

        for i, r in enumerate(note_regions):
            row = tk.Frame(self.note_rail_list_frame)
            row.pack(fill=tk.X, pady=1)
            tk.Label(row, text=f"노트 L{r.get('lane', '?')}: ({r.get('x',0)},{r.get('y',0)}) {r.get('width',0)}x{r.get('height',0)}").pack(side=tk.LEFT)
            idx = i
            tk.Button(row, text="삭제", command=lambda idx=idx: self._remove_capture_region("note", idx)).pack(side=tk.RIGHT)

        for i, r in enumerate(rail_regions):
            row = tk.Frame(self.note_rail_list_frame)
            row.pack(fill=tk.X, pady=1)
            tk.Label(row, text=f"레일 L{r.get('lane', '?')}: ({r.get('x',0)},{r.get('y',0)}) {r.get('width',0)}x{r.get('height',0)}").pack(side=tk.LEFT)
            idx = i
            tk.Button(row, text="삭제", command=lambda idx=idx: self._remove_capture_region("rail", idx)).pack(side=tk.RIGHT)

    def _remove_capture_region(self, region_type: str, index: int) -> None:
        """캡처 영역 삭제"""
        config_key = "note_capture_regions" if region_type == "note" else "rail_capture_regions"
        regions = self.config.get(config_key, [])
        if 0 <= index < len(regions):
            regions.pop(index)
            self.config.set(config_key, regions)
            self._refresh_note_rail_list()

    # ───────────── 테마 ─────────────

    def _apply_theme(self) -> None:
        """현재 테마 적용"""
        theme = self._theme
        self.root.configure(bg=theme["bg"])
        self._apply_theme_recursive(self.root, theme)

    def _apply_theme_recursive(self, widget, theme: dict) -> None:
        """위젯 트리에 테마 적용"""
        try:
            widget_type = widget.winfo_class()
            if widget_type in ("Frame", "Labelframe"):
                widget.configure(bg=theme["bg"])
            elif widget_type == "Label":
                widget.configure(bg=theme["bg"], fg=theme["fg"])
            elif widget_type == "Button":
                widget.configure(bg=theme["button_bg"], fg=theme["fg"],
                                 activebackground=theme["button_active"])
            elif widget_type == "Entry":
                widget.configure(bg=theme["entry_bg"], fg=theme["fg"],
                                 insertbackground=theme["fg"])
            elif widget_type == "Text":
                widget.configure(bg=theme["entry_bg"], fg=theme["fg"],
                                 insertbackground=theme["fg"])
            elif widget_type == "Checkbutton":
                widget.configure(bg=theme["bg"], fg=theme["fg"],
                                 activebackground=theme["bg"],
                                 selectcolor=theme["entry_bg"])
            elif widget_type == "Scale":
                widget.configure(bg=theme["bg"], fg=theme["fg"],
                                 troughcolor=theme["entry_bg"],
                                 activebackground=theme["accent"])
            elif widget_type == "Canvas":
                widget.configure(bg=theme["bg"])
            elif widget_type == "Spinbox":
                widget.configure(bg=theme["entry_bg"], fg=theme["fg"],
                                 buttonbackground=theme["button_bg"])
        except Exception:
            pass

        for child in widget.winfo_children():
            self._apply_theme_recursive(child, theme)

    def _toggle_dark_mode(self, *args) -> None:
        """다크모드 토글"""
        self._theme = DARK_THEME if self.var_dark_mode.get() else LIGHT_THEME
        self._apply_theme()

    def _toggle_always_on_top(self, *args) -> None:
        """항상 위 토글"""
        self.root.attributes("-topmost", self.var_always_top.get())

    # ───────────── 종료 ─────────────

    def _on_close(self) -> None:
        """프로그램 종료 처리"""
        self._stop_bot()
        self._save_config()
        try:
            self.root.destroy()
        except Exception:
            pass

    def run(self) -> None:
        """GUI 메인 루프 실행"""
        self._log("리듬게임 자동 봇이 준비되었습니다.")
        self._log("캡처 영역과 HSV 값을 설정한 후 시작 버튼을 누르세요.")
        self._log("ESC 키로 긴급 종료할 수 있습니다.")
        self.root.mainloop()
