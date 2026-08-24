"""
碧潭能源管理系統 - 電腦版（水電瓦斯抄錶）
以 pywebview 開啟 web/index.html（跟線上版 https://wu8858009.github.io/bitan-energy-pro-live/
同一份介面與邏輯）。資料一律存在本機瀏覽器儲存（localStorage / IndexedDB），
透過 storage_path 導向執行檔同層的 data 資料夾，達成免安裝、可攜式：
複製整個資料夾（含 data/）到別台電腦，資料跟著走。
"""
import os
import sys

if sys.platform == "win32":
    # 讓程式正確感知系統 DPI 縮放，避免視窗被 Windows 自動縮放拉伸而顯示不完整。
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    # 部分電腦（虛擬機、遠端桌面或舊顯卡驅動）WebView2 的 GPU 合成渲染會出現
    # 畫面沒有正確繪製、看起來像被裁切的問題，強制關閉 GPU 加速改用軟體繪圖
    # 可以解決，效能影響對這種簡單介面可忽略不計。
    os.environ.setdefault(
        "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS",
        "--disable-gpu --disable-gpu-compositing --disable-software-rasterizer",
    )

import webview


def base_path():
    """使用者資料要放的位置：exe 同層目錄（打包後）或本檔案所在目錄（開發時）。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def resource_path(relative):
    """讀取隨程式打包的靜態資源（web/ 內的檔案）。"""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative)


def initial_window_size():
    """依實際螢幕大小決定視窗尺寸，避免在較小的螢幕（如筆電常見的
    1366x768）上視窗高度超出螢幕，導致底部導覽列被裁掉、看不到。"""
    default_w, default_h = 480, 860
    min_w, min_h = 380, 650
    try:
        screens = webview.screens
        if screens:
            screen = screens[0]
            # 預留工作列、視窗邊框與標題列的空間
            usable_w = screen.width - 60
            usable_h = screen.height - 90
            default_w = max(min_w, min(default_w, usable_w))
            default_h = max(min_h, min(default_h, usable_h))
    except Exception:
        pass
    return default_w, default_h, min_w, min_h


def main():
    data_dir = os.path.join(base_path(), "data")
    os.makedirs(data_dir, exist_ok=True)

    width, height, min_w, min_h = initial_window_size()
    webview.create_window(
        "碧潭能源管理系統",
        resource_path("web/index.html"),
        width=width,
        height=height,
        min_size=(min_w, min_h),
        background_color="#0d2140",
    )
    # private_mode=False + storage_path：讓 localStorage / IndexedDB（照片）
    # 實際寫入本機 data 資料夾並長期保存，而不是每次啟動都清空的無痕模式。
    webview.start(storage_path=data_dir, private_mode=False)


if __name__ == "__main__":
    main()
