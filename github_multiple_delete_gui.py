import threading
import queue
import requests
import tkinter as tk
from tkinter import messagebox
import ttkbootstrap as tb
from ttkbootstrap.constants import *
import os
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

API_BASE = "https://api.github.com"

class TokenManager:
    def __init__(self):
        self.cache_dir = os.path.expanduser("~/.github_cleaner")
        self.token_file = os.path.join(self.cache_dir, "token.enc")
        self.key_file = os.path.join(self.cache_dir, "key.dat")
        os.makedirs(self.cache_dir, exist_ok=True)
    
    def _get_key(self):
        if os.path.exists(self.key_file):
            with open(self.key_file, 'rb') as f:
                return f.read()
        key = Fernet.generate_key()
        with open(self.key_file, 'wb') as f:
            f.write(key)
        return key
    
    def save_token(self, token: str):
        if not token:
            return
        key = self._get_key()
        f = Fernet(key)
        encrypted = f.encrypt(token.encode())
        with open(self.token_file, 'wb') as file:
            file.write(encrypted)
    
    def load_token(self) -> str:
        if not os.path.exists(self.token_file):
            return ""
        try:
            key = self._get_key()
            f = Fernet(key)
            with open(self.token_file, 'rb') as file:
                encrypted = file.read()
            return f.decrypt(encrypted).decode()
        except Exception:
            return ""
    
    def clear_token(self):
        for file_path in [self.token_file, self.key_file]:
            if os.path.exists(file_path):
                os.remove(file_path)

class GitHubClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/vnd.github.v3+json"
        })
        self.username = None

    def set_token(self, token: str):
        if token:
            self.session.headers["Authorization"] = f"token {token}"
        elif "Authorization" in self.session.headers:
            del self.session.headers["Authorization"]

    def get_user(self) -> str:
        resp = self.session.get(f"{API_BASE}/user")
        resp.raise_for_status()
        data = resp.json()
        self.username = data.get("login")
        return self.username

    def list_owned_repos(self):
        repos = []
        page = 1
        while True:
            resp = self.session.get(
                f"{API_BASE}/user/repos",
                params={"per_page": 100, "page": page, "type": "owner"}
            )
            resp.raise_for_status()
            batch = resp.json()
            if not batch:
                break
            repos.extend([r["name"] for r in batch])
            page += 1
        return repos

    def delete_repo(self, repo_name: str) -> bool:
        if not self.username:
            self.get_user()
        resp = self.session.delete(f"{API_BASE}/repos/{self.username}/{repo_name}")
        if resp.status_code == 204:
            return True
        # Provide more context on common failures
        msg = f"HTTP {resp.status_code}"
        try:
            detail = resp.json().get("message")
            if detail:
                msg += f": {detail}"
        except Exception:
            pass
        raise requests.HTTPError(msg)

class App(tb.Window):
    def __init__(self):
        super().__init__(title="GitHub Repo Cleaner", themename="darkly")
        self.geometry("980x640")
        self.minsize(820, 560)

        self.client = GitHubClient()
        self.token_manager = TokenManager()
        self.ui_queue = queue.Queue()
        self._busy_count = 0
        self._gradient_anim_phase = 0

        self._build_ui()
        self._load_cached_token()
        self.after(50, self._process_ui_queue)

    def _switch_theme(self, name: str):
        try:
            tb.Style().theme_use(name)
        except Exception as e:
            messagebox.showerror("Theme Error", f"Could not switch theme to '{name}'.\n{e}")

    # UI construction
    def _build_ui(self):
        style = tb.Style()

        # Top gradient header with animated accent
        self._header_frame = tk.Frame(self, height=70, bd=0, highlightthickness=0)
        self._header_frame.pack(fill=tk.X, side=tk.TOP)
        self._header_canvas = tk.Canvas(self._header_frame, height=70, bd=0, highlightthickness=0)
        self._header_canvas.pack(fill=tk.BOTH, expand=True)
        self._header_canvas.bind("<Configure>", lambda e: self._draw_header_gradient())
        # Title text with emoji
        self._header_title = self._header_canvas.create_text(
            20, 35, anchor="w",
            text="🧹 GitHub Repo Cleaner",
            font=("Segoe UI", 20, "bold"),
            fill="#ffffff"
        )
        # Subtitle
        self._header_sub = self._header_canvas.create_text(
            360, 35, anchor="w",
            text="– Clean up multiple repositories swiftly",
            font=("Segoe UI", 11),
            fill="#e0e0e0"
        )
        self.after(60, self._animate_header)

        main = tb.Frame(self, padding=16)
        main.pack(fill=tk.BOTH, expand=True)

        tb.Separator(main).pack(fill=tk.X, pady=6)

        # Top controls row
        token_row = tb.Frame(main)
        token_row.pack(fill=tk.X, pady=(0, 10))

        tb.Label(token_row, text="🔐 Access Token:").pack(side=tk.LEFT)
        self.token_var = tk.StringVar()
        self.token_entry = tb.Entry(token_row, textvariable=self.token_var, show="•", width=50)
        self.token_entry.pack(side=tk.LEFT, padx=8, fill=tk.X, expand=True)
        load_btn = tb.Button(token_row, text="🔄 Load Repos", command=self.on_load_repos, bootstyle=PRIMARY)
        load_btn.pack(side=tk.LEFT)
        clear_btn = tb.Button(token_row, text="🗑️ Clear Cache", command=self.clear_token_cache, bootstyle=SECONDARY)
        clear_btn.pack(side=tk.LEFT, padx=(4, 0))
        # Tooltips
        _ToolTip(self.token_entry, "Enter your GitHub Personal Access Token (PAT)")
        _ToolTip(load_btn, "Authenticate and fetch your owned repositories")

        # Username + status + theme switcher
        status_row = tb.Frame(main)
        status_row.pack(fill=tk.X)
        self.user_var = tk.StringVar(value="User: -")
        self.status_var = tk.StringVar(value="Status: Idle")
        # status dot
        self._status_dot = tk.Canvas(status_row, width=12, height=12, bd=0, highlightthickness=0)
        self._status_dot.pack(side=tk.LEFT, padx=(0, 6))
        self._status_dot_id = self._status_dot.create_oval(2, 2, 10, 10, fill="#6c757d", outline="")
        tb.Label(status_row, textvariable=self.user_var, bootstyle=SECONDARY).pack(side=tk.LEFT)

        right_status = tb.Frame(status_row)
        right_status.pack(side=tk.RIGHT)
        tb.Label(right_status, text="Theme:").pack(side=tk.LEFT, padx=(0, 4))
        self.theme_var = tk.StringVar(value=style.theme.name)
        themes = [t for t in style.theme_names() if not t.startswith("_")]
        theme_combo = tb.Combobox(right_status, textvariable=self.theme_var, values=themes, width=16, state="readonly")
        theme_combo.pack(side=tk.LEFT)
        theme_combo.bind("<<ComboboxSelected>>", lambda e: self._switch_theme(self.theme_var.get()))
        tb.Label(right_status, textvariable=self.status_var, bootstyle=SECONDARY).pack(side=tk.LEFT, padx=8)

        # Filter + actions
        action_row = tb.Frame(main)
        action_row.pack(fill=tk.X, pady=(8, 8))
        tb.Label(action_row, text="🔎 Filter:").pack(side=tk.LEFT)
        self.filter_var = tk.StringVar()
        filter_entry = tb.Entry(action_row, textvariable=self.filter_var, width=30)
        filter_entry.pack(side=tk.LEFT, padx=6)
        filter_entry.bind("<KeyRelease>", lambda e: self.apply_filter())
        sel_all_btn = tb.Button(action_row, text="✅ Select All", command=self.select_all, bootstyle=SECONDARY)
        sel_all_btn.pack(side=tk.LEFT, padx=4)
        clr_btn = tb.Button(action_row, text="🧹 Clear Selection", command=self.clear_selection, bootstyle=SECONDARY)
        clr_btn.pack(side=tk.LEFT)
        del_btn = tb.Button(action_row, text="🗑️ Delete Selected", command=self.on_delete_selected, bootstyle=DANGER)
        del_btn.pack(side=tk.RIGHT)
        # Tooltips
        _ToolTip(filter_entry, "Type to filter repository names")
        _ToolTip(sel_all_btn, "Select all repos shown in the list")
        _ToolTip(clr_btn, "Clear the current selection")
        _ToolTip(del_btn, "Permanently delete the selected repositories")

        # Paned area: list on left, log on right
        paned = tb.Panedwindow(main, orient=tk.HORIZONTAL, bootstyle=LIGHT)
        paned.pack(fill=tk.BOTH, expand=True)

        # Left: repos list
        left = tb.Labelframe(paned, text="📦 Repositories", padding=8)
        paned.add(left, weight=1)
        self.listbox = tk.Listbox(left, selectmode=tk.EXTENDED, relief=tk.FLAT, borderwidth=0, highlightthickness=0)
        self.listbox.pack(fill=tk.BOTH, expand=True)
        yscroll = tb.Scrollbar(self.listbox, orient=tk.VERTICAL, command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=yscroll.set)
        yscroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Right: log
        right = tb.Labelframe(paned, text="📝 Activity Log", padding=8)
        paned.add(right, weight=1)
        self.log_text = tk.Text(right, height=10, wrap=tk.WORD, state=tk.DISABLED, relief=tk.FLAT, borderwidth=0, highlightthickness=0)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        # Log coloring tags
        self.log_text.tag_configure("ok", foreground="#28a745")
        self.log_text.tag_configure("err", foreground="#dc3545")
        self.log_text.tag_configure("info", foreground="#17a2b8")

        # Bottom: progress
        bottom = tb.Frame(main)
        bottom.pack(fill=tk.X, pady=(8, 0))
        self.progress = tb.Progressbar(bottom, mode="determinate", bootstyle=INFO)
        self.progress.pack(fill=tk.X)

        # Status bar
        tb.Separator(main).pack(fill=tk.X, pady=(10, 6))
        statusbar = tb.Frame(main)
        statusbar.pack(fill=tk.X)
        self.statusbar_label = tb.Label(statusbar, text="Ready", bootstyle=SECONDARY)
        self.statusbar_label.pack(side=tk.LEFT)

        # Data
        self.all_repos = []
        self.filtered_repos = []
    
    def _load_cached_token(self):
        cached_token = self.token_manager.load_token()
        if cached_token:
            self.token_var.set(cached_token)
    
    def clear_token_cache(self):
        self.token_manager.clear_token()
        self.token_var.set("")
        self.log("🗑️ Token cache cleared")

    # UI helpers
    def log(self, message: str):
        def _append():
            self.log_text.configure(state=tk.NORMAL)
            tag = None
            if message.startswith("✅"):
                tag = "ok"
            elif message.startswith("❌"):
                tag = "err"
            else:
                tag = "info"
            self.log_text.insert(tk.END, message + "\n", (tag,))
            self.log_text.see(tk.END)
            self.log_text.configure(state=tk.DISABLED)
        self.ui_queue.put(_append)

    def set_status(self, text: str):
        def _set():
            self.status_var.set(f"Status: {text}")
            self.statusbar_label.configure(text=f"{text}")
            # update status dot color
            color = "#0d6efd" if "Load" in text or "Authenticating" in text else ("#ffc107" if "Deleting" in text else ("#198754" if "Done" in text else "#6c757d"))
            try:
                self._status_dot.itemconfig(self._status_dot_id, fill=color)
            except Exception:
                pass
        self.ui_queue.put(_set)

    def set_user(self, username: str):
        self.ui_queue.put(lambda: self.user_var.set(f"User: {username}"))

    def set_repos(self, repos):
        self.all_repos = sorted(repos, key=str.lower)
        self.apply_filter()

    def apply_filter(self):
        query = self.filter_var.get().strip().lower()
        if query:
            self.filtered_repos = [r for r in self.all_repos if query in r.lower()]
        else:
            self.filtered_repos = list(self.all_repos)
        self.listbox.delete(0, tk.END)
        for r in self.filtered_repos:
            self.listbox.insert(tk.END, r)

    def select_all(self):
        self.listbox.select_set(0, tk.END)

    def clear_selection(self):
        self.listbox.selection_clear(0, tk.END)

    # Background worker pattern
    def _run_bg(self, target, *args, **kwargs):
        thread = threading.Thread(target=target, args=args, kwargs=kwargs, daemon=True)
        thread.start()

    def _process_ui_queue(self):
        while True:
            try:
                fn = self.ui_queue.get_nowait()
                fn()
            except queue.Empty:
                break
        self.after(50, self._process_ui_queue)

    # Visual helpers
    def _animate_header(self):
        # subtle animated gradient shift
        self._gradient_anim_phase = (self._gradient_anim_phase + 1) % 360
        self._draw_header_gradient()
        self.after(100, self._animate_header)

    def _draw_header_gradient(self):
        c = self._header_canvas
        c.delete("grad")
        w = c.winfo_width() or 980
        h = c.winfo_height() or 70
        # build horizontal gradient stripes
        steps = 64
        for i in range(steps):
            t = (i + self._gradient_anim_phase / 8) / steps
            # blue-purple gradient
            r = int(40 + 80 * t)
            g = int(70 + 30 * (1 - t))
            b = int(160 + 80 * (1 - abs(0.5 - t) * 2))
            color = f"#{r:02x}{g:02x}{b:02x}"
            x0 = int(i * w / steps)
            x1 = int((i + 1) * w / steps)
            c.create_rectangle(x0, 0, x1, h, fill=color, outline=color, tags="grad")
        # Keep title text on top
        try:
            c.tag_raise(self._header_title)
            c.tag_raise(self._header_sub)
        except Exception:
            pass

    def _start_busy(self):
        self._busy_count += 1
        try:
            self.progress.configure(mode="indeterminate")
            self.progress.start(12)
        except Exception:
            pass

    def _stop_busy(self):
        self._busy_count = max(0, self._busy_count - 1)
        if self._busy_count == 0:
            try:
                self.progress.stop()
                self.progress.configure(mode="determinate")
                self.progress.configure(value=0)
            except Exception:
                pass

    # Actions
    def on_load_repos(self):
        token = self.token_var.get().strip()
        if not token:
            if not messagebox.askyesno(
                "No Token Provided",
                "No token entered. Continue anyway? (Only public info will be accessible; deletion will fail)"
            ):
                return
        
        # Save token to encrypted cache
        if token:
            self.token_manager.save_token(token)
        
        self.client.set_token(token)
        self.set_status("Authenticating…")
        self.log("Authenticating with GitHub API…")
        self._start_busy()

        def work():
            try:
                username = self.client.get_user()
                self.set_user(username)
                self.set_status("Fetching repositories…")
                self.log("Fetching repositories you own…")
                repos = self.client.list_owned_repos()
                self.ui_queue.put(lambda: self.set_repos(repos))
                self.set_status(f"Loaded {len(repos)} repos")
                self.log(f"Loaded {len(repos)} repositories.")
            except Exception as e:
                self.set_status("Error")
                self.log(f"Error: {e}")
                messagebox.showerror("Error", f"Failed to load repositories.\n{e}")
            finally:
                self._stop_busy()
        self._run_bg(work)

    def on_delete_selected(self):
        selection = [self.filtered_repos[i] for i in self.listbox.curselection()]
        if not selection:
            messagebox.showinfo("Nothing Selected", "Please select one or more repositories to delete.")
            return

        # One more confirmation
        if not messagebox.askyesno(
            "Confirm Deletion",
            "You are about to permanently delete the selected repositories.\nThis cannot be undone.\n\nProceed?"
        ):
            return

        self.progress.configure(mode="determinate", maximum=len(selection), value=0)
        self.set_status("Deleting…")
        self.log(f"Deleting {len(selection)} repositories…")

        def work():
            deleted = 0
            errors = []
            for repo in selection:
                try:
                    self.client.delete_repo(repo)
                    deleted += 1
                    self.log(f"✅ Deleted {repo}")
                except Exception as e:
                    errors.append((repo, str(e)))
                    self.log(f"❌ Failed to delete {repo}: {e}")
                finally:
                    # update progress safely via queue
                    self.ui_queue.put(lambda v=deleted: self.progress.configure(value=v))

            # refresh list after deletions
            try:
                repos = self.client.list_owned_repos()
                self.ui_queue.put(lambda: self.set_repos(repos))
            except Exception as e:
                self.log(f"Warning: could not refresh repos: {e}")

            summary = f"Deleted: {deleted}, Failed: {len(errors)}"
            self.set_status("Done")
            self.log("=== Deletion Summary ===")
            self.log(summary)
            if errors:
                for r, err in errors:
                    self.log(f" - {r}: {err}")
            messagebox.showinfo("Completed", summary)
        self._run_bg(work)


# Simple tooltip helper (no external deps)
class _ToolTip:
    def __init__(self, widget, text: str, delay: int = 350):
        self.widget = widget
        self.text = text
        self.delay = delay
        self._id = None
        self._tip = None
        widget.bind("<Enter>", self._schedule)
        widget.bind("<Leave>", self._hide)
        widget.bind("<ButtonPress>", self._hide)

    def _schedule(self, _=None):
        self._cancel()
        self._id = self.widget.after(self.delay, self._show)

    def _cancel(self):
        if self._id:
            self.widget.after_cancel(self._id)
            self._id = None

    def _show(self):
        if self._tip or not self.text:
            return
        x, y, cx, cy = self.widget.bbox("insert") if hasattr(self.widget, "bbox") else (0, 0, 0, 0)
        x += self.widget.winfo_rootx() + 20
        y += self.widget.winfo_rooty() + 20
        self._tip = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        lbl = tk.Label(tw, text=self.text, background="#333", foreground="#fff", relief=tk.SOLID, borderwidth=1, padx=6, pady=3)
        lbl.pack()

    def _hide(self, _=None):
        self._cancel()
        if self._tip:
            self._tip.destroy()
            self._tip = None


if __name__ == "__main__":
    app = App()
    app.mainloop()
