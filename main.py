"""
리듬게임 자동 플레이 봇 - 메인 실행 파일
화면을 실시간 캡처하여 노트를 감지하고, 판정선 도달 시 자동으로 키를 입력합니다.

실행 방법:
    python main.py
"""

import sys
import os


def main():
    """메인 진입점"""
    # 필수 라이브러리 확인
    missing = []
    try:
        import cv2
    except ImportError:
        missing.append("opencv-python")
    try:
        import numpy
    except ImportError:
        missing.append("numpy")
    try:
        import mss
    except ImportError:
        missing.append("mss")
    try:
        from PIL import Image
    except ImportError:
        missing.append("Pillow")

    # keyboard 또는 pyautogui 중 하나 필요
    has_input = False
    try:
        import keyboard
        has_input = True
    except ImportError:
        pass
    try:
        import pyautogui
        has_input = True
    except ImportError:
        pass

    if not has_input:
        missing.append("keyboard 또는 pyautogui")

    if missing:
        print("=" * 50)
        print("다음 패키지가 필요합니다:")
        for m in missing:
            print(f"  - {m}")
        print()
        print("설치 명령:")
        print("  pip install opencv-python numpy mss Pillow keyboard pyautogui")
        print("=" * 50)
        sys.exit(1)

    # GUI 실행
    from gui import RhythmBotGUI

    try:
        app = RhythmBotGUI()
        app.run()
    except KeyboardInterrupt:
        print("\n프로그램이 종료되었습니다.")
    except Exception as e:
        print(f"오류 발생: {e}")
        import traceback
        traceback.print_exc()
        input("Enter 키를 눌러 종료...")


if __name__ == "__main__":
    main()
