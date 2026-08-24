"""
製作電腦版免安裝軟體.py
------------------------
把 main.py（碧潭能源管理系統）打包成單一 .exe，雙擊即可執行、不需安裝 Python。

用法：
    python 製作電腦版免安裝軟體.py

打包完成後，執行檔會在 dist/ 資料夾內，發布時請把 exe 連同其旁邊自動產生的
data/ 資料夾一起複製給使用者，這樣抄表資料、照片才會跟著程式一起走
（免安裝、可攜式）。data/ 內是瀏覽器儲存（localStorage、IndexedDB 照片）。
"""
import os
import subprocess
import sys

APP_NAME = "碧潭能源管理系統"
ROOT = os.path.dirname(os.path.abspath(__file__))
MAIN_SCRIPT = os.path.join(ROOT, "main.py")
WEB_DIR = os.path.join(ROOT, "web")
ICON_PATH = os.path.join(ROOT, "icon.ico")  # 選用，若存在會用來當作 exe 圖示


def ensure_packages():
    required = ["webview", "PyInstaller"]
    pip_names = {"webview": "pywebview", "PyInstaller": "pyinstaller"}
    missing = []
    for mod in required:
        try:
            __import__(mod)
        except ImportError:
            missing.append(pip_names[mod])
    if missing:
        print(f"[安裝相依套件] {', '.join(missing)} ...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])


def build():
    ensure_packages()
    import PyInstaller.__main__

    if not os.path.isdir(WEB_DIR):
        print(f"[錯誤] 找不到 web/ 資料夾：{WEB_DIR}")
        sys.exit(1)

    args = [
        MAIN_SCRIPT,
        "--name", APP_NAME,
        "--onefile",
        "--windowed",
        "--noconfirm",
        "--clean",
        "--add-data", f"{WEB_DIR}{os.pathsep}web",
    ]
    if os.path.exists(ICON_PATH):
        args += ["--icon", ICON_PATH]

    print("[開始打包] PyInstaller 執行中，請稍候...")
    PyInstaller.__main__.run(args)

    exe_path = os.path.join(ROOT, "dist", f"{APP_NAME}.exe")
    print("\n" + "=" * 50)
    if os.path.exists(exe_path):
        print(f"[完成] 已產生免安裝執行檔：\n  {exe_path}")
        print("提示：第一次執行 exe 時，會自動在同層目錄建立 data/ 資料夾")
        print("      （存放站點與抄錶資料、照片），")
        print("      發布給其他人時記得把 exe 跟 data/ 資料夾一起複製，資料才不會遺失。")
    else:
        print("[警告] 未在預期路徑找到 exe，請檢查上方輸出訊息是否有錯誤。")
    print("=" * 50)


if __name__ == "__main__":
    build()
