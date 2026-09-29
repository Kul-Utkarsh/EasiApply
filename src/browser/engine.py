import os
from pathlib import Path
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

# Smart stealth import to handle different package versions seamlessly
try:
    from playwright_stealth import stealth_sync
except ImportError:
    try:
        from playwright_stealth.sync import stealth_sync
    except ImportError:
        # Fallback if stealth plugin isn't present
        def stealth_sync(page):
            pass

load_dotenv()

class BrowserManager:
    def __init__(self):
        self.user_data_dir = os.getenv("USER_DATA_DIR", "./user_data")
        self.headless = os.getenv("HEADLESS", "False").lower() == "true"
        self.slow_mo = int(os.getenv("SLOW_MO_MS", 100))
        self.context = None
        self.browser = None
        self.playwright = None

    def start(self):
        self.playwright = sync_playwright().start()
        # Launch persistent context to keep login session with visible foreground settings
        launch_args = [
            "--start-maximized",
            "--window-position=40,40",
            "--window-size=1280,920",
            "--no-default-browser-check"
        ]
        self.browser = self.playwright.chromium.launch_persistent_context(
            user_data_dir=self.user_data_dir,
            headless=self.headless,
            slow_mo=self.slow_mo,
            args=launch_args,
            no_viewport=True  # Use maximized window
        )
        self._force_windows_foreground()
        return self.browser

    def new_page(self):
        # A persistent context automatically creates one page on startup.
        pages = self.browser.pages
        if pages:
            page = pages[0]
        else:
            page = self.browser.new_page()
        try:
            page.bring_to_front()
        except Exception:
            pass
        self._force_windows_foreground()
        stealth_sync(page) # Apply stealth protection
        return page

    def _force_windows_foreground(self):
        """Force the Chromium desktop window into the foreground on Windows."""
        import sys
        if sys.platform != "win32" or self.headless:
            return
        try:
            import ctypes
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32

            def enum_handler(hwnd, _):
                if user32.IsWindowVisible(hwnd):
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buff = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buff, length + 1)
                        title = buff.value.lower()
                        if "linkedin" in title or "chrome" in title or "chromium" in title:
                            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                            user32.ShowWindow(hwnd, 5)  # SW_SHOW
                            fore_thread = user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), None)
                            curr_thread = kernel32.GetCurrentThreadId()
                            if fore_thread != curr_thread:
                                user32.AttachThreadInput(fore_thread, curr_thread, True)
                                user32.BringWindowToTop(hwnd)
                                user32.SetForegroundWindow(hwnd)
                                user32.AttachThreadInput(fore_thread, curr_thread, False)
                            else:
                                user32.BringWindowToTop(hwnd)
                                user32.SetForegroundWindow(hwnd)
                return True

            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
            user32.EnumWindows(WNDENUMPROC(enum_handler), 0)
        except Exception:
            pass

    def stop(self):
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
