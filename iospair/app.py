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
    "unlock": "افتح قفل الجوال",
    "trust": "اضغط «وثوق» في الجوال واكتب الرمز",
    "saving": "جاري الحفظ...",
}

BG = "#f5f6f8"
CARD = "#ffffff"
LINE = "#e5e7eb"
TEXT = "#111111"
ACCENT = "#0a84ff"
OK = "#1f9d55"
ERR = "#d93025"
MUTED = "#6b7280"
FONT = "Segoe UI" if sys.platform == "win32" else "DejaVu Sans"


def card(parent):
    frame = tk.Frame(parent, bg=CARD, highlightbackground=LINE, highlightthickness=1)
    frame.pack(fill="x", padx=20, pady=(0, 10))
    frame.columnconfigure(0, weight=1)
    return frame


class CheckRow:
    """One line of the check panel: text on the right, ✔ / ✖ / – icon at the far right."""

    def __init__(self, parent, row):
        self.icon = tk.Label(parent, font=(FONT, 12, "bold"), bg=CARD, width=2)
        self.icon.grid(row=row, column=2, sticky="e", padx=(0, 10), pady=3)
        self.text = tk.Label(parent, font=(FONT, 11), bg=CARD, anchor="e")
        self.text.grid(row=row, column=1, sticky="e", pady=3)
        self.action = None
        self.parent = parent
        self.row = row

    def set(self, state, text, action=None):
        icon, color = {"ok": ("✔", OK), "bad": ("✖", ERR), "wait": ("–", MUTED)}[state]
        self.icon.config(text=icon, fg=color)
        self.text.config(text=text, fg=TEXT if state == "ok" else color)
        label = action[0] if action else None
        if self.action is not None and self.action.cget("text") != label:
            self.action.destroy()
            self.action = None
        if action and self.action is None:
            self.action = tk.Button(
                self.parent, text=label, font=(FONT, 9), relief="flat", bg=LINE, cursor="hand2", command=action[1]
            )
            self.action.grid(row=self.row, column=0, sticky="w", padx=10)


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.devices = []
        self.busy = False
        # Devices already auto-paired while plugged in; cleared on unplug so a replug pairs again.
        self.handled = set()
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()

        root.title(f"iOSPair {__version__}")
        root.configure(bg=BG)
        root.geometry("440x520")
        root.minsize(400, 480)

        tk.Label(root, text="iOSPair", font=(FONT, 20, "bold"), bg=BG, fg=TEXT).pack(pady=(16, 10))

        checks = card(root)
        tk.Label(checks, text="الفحص", font=(FONT, 10, "bold"), bg=CARD, fg=MUTED).grid(
            row=0, column=1, columnspan=2, sticky="e", padx=10, pady=(8, 2)
        )
        self.check_service = CheckRow(checks, 1)
        self.check_device = CheckRow(checks, 2)
        self.check_ios = CheckRow(checks, 3)
        tk.Frame(checks, bg=CARD, height=6).grid(row=4, column=0)

        self.info = tk.Frame(root, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        self.info.columnconfigure(0, weight=1)
        self.device_box = ttk.Combobox(self.info, state="readonly", font=(FONT, 10), justify="center")
        self.device_box.bind("<<ComboboxSelected>>", lambda _e: self._show_info())
        self.info_rows = []
        for row, key in enumerate(("الاسم", "الجهاز", "الإصدار", "UDID"), start=1):
            tk.Label(self.info, text=key, font=(FONT, 10), bg=CARD, fg=MUTED, anchor="e").grid(
                row=row, column=1, sticky="e", padx=10, pady=2
            )
            value = tk.Label(self.info, font=(FONT, 10, "bold"), bg=CARD, fg=TEXT, anchor="w")
            value.grid(row=row, column=0, sticky="w", padx=10, pady=2)
            self.info_rows.append(value)
        tk.Frame(self.info, bg=CARD, height=4).grid(row=5, column=0)

        self.button = tk.Button(
            root,
            text="طلّع ملف الاقتران",
            font=(FONT, 14, "bold"),
            bg=ACCENT,
            fg="white",
            activebackground="#0060df",
            activeforeground="white",
            disabledforeground="#dbeafe",
            relief="flat",
            cursor="hand2",
            command=lambda: self.start(),
        )
        self.button.pack(fill="x", padx=20, pady=(4, 8), ipady=8)

        self.status = tk.Label(root, text="", font=(FONT, 11), bg=BG, fg=MUTED, wraplength=380, justify="center")
        self.status.pack(padx=20)

        self.extra = tk.Frame(root, bg=BG)
        self.extra.pack(pady=8)

        self._show_devices([], None)
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
            devices, service_ok = future.result(), True
        except core.AppleServiceMissing:
            devices, service_ok = [], False
        except Exception:
            devices, service_ok = [], True

        if not self.busy:
            self._show_devices(devices, service_ok)
        self.root.after(2000, self.refresh)

    def _show_devices(self, devices, service_ok):
        titles = [d.title for d in devices]
        changed = titles != [d.title for d in self.devices]
        self.devices = devices

        if service_ok is None:
            self.check_service.set("wait", "خدمة Apple")
        elif service_ok:
            self.check_service.set("ok", "iTunes مثبّت")
        else:
            self.check_service.set("bad", "iTunes غير مثبّت", ("تحميل", lambda: webbrowser.open(ITUNES_URL)))

        if devices:
            self.check_device.set("ok", "الجوال متصل")
        elif service_ok:
            self.check_device.set("bad", "وصّل الجوال بالكيبل")
        else:
            self.check_device.set("wait", "الجوال")

        if len(devices) > 1:
            if changed:
                current = self.device_box.current()
                self.device_box["values"] = titles
                self.device_box.current(current if 0 <= current < len(devices) else 0)
            self.device_box.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=(8, 4))
        else:
            self.device_box.grid_remove()

        if devices:
            self.info.pack(fill="x", padx=20, pady=(0, 10), before=self.button)
        else:
            self.info.pack_forget()
        self._show_info()
        self._auto_start()

    def _show_info(self):
        device = self._selected()
        if device is None:
            self.check_ios.set("wait", "الإصدار")
        elif device.supported:
            self.check_ios.set("ok", "الإصدار مدعوم")
        else:
            self.check_ios.set("bad", "الإصدار قديم جدًا")

        if device is not None:
            udid = device.udid if len(device.udid) <= 16 else f"{device.udid[:8]}…{device.udid[-6:]}"
            values = (device.name or "-", device.model_name, f"iOS {device.ios}" if device.ios else "-", udid)
            for label, value in zip(self.info_rows, values):
                label.config(text=value)
        self._update_button()

    def _auto_start(self):
        connected = {d.udid for d in self.devices}
        self.handled &= connected
        for index, device in enumerate(self.devices):
            if device.udid not in self.handled:
                self.handled.add(device.udid)
                if not device.supported:
                    continue
                if len(self.devices) > 1:
                    self.device_box.current(index)
                    self._show_info()
                self.start(device)
                return

    def _selected(self):
        if not self.devices:
            return None
        if len(self.devices) == 1:
            return self.devices[0]
        index = self.device_box.current()
        return self.devices[index] if 0 <= index < len(self.devices) else self.devices[0]

    def _update_button(self):
        device = self._selected()
        enabled = device is not None and device.supported and not self.busy
        self.button.config(state="normal" if enabled else "disabled", bg=ACCENT if enabled else "#9cc9ff")

    # -- pairing ------------------------------------------------------------

    def start(self, device=None):
        device = device or self._selected()
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
            self.set_status("رفضت الاقتران. اضغط الزر واختر «وثوق».", ERR)
            return
        except core.TrustTimeout:
            self.set_status("انتهى الوقت. اضغط الزر مرة ثانية.", ERR)
            return
        except core.AppleServiceMissing:
            self.set_status("ثبّت iTunes وأعد المحاولة.", ERR)
            return
        except Exception as e:
            self.set_status(f"صار خطأ. افصل الكيبل ووصّله.\n{type(e).__name__}: {e}", ERR)
            return

        self.set_status("✔ الملف جاهز", OK)
        self.clear_extra()
        tk.Button(
            self.extra,
            text="افتح المجلد",
            font=(FONT, 11, "bold"),
            relief="flat",
            bg=OK,
            fg="white",
            activebackground="#17803f",
            activeforeground="white",
            cursor="hand2",
            command=lambda: open_folder(result.folder),
        ).pack(ipadx=16, ipady=3)
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
