"""Tkinter GUI for batch course video repair."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from video_recovery import __version__
from video_recovery.batch import process_directory
from video_recovery.ffmpeg_tools import ffmpeg_path, ffprobe_path


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"Video Recovery {__version__}")
        self.minsize(760, 520)
        self.geometry("900x620")

        self._log_queue: queue.Queue[str] = queue.Queue()
        self._cancel = threading.Event()
        self._worker: threading.Thread | None = None

        self.folder_var = tk.StringVar()
        self.mode_var = tk.StringVar(value="auto")
        self.recursive_var = tk.BooleanVar(value=True)
        self.only_needed_var = tk.BooleanVar(value=True)
        self.in_place_var = tk.BooleanVar(value=False)
        self.progress_var = tk.DoubleVar(value=0.0)
        self.status_var = tk.StringVar(value="Готово")

        self._build()
        self._refresh_ffmpeg_status()
        self.after(100, self._drain_log)

    def _build(self) -> None:
        pad = {"padx": 10, "pady": 6}
        root = ttk.Frame(self, padding=12)
        root.pack(fill=tk.BOTH, expand=True)

        folder_row = ttk.Frame(root)
        folder_row.pack(fill=tk.X, **pad)
        ttk.Label(folder_row, text="Папка курса:").pack(side=tk.LEFT)
        entry = ttk.Entry(folder_row, textvariable=self.folder_var)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 8))
        ttk.Button(folder_row, text="Обзор…", command=self._pick_folder).pack(
            side=tk.LEFT
        )

        opts = ttk.LabelFrame(root, text="Параметры", padding=10)
        opts.pack(fill=tk.X, **pad)

        mode_row = ttk.Frame(opts)
        mode_row.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(mode_row, text="Режим:").pack(side=tk.LEFT)
        mode = ttk.Combobox(
            mode_row,
            textvariable=self.mode_var,
            values=("auto", "remux", "reencode", "mkv"),
            state="readonly",
            width=12,
        )
        mode.pack(side=tk.LEFT, padx=(8, 0))
        ttk.Label(
            mode_row,
            text="auto — выбрать по анализу; remux — без перекодирования (обычно достаточно)",
        ).pack(side=tk.LEFT, padx=(12, 0))

        checks = ttk.Frame(opts)
        checks.pack(fill=tk.X)
        ttk.Checkbutton(
            checks, text="Рекурсивно по подпапкам", variable=self.recursive_var
        ).pack(side=tk.LEFT, padx=(0, 16))
        ttk.Checkbutton(
            checks,
            text="Чинить только проблемные (critical/high)",
            variable=self.only_needed_var,
        ).pack(side=tk.LEFT, padx=(0, 16))
        ttk.Checkbutton(
            checks,
            text="Заменять оригинал (.bak)",
            variable=self.in_place_var,
        ).pack(side=tk.LEFT)

        actions = ttk.Frame(root)
        actions.pack(fill=tk.X, **pad)
        self.analyze_btn = ttk.Button(
            actions, text="Только анализ", command=lambda: self._start(fix=False)
        )
        self.analyze_btn.pack(side=tk.LEFT)
        self.fix_btn = ttk.Button(
            actions, text="Исправить файлы", command=lambda: self._start(fix=True)
        )
        self.fix_btn.pack(side=tk.LEFT, padx=(8, 0))
        self.cancel_btn = ttk.Button(
            actions, text="Стоп", command=self._request_cancel, state=tk.DISABLED
        )
        self.cancel_btn.pack(side=tk.LEFT, padx=(8, 0))

        self.ffmpeg_label = ttk.Label(root, text="")
        self.ffmpeg_label.pack(anchor=tk.W, padx=10)

        prog = ttk.Frame(root)
        prog.pack(fill=tk.X, **pad)
        self.progress = ttk.Progressbar(prog, variable=self.progress_var, maximum=100)
        self.progress.pack(fill=tk.X, side=tk.LEFT, expand=True)
        ttk.Label(prog, textvariable=self.status_var, width=28).pack(
            side=tk.LEFT, padx=(8, 0)
        )

        log_frame = ttk.LabelFrame(root, text="Журнал", padding=6)
        log_frame.pack(fill=tk.BOTH, expand=True, **pad)
        self.log = tk.Text(log_frame, wrap=tk.WORD, height=20, state=tk.DISABLED)
        scroll = ttk.Scrollbar(log_frame, command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        self.log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        hint = ttk.Label(
            root,
            text=(
                "По умолчанию создаются файлы *_fixed.mp4 рядом с оригиналом. "
                "Нужны ffmpeg и ffprobe (на PATH или рядом с программой)."
            ),
            justify=tk.LEFT,
        )
        hint.pack(anchor=tk.W, padx=10, pady=(0, 4))

    def _refresh_ffmpeg_status(self) -> None:
        ff = ffmpeg_path()
        fp = ffprobe_path()
        if ff and fp:
            self.ffmpeg_label.configure(
                text=f"FFmpeg: OK  ({Path(ff).name}, {Path(fp).name})",
                foreground="#1a7f37",
            )
        else:
            missing = []
            if not ff:
                missing.append("ffmpeg")
            if not fp:
                missing.append("ffprobe")
            self.ffmpeg_label.configure(
                text=f"FFmpeg: не найден ({', '.join(missing)})",
                foreground="#cf222e",
            )

    def _pick_folder(self) -> None:
        path = filedialog.askdirectory(title="Выберите папку курса")
        if path:
            self.folder_var.set(path)

    def _append_log(self, message: str) -> None:
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, message + "\n")
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def _drain_log(self) -> None:
        while True:
            try:
                msg = self._log_queue.get_nowait()
            except queue.Empty:
                break
            self._append_log(msg)
        self.after(100, self._drain_log)

    def _set_busy(self, busy: bool) -> None:
        state = tk.DISABLED if busy else tk.NORMAL
        self.analyze_btn.configure(state=state)
        self.fix_btn.configure(state=state)
        self.cancel_btn.configure(state=tk.NORMAL if busy else tk.DISABLED)

    def _request_cancel(self) -> None:
        self._cancel.set()
        self.status_var.set("Остановка…")

    def _start(self, *, fix: bool) -> None:
        folder = self.folder_var.get().strip()
        if not folder:
            messagebox.showwarning("Папка", "Выберите папку курса.")
            return
        root = Path(folder)
        if not root.is_dir():
            messagebox.showerror("Папка", f"Не найдена папка:\n{root}")
            return
        if not ffmpeg_path() or not ffprobe_path():
            messagebox.showerror(
                "FFmpeg",
                "Не найдены ffmpeg/ffprobe.\n"
                "Установите FFmpeg и добавьте в PATH,\n"
                "либо положите ffmpeg.exe и ffprobe.exe рядом с программой.",
            )
            self._refresh_ffmpeg_status()
            return
        if self._worker and self._worker.is_alive():
            return

        self._cancel.clear()
        self._set_busy(True)
        self.progress_var.set(0)
        self.status_var.set("Работаю…")
        self._append_log("=" * 60)
        self._append_log(
            f"{'Исправление' if fix else 'Анализ'}: {root}  mode={self.mode_var.get()}"
        )

        def on_log(msg: str) -> None:
            self._log_queue.put(msg)

        def on_progress(index: int, total: int, path: Path) -> None:
            pct = (index / total) * 100 if total else 0
            self.after(
                0,
                lambda: (
                    self.progress_var.set(pct),
                    self.status_var.set(f"{index}/{total}  {path.name}"),
                ),
            )

        def work() -> None:
            try:
                result = process_directory(
                    root,
                    fix=fix,
                    only_if_needed=self.only_needed_var.get(),
                    mode=self.mode_var.get(),
                    recursive=self.recursive_var.get(),
                    in_place=self.in_place_var.get(),
                    log=on_log,
                    progress=on_progress,
                    should_cancel=self._cancel.is_set,
                )
                summary = (
                    f"Готово: fixed={result.fixed} skipped={result.skipped} "
                    f"failed={result.failed}"
                )
                self.after(0, lambda: self._finish(ok=result.failed == 0, summary=summary))
            except Exception as exc:  # noqa: BLE001
                self._log_queue.put(f"ERROR: {exc}")
                self.after(0, lambda: self._finish(ok=False, summary=str(exc)))

        self._worker = threading.Thread(target=work, daemon=True)
        self._worker.start()

    def _finish(self, *, ok: bool, summary: str) -> None:
        self._set_busy(False)
        self.progress_var.set(100 if ok else self.progress_var.get())
        self.status_var.set(summary if ok else f"Ошибки: {summary}")
        if ok:
            messagebox.showinfo("Готово", summary)
        else:
            messagebox.showwarning("Завершено с ошибками", summary)


def main() -> int:
    app = App()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
