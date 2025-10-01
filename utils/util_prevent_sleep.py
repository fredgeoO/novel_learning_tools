import ctypes
import time

# Windows API 常量
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002

def prevent_sleep():
    """设置 Windows 不进入睡眠状态"""
    print("防休眠已开启，按 Ctrl+C 退出...")
    try:
        # 保持系统和显示器活跃
        ctypes.windll.kernel32.SetThreadExecutionState(
            ES_CONTINUOUS | ES_SYSTEM_REQUIRED
        )
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n程序已退出，系统将恢复正常休眠策略。")
        # 恢复默认状态
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)

if __name__ == "__main__":
    prevent_sleep()