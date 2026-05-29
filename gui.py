"""
RhythmBotGUI - 초보자 친화적 간단 GUI
스포이드로 노트 색상을 클릭 한 번에 추출, 단계별 설정
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

try:
    import mss
except ImportError:
    mss = None

from config_manager import ConfigManager
from screen_capture import ScreenCapture
from note_detector import NoteDetector
from input_manager import InputManager


# 다크모드 색상
BG = "#1e1e1e"
FG = "#e0e0e0"
ACCENT = "#4fc3f7"
BTN_BG = "#333333"
BTN_ACTIVE = "#555555"
ENTRY_BG = "#2a2a2a"
SUCCESS = "#66bb6a"
ERROR = "#ef5350"
WARN = "#ffa726"


class RhythmBotGUI:
    """초보자용 간단 리듬게임 봇 GUI"""

    def __init__(self):
        self.config = ConfigManager()
        self.capture = ScreenCapture()
        self.detector = NoteDetector()
        self.input_mgr = InputManager()

        self._running = False
        self._bot_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._fps_display = 0.0
        self._note_count = 0
        self._status = "대기 중"

        # 스포이드로 추출한 색상 (BGR)
        self._picked_color_bgr = None
        # HSV 허용 범위 (스포이드 자동 계산용)
        self._hsv_tolerance = 25

        self.root = tk.Tk()
        self.root.title("리듬게임 자동 봇")
        self.root.geometry("700x680")
        self.root.minsize(600, 580)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<Escape>", lambda e: self._emergency_stop())

        if self.config.get("always_on_top"):
            self.root.attributes("-topmost", True)

        self._init_vars()
        self._build_gui()
        self._load_from_config()

    # ─── 변수 초기화 ───

    def _init_vars(self):
        cfg = self.config
        region = cfg.get("capture_region", {})
        self.var_cap_x = tk.IntVar(value=region.get("x", 0))
        self.var_cap_y = tk.IntVar(value=region.get("y", 0))
        self.var_cap_w = tk.IntVar(value=region.get("width", 800))
        self.var_cap_h = tk.IntVar(value=region.get("height", 600))
        self.var_lane_count = tk.IntVar(value=cfg.get("lane_count", 4))
        self.var_keys = tk.StringVar(value=",".join(cfg.get("key_bindings", ["d", "f", "j", "k"])))
        self.var_judge_ratio = tk.DoubleVar(value=cfg.get("judge_line_ratio", 0.85))
        self.var_delay = tk.IntVar(value=cfg.get("input_delay_ms", 0))
        self.var_offset_px = tk.IntVar(value=cfg.get("input_offset_px", 0))
        self.var_tolerance = tk.IntVar(value=25)
        self.var_always_top = tk.BooleanVar(value=cfg.get("always_on_top", False))

        # 콤보 제외 영역 (캐피 영역 기준 상대 좌표)
        exc = cfg.get("exclude_region", {})
        self.var_exc_x = tk.IntVar(value=exc.get("x", 0))
        self.var_exc_y = tk.IntVar(value=exc.get("y", 0))
        self.var_exc_w = tk.IntVar(value=exc.get("width", 0))
        self.var_exc_h = tk.IntVar(value=exc.get("height", 0))

        hsv_l = cfg.get("hsv_lower", [0, 0, 200])
        hsv_u = cfg.get("hsv_upper", [180, 50, 255])
        self.var_h_low = tk.IntVar(value=hsv_l[0])
        self.var_s_low = tk.IntVar(value=hsv_l[1])
        self.var_v_low = tk.IntVar(value=hsv_l[2])
        self.var_h_high = tk.IntVar(value=hsv_u[0])
        self.var_s_high = tk.IntVar(value=hsv_u[1])
        self.var_v_high = tk.IntVar(value=hsv_u[2])

    # ─── GUI 구성 ───

    def _build_gui(self):
        # 스크롤 가능한 메인
        canvas = tk.Canvas(self.root, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.root, orient=tk.VERTICAL, command=canvas.yview)
        self.main = tk.Frame(canvas, bg=BG)
        self.main.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.main, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))
        canvas.bind_all("<Button-4>", lambda e: canvas.yview_scroll(-1, "units"))
        canvas.bind_all("<Button-5>", lambda e: canvas.yview_scroll(1, "units"))

        # 타이틀
        tk.Label(self.main, text="🎵 리듬게임 자동 봇", font=("", 18, "bold"),
                 bg=BG, fg=ACCENT).pack(pady=(10, 5))
        tk.Label(self.main, text="아래 순서대로 설정하면 끝!", font=("", 11),
                 bg=BG, fg="#aaaaaa").pack()

        self._build_step1_region()
        self._build_step2_color()
        self._build_step3_keys()
        self._build_step4_judge()
        self._build_step5_control()
        self._build_status_bar()
        self._build_preview()
        self._build_log()

    def _section(self, title: str, step: int) -> tk.LabelFrame:
        lf = tk.LabelFrame(
            self.main, text=f"  STEP {step}. {title}  ",
            font=("", 11, "bold"), bg=BG, fg=ACCENT,
            padx=12, pady=8, labelanchor="n"
        )
        lf.pack(fill=tk.X, padx=15, pady=6)
        return lf

    # ─── STEP 1: 캡처 영역 ───

    def _build_step1_region(self):
        f = self._section("게임 화면 영역 선택", 1)

        tk.Label(f, text="게임에서 노트가 떨어지는 영역을 선택하세요.",
                 bg=BG, fg="#bbbbbb", wraplength=500).pack(anchor="w")

        btn_frame = tk.Frame(f, bg=BG)
        btn_frame.pack(fill=tk.X, pady=5)

        self.btn_select_region = tk.Button(
            btn_frame, text="🖱 화면에서 영역 드래그", font=("", 11),
            bg="#2196F3", fg="white", activebackground="#1976D2",
            command=self._select_capture_region, height=2
        )
        self.btn_select_region.pack(fill=tk.X)

        # 영역 표시
        self.lbl_region = tk.Label(f, text="영역: 미설정", bg=BG, fg="#999999")
        self.lbl_region.pack(anchor="w", pady=2)

    # ─── STEP 2: 색상 스포이드 ───

    def _build_step2_color(self):
        f = self._section("노트 색상 추출 (스포이드)", 2)

        tk.Label(f, text="아래 버튼을 누른 뒤, 게임 화면의 노트 위를 클릭하세요.\n"
                         "자동으로 색상을 인식합니다.",
                 bg=BG, fg="#bbbbbb", wraplength=500, justify="left").pack(anchor="w")

        btn_frame = tk.Frame(f, bg=BG)
        btn_frame.pack(fill=tk.X, pady=5)

        self.btn_eyedropper = tk.Button(
            btn_frame, text="💧 스포이드로 노트 색상 추출", font=("", 11),
            bg="#9C27B0", fg="white", activebackground="#7B1FA2",
            command=self._start_eyedropper, height=2
        )
        self.btn_eyedropper.pack(fill=tk.X)

        # 추출된 색상 표시
        color_row = tk.Frame(f, bg=BG)
        color_row.pack(fill=tk.X, pady=3)

        tk.Label(color_row, text="추출된 색상:", bg=BG, fg=FG).pack(side=tk.LEFT)
        self.color_preview = tk.Label(color_row, text="   ", bg="#555555",
                                      width=4, relief="solid")
        self.color_preview.pack(side=tk.LEFT, padx=5)
        self.lbl_color_info = tk.Label(color_row, text="미추출", bg=BG, fg="#999999")
        self.lbl_color_info.pack(side=tk.LEFT)

        # 허용 범위
        tol_row = tk.Frame(f, bg=BG)
        tol_row.pack(fill=tk.X, pady=3)
        tk.Label(tol_row, text="색상 허용 범위:", bg=BG, fg=FG).pack(side=tk.LEFT)
        tk.Scale(tol_row, variable=self.var_tolerance, from_=5, to=80,
                 orient=tk.HORIZONTAL, length=200, bg=BG, fg=FG,
                 troughcolor=ENTRY_BG, activebackground=ACCENT,
                 command=lambda v: self._update_hsv_from_picked()
                 ).pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(tol_row, text="(작을수록 정밀, 클수록 넓게 인식)", bg=BG,
                 fg="#888888", font=("", 9)).pack(side=tk.LEFT)

        # 콤보 제외 영역 버튼
        exc_frame = tk.Frame(f, bg=BG)
        exc_frame.pack(fill=tk.X, pady=5)

        self.btn_exclude = tk.Button(
            exc_frame, text="🚫 콤보 영역 설정 (선택사항)", font=("", 10),
            bg="#E65100", fg="white", activebackground="#BF360C",
            command=self._select_exclude_region
        )
        self.btn_exclude.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.btn_exc_clear = tk.Button(
            exc_frame, text="❌ 해제", font=("", 10),
            bg=BTN_BG, fg=FG, activebackground=BTN_ACTIVE,
            command=self._clear_exclude_region
        )
        self.btn_exc_clear.pack(side=tk.LEFT, padx=(5, 0))

        self.lbl_exclude = tk.Label(f, text="콤보 제외: 미설정", bg=BG, fg="#999999", font=("", 9))
        self.lbl_exclude.pack(anchor="w")

    # ─── STEP 3: 키 설정 ───

    def _build_step3_keys(self):
        f = self._section("레인 & 키 설정", 3)

        row1 = tk.Frame(f, bg=BG)
        row1.pack(fill=tk.X, pady=3)
        tk.Label(row1, text="레인 개수:", bg=BG, fg=FG).pack(side=tk.LEFT)
        tk.Spinbox(row1, from_=1, to=10, textvariable=self.var_lane_count,
                   width=4, bg=ENTRY_BG, fg=FG, insertbackground=FG
                   ).pack(side=tk.LEFT, padx=5)

        row2 = tk.Frame(f, bg=BG)
        row2.pack(fill=tk.X, pady=3)
        tk.Label(row2, text="키 바인딩:", bg=BG, fg=FG).pack(side=tk.LEFT)
        tk.Entry(row2, textvariable=self.var_keys, width=20,
                 bg=ENTRY_BG, fg=FG, insertbackground=FG
                 ).pack(side=tk.LEFT, padx=5)
        tk.Label(row2, text="(쉼표로 구분 예: d,f,j,k)", bg=BG,
                 fg="#888888", font=("", 9)).pack(side=tk.LEFT)

    # ─── STEP 4: 판정선 ───

    def _build_step4_judge(self):
        f = self._section("판정선 위치", 4)

        tk.Label(f, text="노트를 언제 눌러야 하는지 위치를 정합니다.\n"
                         "1.0에 가까울수록 아래쪽입니다.",
                 bg=BG, fg="#bbbbbb", wraplength=500, justify="left").pack(anchor="w")

        row = tk.Frame(f, bg=BG)
        row.pack(fill=tk.X, pady=3)
        tk.Label(row, text="판정선:", bg=BG, fg=FG).pack(side=tk.LEFT)
        tk.Scale(row, variable=self.var_judge_ratio, from_=0.3, to=1.0,
                 resolution=0.01, orient=tk.HORIZONTAL, length=300,
                 bg=BG, fg=FG, troughcolor=ENTRY_BG,
                 activebackground=ACCENT).pack(side=tk.LEFT, fill=tk.X, expand=True)

        # 입력 오프셋
        row2 = tk.Frame(f, bg=BG)
        row2.pack(fill=tk.X, pady=3)
        tk.Label(row2, text="입력 오프셋(px):", bg=BG, fg=FG).pack(side=tk.LEFT)
        tk.Scale(row2, variable=self.var_offset_px, from_=-80, to=80,
                 resolution=5, orient=tk.HORIZONTAL, length=250,
                 bg=BG, fg=FG, troughcolor=ENTRY_BG,
                 activebackground=ACCENT).pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(row2, text="(-: 빨리 / +: 늦게)", bg=BG,
                 fg="#888888", font=("", 9)).pack(side=tk.LEFT)

    # ─── STEP 5: 시작/정지 ───

    def _build_step5_control(self):
        f = self._section("실행", 5)

        btn_row = tk.Frame(f, bg=BG)
        btn_row.pack(fill=tk.X, pady=5)

        self.btn_start = tk.Button(
            btn_row, text="▶  시작", font=("", 13, "bold"),
            bg=SUCCESS, fg="white", activebackground="#43a047",
            command=self._start_bot, height=2
        )
        self.btn_start.pack(side=tk.LEFT, padx=3, expand=True, fill=tk.X)

        self.btn_stop = tk.Button(
            btn_row, text="■  정지", font=("", 13, "bold"),
            bg=ERROR, fg="white", activebackground="#c62828",
            command=self._stop_bot, height=2, state=tk.DISABLED
        )
        self.btn_stop.pack(side=tk.LEFT, padx=3, expand=True, fill=tk.X)

        # 보조 버튼
        btn_row2 = tk.Frame(f, bg=BG)
        btn_row2.pack(fill=tk.X, pady=3)

        tk.Button(btn_row2, text="💾 설정 저장", bg=BTN_BG, fg=FG,
                  activebackground=BTN_ACTIVE,
                  command=self._save_config).pack(side=tk.LEFT, padx=3, expand=True, fill=tk.X)
        tk.Button(btn_row2, text="🔄 설정 초기화", bg=BTN_BG, fg=FG,
                  activebackground=BTN_ACTIVE,
                  command=self._reset_config).pack(side=tk.LEFT, padx=3, expand=True, fill=tk.X)

        cb = tk.Checkbutton(btn_row2, text="항상 위", variable=self.var_always_top,
                            bg=BG, fg=FG, selectcolor=ENTRY_BG,
                            activebackground=BG,
                            command=lambda: self.root.attributes("-topmost", self.var_always_top.get()))
        cb.pack(side=tk.LEFT, padx=5)

        # 테스트 입력 버튼
        btn_row3 = tk.Frame(f, bg=BG)
        btn_row3.pack(fill=tk.X, pady=3)
        tk.Button(btn_row3, text="⌨ 키 입력 테스트 (3초 후 d,f,j,k 자동 입력)",
                  bg="#FF6F00", fg="white", activebackground="#E65100",
                  command=self._test_key_input).pack(fill=tk.X)
        self.lbl_test = tk.Label(f, text="", bg=BG, fg="#999999", font=("", 9))
        self.lbl_test.pack(anchor="w")

    # ─── 상태바 ───

    def _build_status_bar(self):
        bar = tk.Frame(self.main, bg="#111111")
        bar.pack(fill=tk.X, padx=15, pady=3)

        self.lbl_status = tk.Label(bar, text="상태: 대기 중", bg="#111111", fg=FG,
                                   anchor="w", font=("", 10))
        self.lbl_status.pack(side=tk.LEFT, padx=5)

        self.lbl_fps = tk.Label(bar, text="FPS: 0", bg="#111111", fg=ACCENT,
                                anchor="e", font=("", 10))
        self.lbl_fps.pack(side=tk.RIGHT, padx=5)

        self.lbl_notes = tk.Label(bar, text="노트: 0", bg="#111111", fg=WARN,
                                  anchor="e", font=("", 10))
        self.lbl_notes.pack(side=tk.RIGHT, padx=5)

        self.lbl_keys = tk.Label(bar, text="키: -", bg="#111111", fg=SUCCESS,
                                 anchor="e", font=("", 10))
        self.lbl_keys.pack(side=tk.RIGHT, padx=5)

    # ─── 미리보기 (별도 창) ───

    def _build_preview(self):
        # 메인 창에는 미리보기 열기 버튼만
        f = tk.Frame(self.main, bg=BG)
        f.pack(fill=tk.X, padx=15, pady=3)
        self.btn_preview = tk.Button(
            f, text="🔍 미리보기 창 열기", bg=BTN_BG, fg=FG,
            activebackground=BTN_ACTIVE, command=self._open_preview_window
        )
        self.btn_preview.pack(fill=tk.X)

        # 미리보기 창 참조
        self._preview_win = None
        self._preview_canvas = None
        self._preview_photo = None

    def _open_preview_window(self):
        """고정 크기 미리보기 창 열기"""
        if self._preview_win is not None:
            try:
                self._preview_win.lift()
                return
            except tk.TclError:
                self._preview_win = None

        win = tk.Toplevel(self.root)
        win.title("미리보기 - 노트 감지")
        win.geometry("500x400")
        win.configure(bg="#111111")
        win.protocol("WM_DELETE_WINDOW", lambda: self._close_preview_window())

        self._preview_canvas = tk.Label(win, bg="#111111")
        self._preview_canvas.pack(fill=tk.BOTH, expand=True)

        self._preview_win = win

    # ─── 로그 ───

    def _build_log(self):
        f = tk.LabelFrame(self.main, text="  로그  ", font=("", 10),
                          bg=BG, fg="#888888", padx=5, pady=3)
        f.pack(fill=tk.X, padx=15, pady=(3, 10))

        self.log_text = tk.Text(f, height=4, state=tk.DISABLED, wrap=tk.WORD,
                                bg="#111111", fg="#aaaaaa", insertbackground=FG)
        self.log_text.pack(fill=tk.X)

    # ═══════════ 스포이드 (핵심 기능) ═══════════

    def _start_eyedropper(self):
        """화면 전체를 캡처 후, 사용자가 클릭한 위치의 색상을 추출"""
        self._log("스포이드 모드: 노트 위를 클릭하세요 (ESC로 취소)")

        picker = tk.Toplevel(self.root)
        picker.attributes("-fullscreen", True)
        picker.attributes("-topmost", True)
        picker.configure(cursor="cross")

        # 현재 화면 캡처
        sct = mss.mss()
        monitor = sct.monitors[0]
        screenshot = sct.grab(monitor)
        img_array = np.array(screenshot, dtype=np.uint8)[:, :, :3]  # BGRA→BGR
        sct.close()

        # PIL로 변환하여 tkinter에 표시
        img_rgb = cv2.cvtColor(img_array, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(img_rgb)
        photo = ImageTk.PhotoImage(pil_img)

        canvas = tk.Canvas(picker, highlightthickness=0)
        canvas.pack(fill=tk.BOTH, expand=True)
        canvas.create_image(0, 0, image=photo, anchor="nw")
        canvas._photo = photo

        # 돋보기/색상 표시 라벨
        info_label = tk.Label(picker, text="", bg="black", fg="white",
                              font=("", 12, "bold"), padx=8, pady=4)

        def on_move(event):
            x, y = event.x, event.y
            h_img, w_img = img_array.shape[:2]
            if 0 <= x < w_img and 0 <= y < h_img:
                b, g, r = img_array[y, x]
                hex_color = f"#{r:02x}{g:02x}{b:02x}"
                info_label.config(text=f"  {hex_color}  ", bg=hex_color,
                                  fg="white" if (r + g + b) < 400 else "black")
                info_label.place(x=x + 15, y=y + 15)

        def on_click(event):
            x, y = event.x, event.y
            h_img, w_img = img_array.shape[:2]
            if 0 <= x < w_img and 0 <= y < h_img:
                # 클릭 지점 주변 5x5 영역 평균 색상
                x1 = max(0, x - 2)
                y1 = max(0, y - 2)
                x2 = min(w_img, x + 3)
                y2 = min(h_img, y + 3)
                region = img_array[y1:y2, x1:x2]
                avg_bgr = region.mean(axis=(0, 1)).astype(int)
                self._picked_color_bgr = tuple(avg_bgr)
                self._update_hsv_from_picked()
                picker.destroy()
                b, g, r = self._picked_color_bgr
                hex_color = f"#{r:02x}{g:02x}{b:02x}"
                self.color_preview.config(bg=hex_color)
                self.lbl_color_info.config(
                    text=f"RGB({r},{g},{b})",
                    fg=FG
                )
                self._log(f"색상 추출 완료: RGB({r},{g},{b})")

        canvas.bind("<Motion>", on_move)
        canvas.bind("<Button-1>", on_click)
        picker.bind("<Escape>", lambda e: picker.destroy())

    def _update_hsv_from_picked(self):
        """스포이드로 추출한 색상에서 HSV 범위를 자동 계산"""
        if self._picked_color_bgr is None:
            return

        b, g, r = self._picked_color_bgr
        pixel = np.uint8([[[b, g, r]]])
        hsv_pixel = cv2.cvtColor(pixel, cv2.COLOR_BGR2HSV)[0][0]
        h, s, v = int(hsv_pixel[0]), int(hsv_pixel[1]), int(hsv_pixel[2])

        tol = self.var_tolerance.get()

        # H는 0~180 범위 (OpenCV)
        h_tol = max(5, tol // 2)
        s_tol = tol * 2
        v_tol = tol * 2

        self.var_h_low.set(max(0, h - h_tol))
        self.var_s_low.set(max(0, s - s_tol))
        self.var_v_low.set(max(0, v - v_tol))
        self.var_h_high.set(min(180, h + h_tol))
        self.var_s_high.set(min(255, s + s_tol))
        self.var_v_high.set(min(255, v + v_tol))

    # ═══════════ 캡처 영역 선택 ═══════════

    def _select_capture_region(self):
        """마우스 드래그로 캡처 영역 선택"""
        self._log("화면에서 영역을 드래그하세요 (ESC로 취소)")

        selector = tk.Toplevel(self.root)
        selector.attributes("-fullscreen", True)
        selector.attributes("-alpha", 0.3)
        selector.configure(bg="black", cursor="cross")
        selector.attributes("-topmost", True)

        canvas = tk.Canvas(selector, bg="black", highlightthickness=0)
        canvas.pack(fill=tk.BOTH, expand=True)

        start = {"x": 0, "y": 0}
        rect_id = [None]

        def on_press(event):
            start["x"], start["y"] = event.x, event.y

        def on_drag(event):
            if rect_id[0]:
                canvas.delete(rect_id[0])
            rect_id[0] = canvas.create_rectangle(
                start["x"], start["y"], event.x, event.y,
                outline="red", width=2
            )

        def on_release(event):
            x1 = min(start["x"], event.x)
            y1 = min(start["y"], event.y)
            x2 = max(start["x"], event.x)
            y2 = max(start["y"], event.y)
            if x2 - x1 > 10 and y2 - y1 > 10:
                self.var_cap_x.set(x1)
                self.var_cap_y.set(y1)
                self.var_cap_w.set(x2 - x1)
                self.var_cap_h.set(y2 - y1)
                self.lbl_region.config(
                    text=f"영역: ({x1}, {y1}) → ({x2}, {y2})  [{x2-x1} x {y2-y1}]",
                    fg=SUCCESS
                )
                self._log(f"영역 선택 완료: ({x1},{y1}) {x2-x1}x{y2-y1}")
            selector.destroy()

        canvas.bind("<ButtonPress-1>", on_press)
        canvas.bind("<B1-Motion>", on_drag)
        canvas.bind("<ButtonRelease-1>", on_release)
        selector.bind("<Escape>", lambda e: selector.destroy())

    def _select_exclude_region(self):
        """콤보 제외 영역 선택 - 캐피 영역 내에서 드래그"""
        cap_x = self.var_cap_x.get()
        cap_y = self.var_cap_y.get()
        cap_w = self.var_cap_w.get()
        cap_h = self.var_cap_h.get()

        if cap_w < 20 or cap_h < 20:
            messagebox.showwarning("알림", "먼저 STEP 1에서 캐피 영역을 선택하세요!")
            return

        # 캐피 영역만 캐피하여 표시
        sct = mss.mss()
        monitor = {"top": cap_y, "left": cap_x, "width": cap_w, "height": cap_h}
        screenshot = sct.grab(monitor)
        img_array = np.array(screenshot, dtype=np.uint8)[:, :, :3]
        sct.close()

        img_rgb = cv2.cvtColor(img_array, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(img_rgb)
        photo = ImageTk.PhotoImage(pil_img)

        selector = tk.Toplevel(self.root)
        selector.title("콤보 영역 선택 - 콤보가 뜨는 곳을 드래그하세요")
        selector.geometry(f"{cap_w}x{cap_h}")
        selector.attributes("-topmost", True)

        canvas = tk.Canvas(selector, highlightthickness=0)
        canvas.pack(fill=tk.BOTH, expand=True)
        canvas.create_image(0, 0, image=photo, anchor="nw")
        canvas._photo = photo

        start = {"x": 0, "y": 0}
        rect_id = [None]

        def on_press(event):
            start["x"], start["y"] = event.x, event.y

        def on_drag(event):
            if rect_id[0]:
                canvas.delete(rect_id[0])
            rect_id[0] = canvas.create_rectangle(
                start["x"], start["y"], event.x, event.y,
                outline="orange", width=2, dash=(4, 4)
            )

        def on_release(event):
            x1 = min(start["x"], event.x)
            y1 = min(start["y"], event.y)
            x2 = max(start["x"], event.x)
            y2 = max(start["y"], event.y)
            if x2 - x1 > 5 and y2 - y1 > 5:
                self.var_exc_x.set(x1)
                self.var_exc_y.set(y1)
                self.var_exc_w.set(x2 - x1)
                self.var_exc_h.set(y2 - y1)
                self.lbl_exclude.config(
                    text=f"콤보 제외: ({x1},{y1}) [{x2-x1}x{y2-y1}]",
                    fg=WARN
                )
                self._log(f"콤보 제외 영역 설정: ({x1},{y1}) {x2-x1}x{y2-y1}")
            selector.destroy()

        canvas.bind("<ButtonPress-1>", on_press)
        canvas.bind("<B1-Motion>", on_drag)
        canvas.bind("<ButtonRelease-1>", on_release)
        selector.bind("<Escape>", lambda e: selector.destroy())

    def _clear_exclude_region(self):
        self.var_exc_x.set(0)
        self.var_exc_y.set(0)
        self.var_exc_w.set(0)
        self.var_exc_h.set(0)
        self.lbl_exclude.config(text="콤보 제외: 미설정", fg="#999999")
        self._log("콤보 제외 영역 해제")

    # ═══════════ 봇 제어 ═══════════

    def _start_bot(self):
        if self._running:
            return

        # 검증
        if self.var_cap_w.get() < 20 or self.var_cap_h.get() < 20:
            messagebox.showwarning("알림", "먼저 STEP 1에서 캡처 영역을 선택하세요!")
            return

        if self._picked_color_bgr is None:
            # HSV가 기본값이면 경고
            if self.var_h_low.get() == 0 and self.var_v_low.get() == 200:
                messagebox.showwarning("알림", "STEP 2에서 스포이드로 노트 색상을 추출하세요!")
                return

        try:
            self._gui_to_config()
            self.btn_start.config(state=tk.DISABLED)
            self._status = "준비 중..."
            self._log("3초 후 시작합니다 - 게임 창을 클릭하세요!")
            self._update_status()
            self.root.update()

            # 카운트다운 (게임에 포커스 줄 시간)
            for i in range(3, 0, -1):
                self._status = f"{i}초 후 시작..."
                self._update_status()
                self.root.update()
                time.sleep(1)

            self._running = True
            self._stop_event.clear()
            self._status = "실행 중"

            self.capture.start()

            keys = [k.strip() for k in self.var_keys.get().split(",")]
            self.input_mgr.configure(
                key_bindings=keys,
                debounce_ms=8,
                input_delay_ms=self.var_delay.get(),
            )
            self.input_mgr.start()

            self._bot_thread = threading.Thread(target=self._bot_loop, daemon=True)
            self._bot_thread.start()

            self._update_preview()

            self.btn_stop.config(state=tk.NORMAL)
            self._log("봇 시작! 게임 창에 포커스가 있는지 확인하세요.")
            self._update_status()

        except Exception as e:
            self._running = False
            self._log(f"시작 실패: {e}")

    def _stop_bot(self):
        self._running = False
        self._stop_event.set()
        self._status = "정지"
        self.input_mgr.stop()
        self.capture.stop()
        self.btn_start.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        self._log("봇 정지")
        self._update_status()

    def _emergency_stop(self):
        self._stop_bot()
        self._status = "긴급 종료"
        self._log("긴급 종료! (ESC)")
        self._update_status()

    def _test_key_input(self):
        """키 입력 테스트 - 3초 후 각 키를 여러 방법으로 시도"""
        self._log("키 입력 테스트: 3초 후 입력됩니다. 메모장을 열고 클릭해서 포커스를 주세요!")
        self.lbl_test.config(text="3초 후 입력됩니다... 메모장을 클릭하세요!", fg=WARN)

        def do_test():
            import platform
            is_win = platform.system() == "Windows"
            time.sleep(3)
            keys = [k.strip() for k in self.var_keys.get().split(",")]
            results = []

            for key in keys:
                ok = False

                # 방법 1: keyboard 라이브러리
                if not ok:
                    try:
                        import keyboard as _kb
                        _kb.press(key)
                        time.sleep(0.05)
                        _kb.release(key)
                        results.append(f"{key}=keyboard OK")
                        ok = True
                    except Exception as e:
                        results.append(f"{key}=keyboard 실패({e})")

                # 방법 2: Windows ctypes SendInput
                if not ok and is_win:
                    try:
                        import ctypes
                        from ctypes import wintypes
                        user32 = ctypes.WinDLL("user32")
                        vk_map = {
                            "a":0x41,"b":0x42,"c":0x43,"d":0x44,"e":0x45,
                            "f":0x46,"g":0x47,"h":0x48,"i":0x49,"j":0x4A,
                            "k":0x4B,"l":0x4C,"m":0x4D,"n":0x4E,"o":0x4F,
                            "p":0x50,"q":0x51,"r":0x52,"s":0x53,"t":0x54,
                            "u":0x55,"v":0x56,"w":0x57,"x":0x58,"y":0x59,"z":0x5A,
                        }
                        vk = vk_map.get(key.lower(), 0)
                        if vk:
                            user32.keybd_event(vk, 0, 0, 0)
                            time.sleep(0.05)
                            user32.keybd_event(vk, 0, 2, 0)
                            results.append(f"{key}=ctypes OK")
                            ok = True
                    except Exception as e:
                        results.append(f"{key}=ctypes 실패({e})")

                # 방법 3: pyautogui
                if not ok:
                    try:
                        import pyautogui
                        pyautogui.FAILSAFE = False
                        pyautogui.PAUSE = 0
                        pyautogui.press(key)
                        results.append(f"{key}=pyautogui OK")
                        ok = True
                    except Exception as e:
                        results.append(f"{key}=pyautogui 실패({e})")

                time.sleep(0.15)

            result_str = " | ".join(results)
            self.root.after(0, lambda: self.lbl_test.config(
                text=f"결과: {result_str}", fg=SUCCESS if "OK" in result_str else ERROR
            ))
            self.root.after(0, lambda: self._log(f"키 테스트: {result_str}"))
            if "실패" in result_str and is_win:
                self.root.after(0, lambda: self._log("→ 관리자 권한으로 실행해보세요! (우클릭→관리자 권한으로 실행)"))

        threading.Thread(target=do_test, daemon=True).start()

    # ═══════════ 봇 루프 ═══════════

    def _bot_loop(self):
        """메인 봇 루프 - 위치 기반 판정"""
        perf = time.perf_counter

        # ── 설정값 캐싱 ──
        region = {
            "x": self.var_cap_x.get(),
            "y": self.var_cap_y.get(),
            "width": self.var_cap_w.get(),
            "height": self.var_cap_h.get(),
        }
        lane_count = self.var_lane_count.get()
        hsv_lower = [self.var_h_low.get(), self.var_s_low.get(), self.var_v_low.get()]
        hsv_upper = [self.var_h_high.get(), self.var_s_high.get(), self.var_v_high.get()]
        judge_ratio = self.var_judge_ratio.get()
        offset_px = self.var_offset_px.get()
        judge_update_counter = 0

        exc_w = self.var_exc_w.get()
        exc_h = self.var_exc_h.get()
        exclude_rect = None
        if exc_w > 0 and exc_h > 0:
            exclude_rect = {
                "x": self.var_exc_x.get(),
                "y": self.var_exc_y.get(),
                "width": exc_w,
                "height": exc_h,
            }

        # ── 레인별 상태 ──
        holding = [False] * lane_count
        hold_seen = [0.0] * lane_count
        pressed = [False] * lane_count
        track_y = [0.0] * lane_count

        # ── 판정 상수 ──
        HIT_ABOVE = 0       # 판정선 도달 후에만 입력 (예측 없음)
        HIT_BELOW = 18      # 판정선 아래 18px까지 허용
        HOLD_GRACE = 0.03   # 롱노트 감지 끊김 허용 (30ms)

        last_log_time = 0.0
        frame_count = 0
        preview_open = self._preview_win is not None

        while self._running and not self._stop_event.is_set():
            try:
                self.input_mgr.tick()
                frame = self.capture.capture(region)
                if frame is None or frame.size == 0:
                    continue

                h, w = frame.shape[:2]

                judge_update_counter += 1
                if judge_update_counter % 10 == 0:
                    judge_ratio = self.var_judge_ratio.get()
                    offset_px = self.var_offset_px.get()
                judge_y = int(h * judge_ratio) + offset_px

                build_debug = preview_open and frame_count % 10 == 0
                notes = self.detector.detect(
                    frame=frame,
                    lane_count=lane_count,
                    hsv_lower=hsv_lower,
                    hsv_upper=hsv_upper,
                    min_note_size=10,
                    judge_line_y=judge_y,
                    exclude_rect=exclude_rect,
                    build_debug=build_debug,
                )

                now = perf()
                self._note_count = len(notes)
                self._fps_display = self.capture.fps
                frame_count += 1

                # ── 노트 선택: 이미 친 노트 + 지나간 노트 제외 ──
                dead_y = judge_y + HIT_BELOW
                best = [None] * lane_count
                for note in notes:
                    li = note.lane
                    if li >= lane_count:
                        continue
                    if not holding[li]:
                        ref = note.bottom if note.is_long else note.center_y
                        if ref > dead_y:
                            continue
                        # 이미 입력한 노트가 판정선 아래 → 무시 (새 노트 우선)
                        if pressed[li] and ref > judge_y:
                            continue
                    if best[li] is None or note.center_y > best[li].center_y:
                        best[li] = note

                normal_press = set()
                long_press = set()
                release_set = set()

                for li in range(lane_count):
                    note = best[li]

                    # ── 1) 노트 없음 ──
                    if note is None:
                        if holding[li] and now - hold_seen[li] > HOLD_GRACE:
                            release_set.add(li)
                            holding[li] = False
                        continue

                    # ── 2) 롱노트 홀드 중 ──
                    if holding[li]:
                        # 새 노트가 판정선 위 40px 이상 → 홀드 해제
                        if note.center_y < judge_y - 40:
                            release_set.add(li)
                            holding[li] = False
                            pressed[li] = False
                            continue
                        hold_seen[li] = now
                        # 꼬리(상단)가 판정선 도달 → 홀드 해제
                        if note.y >= judge_y:
                            release_set.add(li)
                            holding[li] = False
                        continue

                    # ── 3) 새 노트 감지 (위치가 12px 이상 위로 점프) ──
                    if pressed[li] and note.center_y < track_y[li] - 12:
                        pressed[li] = False
                    track_y[li] = note.center_y

                    if pressed[li]:
                        continue

                    # ── 4) 히트 판정 (판정선 도달 후 입력) ──
                    hit_ref = note.bottom if note.is_long else note.center_y
                    dist = judge_y - hit_ref

                    if -HIT_BELOW <= dist <= HIT_ABOVE:
                        pressed[li] = True
                        if note.is_long:
                            long_press.add(li)
                            holding[li] = True
                            hold_seen[li] = now
                        else:
                            normal_press.add(li)

                # ── 키 입력 실행 ──
                if normal_press or long_press:
                    self.input_mgr.press_lanes_batch(normal_press, long_press)
                if release_set:
                    self.input_mgr.release_lanes_batch(release_set)

                # ── 주기적 로그 ──
                if now - last_log_time > 3.0:
                    last_log_time = now
                    preview_open = self._preview_win is not None
                    self._log(
                        f"노트:{len(notes)}개 | FPS:{self.capture.fps:.0f} | "
                        f"입력:{self.input_mgr.press_count}"
                    )

            except Exception as e:
                self._log(f"오류: {e}")
                time.sleep(0.05)

    def _close_preview_window(self):
        if self._preview_win is not None:
            try:
                self._preview_win.destroy()
            except Exception:
                pass
            self._preview_win = None
            self._preview_canvas = None

    # ═══════════ 미리보기 ═══════════

    def _update_preview(self):
        if not self._running:
            return
        try:
            # 미리보기 창이 열려있을 때만 업데이트
            if self._preview_win is not None and self._preview_canvas is not None:
                debug_frame = self.detector.debug_frame
                if debug_frame is not None and Image is not None:
                    try:
                        pw = self._preview_canvas.winfo_width()
                        ph = self._preview_canvas.winfo_height()
                    except tk.TclError:
                        self._preview_win = None
                        self._preview_canvas = None
                        pw, ph = 0, 0
                    if pw > 10 and ph > 10:
                        rgb = cv2.cvtColor(debug_frame, cv2.COLOR_BGR2RGB)
                        img = Image.fromarray(rgb).resize((pw, ph), Image.Resampling.NEAREST)
                        photo = ImageTk.PhotoImage(img)
                        self._preview_canvas.config(image=photo, text="")
                        self._preview_photo = photo  # 참조 유지
        except Exception:
            pass

        self._update_status()
        if self._running:
            self.root.after(33, self._update_preview)

    def _update_status(self):
        try:
            self.lbl_status.config(text=f"상태: {self._status}")
            self.lbl_fps.config(text=f"FPS: {self._fps_display:.0f}")
            self.lbl_notes.config(text=f"노트: {self._note_count}")
            pc = self.input_mgr.press_count
            active = self.input_mgr.active_lanes
            keys = self.input_mgr.key_bindings
            key_str = ", ".join(keys[i] if i < len(keys) else "?" for i in active) if active else "-"
            self.lbl_keys.config(text=f"입력: {pc} | 키: {key_str}")
        except Exception:
            pass

    # ═══════════ 설정 ═══════════

    def _gui_to_config(self):
        self.config.set("capture_region", {
            "x": self.var_cap_x.get(), "y": self.var_cap_y.get(),
            "width": self.var_cap_w.get(), "height": self.var_cap_h.get(),
        })
        self.config.set("lane_count", self.var_lane_count.get())
        self.config.set("key_bindings", [k.strip() for k in self.var_keys.get().split(",")])
        self.config.set("judge_line_ratio", self.var_judge_ratio.get())
        self.config.set("input_delay_ms", self.var_delay.get())
        self.config.set("input_offset_px", self.var_offset_px.get())
        self.config.set("hsv_lower", [self.var_h_low.get(), self.var_s_low.get(), self.var_v_low.get()])
        self.config.set("hsv_upper", [self.var_h_high.get(), self.var_s_high.get(), self.var_v_high.get()])
        self.config.set("always_on_top", self.var_always_top.get())
        self.config.set("exclude_region", {
            "x": self.var_exc_x.get(), "y": self.var_exc_y.get(),
            "width": self.var_exc_w.get(), "height": self.var_exc_h.get(),
        })

    def _load_from_config(self):
        region = self.config.get("capture_region", {})
        x, y = region.get("x", 0), region.get("y", 0)
        w, h = region.get("width", 800), region.get("height", 600)
        if w > 20 and h > 20:
            self.lbl_region.config(
                text=f"영역: ({x}, {y}) → ({x+w}, {y+h})  [{w} x {h}]",
                fg=SUCCESS
            )

    def _save_config(self):
        try:
            self._gui_to_config()
            self.config.save()
            self._log("설정 저장 완료!")
        except Exception as e:
            self._log(f"저장 실패: {e}")

    def _reset_config(self):
        if messagebox.askyesno("확인", "설정을 기본값으로 초기화할까요?"):
            self.config.reset()
            self._init_vars()
            self._picked_color_bgr = None
            self.color_preview.config(bg="#555555")
            self.lbl_color_info.config(text="미추출", fg="#999999")
            self.lbl_region.config(text="영역: 미설정", fg="#999999")
            self._log("설정 초기화 완료")

    # ═══════════ 로그 ═══════════

    def _log(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        try:
            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, line + "\n")
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)
            lines = int(self.log_text.index("end-1c").split(".")[0])
            if lines > 50:
                self.log_text.config(state=tk.NORMAL)
                self.log_text.delete("1.0", "2.0")
                self.log_text.config(state=tk.DISABLED)
        except Exception:
            pass

    # ═══════════ 종료 ═══════════

    def _on_close(self):
        self._stop_bot()
        self._save_config()
        self._close_preview_window()
        try:
            self.root.destroy()
        except Exception:
            pass

    def run(self):
        self._log("리듬게임 자동 봇 준비 완료!")
        self._log("STEP 1~4를 순서대로 설정 후 시작 버튼을 누르세요.")
        self._log("ESC 키 = 긴급 종료")
        self.root.mainloop()
