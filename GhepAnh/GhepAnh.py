#!/usr/bin/env python3
"""Điều khiển các bước cắt ảnh và nhúng giao diện ghép PSD."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

ROOT = Path(__file__).resolve().parent.parent
CUT_DIR = ROOT / "Cắt"
GUN_DIR = ROOT / "DienLV" / "standalone"
PSD_DIR = ROOT / "GhepPSD"
sys.path.insert(0, str(CUT_DIR))
sys.path.insert(0, str(PSD_DIR))

import Start as cut_tool  # noqa: E402
import GhepPSD as psd_tool  # noqa: E402


class Dashboard:
    BG = "#11111b"
    PANEL = "#1e1e2e"
    TEXT = "#cdd6f4"
    BLUE = "#89b4fa"
    GREEN = "#a6e3a1"

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("GHÉP ẢNH ACC | Bảng điều khiển")
        root.geometry("1060x860")
        root.minsize(880, 720)
        root.configure(bg=self.BG)
        self.account = tk.StringVar()
        self.status = tk.StringVar(value="Sẵn sàng")
        self.cut_running = False
        self.move_running = False
        self._build()

    def label(self, parent, value, size=10, color=None, bold=False):
        return tk.Label(parent, text=value, bg=parent.cget("bg"), fg=color or self.TEXT,
                        anchor="w", justify="left",
                        font=("Segoe UI", size, "bold" if bold else "normal"))

    def button(self, parent, value, action, color):
        return tk.Button(parent, text=value, command=action, bg=color, fg=self.BG,
                         activebackground="white", relief="flat", padx=14, pady=7,
                         font=("Segoe UI", 10, "bold"))

    def _build(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("Ghep.TNotebook", background=self.BG, borderwidth=0)
        style.configure("Ghep.TNotebook.Tab", background=self.PANEL, foreground=self.TEXT,
                        padding=(20, 10), font=("Segoe UI", 10, "bold"))
        style.map("Ghep.TNotebook.Tab", background=[("selected", self.BLUE)],
                  foreground=[("selected", self.BG)])
        tabs = ttk.Notebook(self.root, style="Ghep.TNotebook")
        tabs.pack(fill="both", expand=True, padx=12, pady=12)
        workflow = tk.Frame(tabs, bg=self.BG, padx=20, pady=17)
        compose = tk.Frame(tabs, bg=self.BG)
        tabs.add(workflow, text="Cắt ảnh và tạo súng")
        tabs.add(compose, text="Ghép PSD")
        self.tabs = tabs

        self.label(workflow, "GHÉP ẢNH ACC", 20, self.BLUE, True).pack(anchor="w")
        self.label(workflow, "Điều khiển các bước chính ngay tại đây.", color="#a6adc8").pack(anchor="w", pady=(2, 15))
        acc_row = tk.Frame(workflow, bg=self.PANEL, padx=14, pady=12)
        acc_row.pack(fill="x", pady=(0, 12))
        self.label(acc_row, "MÃ ACC", bold=True).pack(side="left")
        tk.Entry(acc_row, textvariable=self.account, font=("Segoe UI", 12),
                 bg="#313244", fg="white", insertbackground="white", relief="flat",
                 width=25).pack(side="left", padx=(16, 12), fill="x", expand=True)
        self.label(acc_row, "Dùng chung với tab Ghép PSD", 9, "#a6adc8").pack(side="left")

        self.step(workflow, "01", "Chuyển ảnh súng", "Sung.py chuyển ảnh Xưởng Súng sang DienLV/standalone/input.",
                  [("Chạy chuyển ảnh súng", self.move_guns, self.BLUE)])
        self.step(workflow, "02", "Cắt ảnh", "Start.py cắt ảnh trong Cắt/input vào Cắt/output/<mã acc>.",
                  [("Bắt đầu cắt", self.start_cut, self.GREEN),
                   ("Xóa ảnh input", self.delete_input, "#f38ba8")])
        self.step(workflow, "03", "Tạo ảnh súng", "DienLV.exe xử lý ảnh súng trong thư mục input của nó.",
                  [("Mở DienLV.exe", self.open_dienlv, self.GREEN)])
        self.step(workflow, "04", "Ghép PSD", "Toàn bộ chức năng GhepPSD.py nằm trong tab Ghép PSD.",
                  [("Sang tab Ghép PSD", lambda: tabs.select(compose), self.BLUE)])

        folders = tk.Frame(workflow, bg=self.BG)
        folders.pack(fill="x", pady=(6, 9))
        for title, path in (("Ảnh gốc", CUT_DIR / "input"),
                            ("Ảnh súng", GUN_DIR / "input"),
                            ("Ảnh đã cắt", CUT_DIR / "output"),
                            ("PSD kết quả", PSD_DIR / "KetQua")):
            tk.Button(folders, text=title, command=lambda p=path: self.open_folder(p),
                      bg="#313244", fg=self.TEXT, relief="flat", padx=12, pady=6).pack(side="left", padx=(0, 7))
        self.label(workflow, "NHẬT KÝ", 9, "#a6adc8", True).pack(anchor="w")
        log_frame = tk.Frame(workflow, bg=self.PANEL)
        log_frame.pack(fill="both", expand=True, pady=(4, 5))
        self.log = tk.Text(log_frame, height=7, bg=self.PANEL, fg=self.TEXT,
                           font=("Consolas", 9), wrap="word", relief="flat", state="disabled")
        self.log.pack(side="left", fill="both", expand=True, padx=8, pady=6)
        scroll = tk.Scrollbar(log_frame, command=self.log.yview)
        scroll.pack(side="right", fill="y")
        self.log.configure(yscrollcommand=scroll.set)
        tk.Label(workflow, textvariable=self.status, bg=self.BG, fg=self.GREEN,
                 font=("Segoe UI", 9)).pack(anchor="w")
        self.append("Sẵn sàng. Mã acc được dùng chung ở cả hai tab.")
        self.psd_gui = psd_tool.ComposeGUI(compose, account_variable=self.account)

    def step(self, parent, number, title, description, buttons):
        card = tk.Frame(parent, bg=self.PANEL, padx=15, pady=12)
        card.pack(fill="x", pady=(0, 8))
        heading = tk.Frame(card, bg=self.PANEL)
        heading.pack(fill="x")
        self.label(heading, number, 13, self.BLUE, True).pack(side="left", padx=(0, 10))
        self.label(heading, title, 12, bold=True).pack(side="left")
        for label, action, color in reversed(buttons):
            self.button(heading, label, action, color).pack(side="right", padx=(7, 0))
        self.label(card, description, 9, "#a6adc8").pack(anchor="w", pady=(6, 0))

    def append(self, line):
        self.log.configure(state="normal")
        self.log.insert("end", str(line).rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def busy(self):
        return self.cut_running or self.move_running

    def move_guns(self):
        if self.busy():
            messagebox.showinfo("Đang xử lý", "Hãy đợi bước hiện tại hoàn tất.", parent=self.root)
            return
        script = CUT_DIR / "Sung.py"
        if not script.is_file():
            messagebox.showerror("Thiếu tool", str(script), parent=self.root)
            return
        self.move_running = True
        self.status.set("Đang chuyển ảnh súng...")
        self.append("[CHẠY] Sung.py")

        def worker():
            try:
                result = subprocess.run([sys.executable, str(script)], cwd=CUT_DIR,
                                        capture_output=True, text=True, encoding="utf-8",
                                        errors="replace",
                                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                output = (result.stdout + result.stderr).strip()
                self.root.after(0, lambda: self.finish_move(result.returncode, output))
            except OSError as exc:
                self.root.after(0, lambda error=str(exc): self.finish_move(1, error))

        threading.Thread(target=worker, daemon=True).start()

    def finish_move(self, code, output):
        self.move_running = False
        if output:
            self.append(output)
        self.status.set("Đã chuyển ảnh súng" if code == 0 else "Chuyển ảnh súng gặp lỗi")
        if code:
            messagebox.showerror("Sung.py gặp lỗi", "Xem nhật ký bên dưới.", parent=self.root)

    def start_cut(self):
        if self.busy():
            messagebox.showinfo("Đang xử lý", "Hãy đợi bước hiện tại hoàn tất.", parent=self.root)
            return
        try:
            account = cut_tool.validate_account_id(self.account.get())
        except ValueError as exc:
            messagebox.showwarning("Mã acc chưa hợp lệ", str(exc), parent=self.root)
            return
        if not cut_tool.list_source_images():
            messagebox.showinfo("Thiếu ảnh", f"Chưa có ảnh trong {CUT_DIR / 'input'}", parent=self.root)
            return
        self.cut_running = True
        self.status.set(f"Đang cắt acc {account}...")
        self.append(f"[CHẠY] Start.py cho acc {account}")

        def worker():
            try:
                result = cut_tool.process_all_for_account(
                    acc_id=account,
                    log_fn=lambda value: self.root.after(0, lambda text=value: self.append(text)))
                self.root.after(0, lambda: self.finish_cut(account, result, None))
            except Exception as exc:
                self.root.after(0, lambda error=str(exc): self.finish_cut(account, None, error))

        threading.Thread(target=worker, daemon=True).start()

    def finish_cut(self, account, result, error):
        self.cut_running = False
        if error:
            self.status.set("Cắt ảnh gặp lỗi")
            self.append("[LỖI] " + error)
            messagebox.showerror("Cắt ảnh gặp lỗi", error, parent=self.root)
        else:
            self.status.set(f"Đã cắt xong acc {account}")
            self.append(f"[XONG] Ảnh acc {account}: {result['output_dir']}")
            messagebox.showinfo("Đã cắt xong", f"Kết quả: {result['output_dir']}", parent=self.root)

    def delete_input(self):
        if self.busy():
            messagebox.showwarning("Đang xử lý", "Hãy đợi bước hiện tại hoàn tất.", parent=self.root)
            return
        images = cut_tool.list_source_images()
        if not images:
            messagebox.showinfo("Không có ảnh", "Thư mục Cắt/input đang trống.", parent=self.root)
            return
        if not messagebox.askyesno("Xác nhận xóa input",
                                   f"Xóa vĩnh viễn {len(images)} ảnh trong {CUT_DIR / 'input'}?\n"
                                   "Ảnh đã cắt và ảnh súng đã chuyển sẽ không bị xóa.",
                                   icon="warning", parent=self.root):
            return
        deleted, failed = 0, []
        for path in images:
            try:
                os.remove(path)
                deleted += 1
            except OSError as exc:
                failed.append(f"{path}: {exc}")
        self.append(f"[XÓA INPUT] {deleted}/{len(images)} ảnh.")
        if failed:
            self.append("\n".join(failed))
            messagebox.showwarning("Xóa chưa hết", f"Còn {len(failed)} ảnh lỗi. Xem nhật ký.", parent=self.root)
        else:
            messagebox.showinfo("Đã xóa", f"Đã xóa {deleted} ảnh input.", parent=self.root)

    def open_dienlv(self):
        exe = GUN_DIR / "DienLV.exe"
        try:
            if not exe.is_file():
                raise FileNotFoundError(str(exe))
            subprocess.Popen([str(exe)], cwd=GUN_DIR)
        except OSError as exc:
            messagebox.showerror("Không mở được DienLV", str(exc), parent=self.root)
            return
        self.status.set("Đã mở DienLV.exe")
        self.append("[MỞ] DienLV.exe")

    def open_folder(self, path):
        if not path.is_dir():
            messagebox.showerror("Thiếu thư mục", str(path), parent=self.root)
            return
        try:
            os.startfile(path)
        except OSError as exc:
            messagebox.showerror("Không mở được thư mục", str(exc), parent=self.root)


def main():
    root = tk.Tk()
    Dashboard(root)
    root.mainloop()


if __name__ == "__main__":
    main()
