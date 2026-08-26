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

import shutil
import subprocess
import tempfile
import time
import urllib.request
import webbrowser

import webview


class Api:
    """提供給前端 JS 呼叫的橋接：開啟外部連結、下載並套用新版 exe。"""

    def open_url(self, url):
        webbrowser.open(url)

    def download_and_apply_update(self, download_url, target_version):
        """下載新版 exe 並排入更新：寫一個批次檔等本程式結束後覆蓋 exe 本體再重啟。
        只動 exe 檔案本身，絕不觸碰 data/ 資料夾；下載成功後還會多備份一份
        data/ 到同層的 data_backup_before_update，就算真的出了什麼意外，
        資料也救得回來。

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

            data_dir = os.path.join(os.path.dirname(exe_path), "data")
            if os.path.isdir(data_dir):
                backup_dir = os.path.join(os.path.dirname(exe_path), "data_backup_before_update")
                try:
                    if os.path.isdir(backup_dir):
                        shutil.rmtree(backup_dir, ignore_errors=True)
                    shutil.copytree(data_dir, backup_dir)
                except Exception:
                    pass  # 備份是多一層保險，備份失敗也不該擋下正常更新

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
        """關閉程式（目前只有自動更新流程會呼叫，關閉後由批次檔套用新版 exe）。

        原本直接 os._exit(0) 是硬殺行程，WebView2 的 IndexedDB（含每日記錄/
        月結讀數的照片）寫入完成（transaction oncomplete）不等於已經真正落盤，
        硬殺可能讓剛存的照片來不及寫進磁碟就消失。改成先正常關閉視窗，讓
        WebView2 走它自己的關閉流程把資料落盤，再等一小段緩衝時間，最後才
        os._exit 確保行程真的結束（批次檔要等行程消失才會覆蓋 exe）。"""
        try:
            if webview.windows:
                webview.windows[0].destroy()
        except Exception:
            pass
        time.sleep(0.6)
        os._exit(0)

    def export_report_pdf(self, suggested_name):
        """把目前畫面直接存成 PDF（呼叫前 JS 已經把要匯出的報表內容準備好顯示在
        #printReportArea，並靠 @media print CSS 只讓那個區塊在「列印檢視」下
        可見）。改用 WebView2 內建的 PrintToPdfAsync，不透過瀏覽器列印對話框：
        使用者不用每次手動關閉「頁首及頁尾」，也不會印出網址、日期、頁碼這些
        瀏覽器自動加的東西。存檔位置固定在 exe 同層的「報表匯出」資料夾，存完
        直接用系統預設的 PDF 開啟程式打開，方便馬上看到結果。"""
        try:
            import clr

            clr.AddReference("System.Windows.Forms")
            from System import Func, Type

            from webview.platforms import winforms as _wf

            win = webview.windows[0]
            browser_view = _wf.BrowserView.instances[win.uid]
            webview_ctrl = browser_view.browser.webview
            core = webview_ctrl.CoreWebView2

            save_dir = os.path.join(base_path(), "報表匯出")
            os.makedirs(save_dir, exist_ok=True)
            safe_name = "".join(c for c in suggested_name if c not in '\\/:*?"<>|').strip() or "報表"
            if not safe_name.lower().endswith(".pdf"):
                safe_name += ".pdf"
            path = os.path.join(save_dir, safe_name)
            base_p, ext = os.path.splitext(path)
            n = 1
            while os.path.exists(path):
                path = f"{base_p}({n}){ext}"
                n += 1

            holder = {}

            def _start():
                settings = core.Environment.CreatePrintSettings()
                settings.ShouldPrintHeaderAndFooter = False
                settings.ShouldPrintBackgrounds = True
                holder["task"] = core.PrintToPdfAsync(path, settings)
                return True

            webview_ctrl.Invoke(Func[Type](_start))
            ok = holder["task"].Result
            if not ok:
                return {"ok": False, "error": "WebView2 回報存檔失敗"}
            try:
                os.startfile(path)
            except Exception:
                pass
            return {"ok": True, "path": path}
        except Exception as e:
            return {"ok": False, "error": str(e)}


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


def index_url():
    """回傳 index.html 路徑，並帶上依檔案內容算出的雜湊當查詢參數。

    data_dir（storage_path）跨版本沿用同一個 WebView2 設定檔，Chromium 對
    file:// 也會用磁碟快取；曾實際發生過使用者更新到新版 exe，畫面卻還是
    讀到舊版快取內容的狀況（新版 exe 裡的 index.html 明明是對的）。用內容
    雜湊當查詢字串，內容一變網址就變，強迫換版時一定是快取未命中。"""
    path = resource_path("web/index.html")
    try:
        import hashlib

        with open(path, "rb") as f:
            digest = hashlib.md5(f.read()).hexdigest()[:12]
    except Exception:
        digest = str(int(os.path.getmtime(path)))
    return f"{path}?v={digest}"


def initial_window_size():
    """依實際螢幕大小決定視窗尺寸與置中位置，讓視窗大致佔滿螢幕的 85%（保留
    一些邊界，不做成滿版全螢幕），並在該螢幕正中央開啟；避免在較小的螢幕
    （如筆電常見的 1366x768）上視窗尺寸超出螢幕，導致內容被裁掉、看不到。

    介面本身是響應式設計，寬度到 700px 以上會變成雙欄卡片、1024px 以上三欄、
    1400px 以上四欄（跟線上版桌機瀏覽時一樣）。視窗跟著螢幕大小走，才能真正
    套用電腦版排版，不是固定小尺寸的手機直式單欄窄版。"""
    min_w, min_h = 760, 600
    default_w, default_h = 1280, 860  # 抓不到螢幕資訊時的備用尺寸
    screen = None
    try:
        screens = webview.screens
        if screens:
            screen = screens[0]
            # 預留工作列、視窗邊框與標題列的空間
            usable_w = screen.width - 60
            usable_h = screen.height - 90
            target_w = int(screen.width * 0.85)
            target_h = int(screen.height * 0.85)
            default_w = max(min_w, min(target_w, usable_w))
            default_h = max(min_h, min(target_h, usable_h))
    except Exception:
        pass
    return default_w, default_h, min_w, min_h, screen


def main():
    data_dir = os.path.join(base_path(), "data")
    os.makedirs(data_dir, exist_ok=True)

    width, height, min_w, min_h, screen = initial_window_size()
    webview.create_window(
        "碧潭能源管理系統",
        index_url(),
        width=width,
        height=height,
        min_size=(min_w, min_h),
        background_color="#0d2140",
        js_api=Api(),
        screen=screen,  # 明確指定螢幕，確保視窗在該螢幕正中央開啟（含多螢幕情境）
        maximized=True,  # 一開就自動放大到最大化，width/height 只是還原（取消最大化）時的尺寸
    )
    # private_mode=False + storage_path：讓 localStorage / IndexedDB（照片）
    # 實際寫入本機 data 資料夾並長期保存，而不是每次啟動都清空的無痕模式。
    webview.start(storage_path=data_dir, private_mode=False)


if __name__ == "__main__":
    main()
