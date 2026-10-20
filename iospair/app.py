"""iOSPair - one-button pairing-file generator for Windows."""

import asyncio
import os
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from tkinter import ttk

from iospair import __version__, core

ITUNES_URL = "https://www.apple.com/itunes/download/win64"

STATUS_TEXT = {
    "connecting": "جاري الاتصال بالجوال...",
    "unlock": "افتح قفل الجوال 🔓",
    "trust": "اضغط «وثوق» في الجوال واكتب رمز القفل\nTrust",
    "saving": "جاري حفظ الملف...",
}

BG = "#f5f6f8"
CARD = "#ffffff"
ACCENT = "#0a84ff"
OK = "#1f9d55"
ERR = "#d93025"
MUTED = "#6b7280"
FONT = "Segoe UI" if sys.platform == "win32" else "DejaVu Sans"


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.devices = []
        self.busy = False
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()

        root.title(f"iOSPair {__version__}")
        root.configure(bg=BG)
        root.geometry("460x440")
        root.minsize(420, 400)

        tk.Label(root, text="iOSPair", font=(FONT, 22, "bold"), bg=BG, fg="#111").pack(pady=(22, 0))
        tk.Label(root, text="ملف الاقتران للجوال", font=(FONT, 12), bg=BG, fg=MUTED).pack()

        card = tk.Frame(root, bg=CARD, highlightbackground="#e5e7eb", highlightthickness=1)
        card.pack(fill="x", padx=24, pady=18)

        self.device_label = tk.Label(card, text="", font=(FONT, 12), bg=CARD, fg="#111", wraplength=380)
        self.device_label.pack(pady=(16, 6), padx=12)

        self.device_box = ttk.Combobox(card, state="readonly", font=(FONT, 11), justify="center")
        self.device_box.bind("<<ComboboxSelected>>", lambda _e: self._update_button())

        self.button = tk.Button(
            card,
            text="طلّع ملف الاقتران",
            font=(FONT, 15, "bold"),
            bg=ACCENT,
            fg="white",
            activebackground="#0060df",
            activeforeground="white",
            disabledforeground="#dbeafe",
            relief="flat",
            cursor="hand2",
            command=self.start,
        )
        self.button.pack(fill="x", padx=16, pady=(8, 16), ipady=10)

        self.status = tk.Label(root, text="", font=(FONT, 12), bg=BG, fg=MUTED, wraplength=400, justify="center")
        self.status.pack(padx=24)

        self.extra = tk.Frame(root, bg=BG)
        self.extra.pack(pady=10)

        self.refresh()

    # -- background helpers -------------------------------------------------

    def run_async(self, coro, on_done):
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)

        def check():
            if future.done():
                on_done(future)
            else:
                self.root.after(100, check)

        check()

    def set_status(self, text, color=MUTED):
        self.status.config(text=text, fg=color)

    def clear_extra(self):
        for child in self.extra.winfo_children():
            child.destroy()

    # -- device detection ---------------------------------------------------

    def refresh(self):
        if not self.busy:
            self.run_async(core.list_devices(), self._on_devices)
        else:
            self.root.after(2000, self.refresh)

    def _on_devices(self, future):
        try:
            devices = future.result()
            missing_service = False
        except core.AppleServiceMissing:
            devices, missing_service = [], True
        except Exception:
            devices, missing_service = [], False

        if not self.busy:
            self._show_devices(devices, missing_service)
        self.root.after(2000, self.refresh)

    def _show_devices(self, devices, missing_service):
        changed = [d.udid for d in devices] != [d.udid for d in self.devices] or any(
            a.title != b.title for a, b in zip(devices, self.devices)
        )
        self.devices = devices

        if missing_service:
            self.device_label.config(text="لازم تثبّت iTunes أول مرة عشان الكمبيوتر يتعرف على الجوال", fg=ERR)
            if not getattr(self, "_itunes_shown", False):
                self.clear_extra()
                tk.Button(
                    self.extra,
                    text="تحميل iTunes",
                    font=(FONT, 11),
                    relief="flat",
                    bg="#e5e7eb",
                    cursor="hand2",
                    command=lambda: webbrowser.open(ITUNES_URL),
                ).pack(ipadx=10, ipady=4)
                self._itunes_shown = True
        else:
            if getattr(self, "_itunes_shown", False):
                self.clear_extra()
                self._itunes_shown = False
            if not devices:
                self.device_label.config(text="وصّل الجوال بالكمبيوتر بكيبل USB", fg=MUTED)
            elif len(devices) == 1:
                self.device_label.config(text=f"📱 {devices[0].title}", fg="#111")
            else:
                self.device_label.config(text="اختر الجوال", fg="#111")

        if len(devices) > 1:
            if changed:
                current = self.device_box.current()
                self.device_box["values"] = [d.title for d in devices]
                self.device_box.current(current if 0 <= current < len(devices) else 0)
            if not self.device_box.winfo_ismapped():
                self.device_box.pack(fill="x", padx=16, pady=(0, 4), before=self.button)
        elif self.device_box.winfo_ismapped():
            self.device_box.pack_forget()

        self._update_button()

    def _selected(self):
        if not self.devices:
            return None
        if len(self.devices) == 1:
            return self.devices[0]
        index = self.device_box.current()
        return self.devices[index] if 0 <= index < len(self.devices) else self.devices[0]

    def _update_button(self):
        enabled = bool(self.devices) and not self.busy
        self.button.config(state="normal" if enabled else "disabled", bg=ACCENT if enabled else "#9cc9ff")

    # -- pairing ------------------------------------------------------------

    def start(self):
        device = self._selected()
        if device is None or self.busy:
            return
        self.busy = True
        self._update_button()
        self.clear_extra()

        def status(key):
            self.root.after(0, self.set_status, STATUS_TEXT.get(key, key), ACCENT)

        self.run_async(core.generate(device.udid, core.default_output_dir(), status), self._on_done)

    def _on_done(self, future):
        self.busy = False
        self._update_button()
        try:
            result = future.result()
        except core.UserDenied:
            self.set_status("رفضت الاقتران في الجوال. اضغط الزر مرة ثانية واختر «وثوق».", ERR)
            return
        except core.TrustTimeout:
            self.set_status("انتهى الوقت. اضغط الزر مرة ثانية ووافق في الجوال.", ERR)
            return
        except core.AppleServiceMissing:
            self.set_status("ثبّت iTunes وأعد المحاولة.", ERR)
            return
        except Exception as e:
            self.set_status(f"صار خطأ، افصل الكيبل ووصّله وجرب مرة ثانية.\n{type(e).__name__}: {e}", ERR)
            return

        self.set_status("✔ تم! الملف جاهز", OK)
        self.clear_extra()
        tk.Button(
            self.extra,
            text="افتح المجلد",
            font=(FONT, 12, "bold"),
            relief="flat",
            bg=OK,
            fg="white",
            activebackground="#17803f",
            activeforeground="white",
            cursor="hand2",
            command=lambda: open_folder(result.folder),
        ).pack(ipadx=16, ipady=4)
        apps = []
        for _path, app in result.files:
            if app not in apps:
                apps.append(app)
        tk.Label(
            self.extra,
            text="\n".join(apps),
            font=(FONT, 9),
            bg=BG,
            fg=MUTED,
        ).pack(pady=(8, 0))
        open_folder(result.folder)


def open_folder(path):
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def main():
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
