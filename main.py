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

import subprocess
import tempfile
import urllib.request
import webbrowser

import webview


class Api:
    """提供給前端 JS 呼叫的橋接：開啟外部連結、下載並套用新版 exe。"""

    def open_url(self, url):
        webbrowser.open(url)

    def download_and_apply_update(self, download_url, target_version):
        """下載新版 exe 並排入更新：寫一個批次檔等本程式結束後覆蓋 exe 本體再重啟。
        只動 exe 檔案本身，絕不觸碰 data/ 資料夾。

        批次檔是在本程式結束後、脫離本程式監控下才實際執行覆蓋動作，這裡回傳的
        {"ok": True} 只代表「下載成功、更新已排程」，不代表覆蓋一定會成功
        （例如防毒軟體攔截、磁碟權限問題）。真正是否成功，靠 check_pending_update()
        在下次啟動時比對版本號來確認，交給前端顯示結果，避免謊報已更新成功。"""
        if not getattr(sys, "frozen", False):
            return {"ok": False, "error": "開發模式無法自動更新，請先打包成 exe 再測試"}
        try:
            exe_path = sys.executable
            tmp_exe = os.path.join(tempfile.gettempdir(), "bitan_update_download.exe")
            urllib.request.urlretrieve(download_url, tmp_exe)

            if os.path.getsize(tmp_exe) < 1024 * 1024:
                os.remove(tmp_exe)
                return {"ok": False, "error": "下載的檔案異常，請稍後再試"}

            marker_path = os.path.join(tempfile.gettempdir(), "bitan_update_marker.txt")
            with open(marker_path, "w", encoding="utf-8") as f:
                f.write(target_version)

            pid = os.getpid()
            bat_path = os.path.join(tempfile.gettempdir(), "bitan_apply_update.bat")
            script = (
                "@echo off\r\n"
                ":wait\r\n"
                f'tasklist /fi "PID eq {pid}" 2>nul | find "{pid}" >nul\r\n'
                "if not errorlevel 1 (\r\n"
                "  timeout /t 1 /nobreak >nul\r\n"
                "  goto wait\r\n"
                ")\r\n"
                f'move /y "{tmp_exe}" "{exe_path}" >nul\r\n'
                f'start "" "{exe_path}"\r\n'
                'del "%~f0"\r\n'
            )
            with open(bat_path, "w", encoding="mbcs") as f:
                f.write(script)

            subprocess.Popen(["cmd", "/c", bat_path], creationflags=subprocess.CREATE_NO_WINDOW)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def check_pending_update(self):
        """啟動時呼叫：檢查上次是否有排程過更新，回報版本號有沒有真的變成新版。"""
        marker_path = os.path.join(tempfile.gettempdir(), "bitan_update_marker.txt")
        if not os.path.exists(marker_path):
            return {"pending": False}
        try:
            with open(marker_path, "r", encoding="utf-8") as f:
                target = f.read().strip()
        finally:
            try:
                os.remove(marker_path)
            except Exception:
                pass
        return {"pending": True, "target": target}

    def quit_app(self):
        os._exit(0)


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
    1366x768）上視窗高度超出螢幕，導致底部導覽列被裁掉、看不到。

    介面本身是響應式設計，寬度到 700px 以上會變成雙欄卡片、1024px 以上三欄、
    1400px 以上四欄（跟線上版桌機瀏覽時一樣）。預設用桌機尺寸開窗，讓電腦版
    exe 一開就是電腦排版，不是手機直式那種單欄窄版。"""
    default_w, default_h = 1280, 860
    min_w, min_h = 760, 600
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
        js_api=Api(),
    )
    # private_mode=False + storage_path：讓 localStorage / IndexedDB（照片）
    # 實際寫入本機 data 資料夾並長期保存，而不是每次啟動都清空的無痕模式。
    webview.start(storage_path=data_dir, private_mode=False)


if __name__ == "__main__":
    main()
