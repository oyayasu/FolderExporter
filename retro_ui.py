"""FolderExporter classic desktop interface (macOS and Windows, English only)."""
from __future__ import annotations
import base64
from pathlib import Path
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import tkinter.font as tkfont

from engine import Options, load_project
from workflow import (Naming, folder_tree, discover_drawings, is_organizer,
                      make_plan, export_plan, safe_stem)

FACE = "#C0C0C0"
LIGHT = "#FFFFFF"
SHADOW = "#808080"
DARK = "#404040"
NAVY = "#000080"
TEXT = "#161616"
INACTIVE = "#808080"
ENTRY = "#FFFFFF"
ICON_PNG = "iVBORw0KGgoAAAANSUhEUgAAACAAAAAbBAMAAADv6ZCpAAAAMFBMVEXWqmYkGBHllDf87HX08KqCaUD3xDnN1tUHBQLmizL2xkP+8ol+ZjnjkC6AZzv27InyHmPvAAAAEHRSTlP/////////AP//////////hG6+3wAAAN1JREFUeNpdkDFqAkEYhb/5dxpB4oQVglWihY2Fgb3AFtt7g+ABUliJTVjSpPYWlskBLKxsvcEK9jorVkLMplhhfn3d93gz8+aZmaMqCbIPBdLSBgmXo4oIEH0+1nKABehnnUbBy64zB/MVw6Vdx/82IHDOolPivR8mB1cnvHrEWzjrHk5gqthgAeNuilX5MSFdXfnDAk+eb/i1ACNLPm4vw4muMFEXkCFgBsF4K0X0GIBg4p9ALaSqP6wSzUWg5zHCncSsXwOUcNcDhDRACkj0HoztdfUb2X1P7Qf8A1WAMR5T10btAAAAAElFTkSuQmCC"


class ClassicButton(tk.Button):
    def __init__(self, parent, text, command, primary=False, **kwargs):
        super().__init__(parent, text=text, command=command, bg=FACE, fg=TEXT,
                         activebackground="#DCDCDC", activeforeground=TEXT,
                         relief="raised", bd=2, highlightthickness=0,
                         padx=12, pady=5 if primary else 3, takefocus=True,
                         cursor="hand2", **kwargs)


class Application(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("FolderExporter")
        self.geometry("1130x745")
        self.minsize(900, 600)
        self.configure(bg=FACE)
        families = {x.lower(): x for x in tkfont.families(self)}
        family = next((families[c.lower()] for c in
                       ("MS Sans Serif", "Chicago", "Geneva", "Tahoma", "Arial")
                       if c.lower() in families), "Arial")
        self.font_ui = (family, 10)
        self.font_small = (family, 9)
        self.font_heading = (family, 10, "bold")
        self.option_add("*Font", f"{{{family}}} 10")
        try:
            self.folder_icon = tk.PhotoImage(data=ICON_PNG, format="png")
            self.iconphoto(True, self.folder_icon)
        except tk.TclError:
            self.folder_icon = None

        self.source: Path | None = None
        self.project = None
        self.tree_nodes = []
        self.drawings = []
        self.selected: set[str] = set()
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.worker: threading.Thread | None = None
        self.loading = False

        self.file_label = tk.StringVar(value="No project selected")
        self.status = tk.StringVar(value="Ready. Choose a project to begin.")
        self.selection_label = tk.StringVar(value="0 drawings selected")
        self.keywords = tk.StringVar(value="chapter, section")
        self.separate = tk.BooleanVar(value=True)
        self.format_var = tk.StringVar(value="PNG")
        self.scale_var = tk.StringVar(value="100")
        self.quality_var = tk.StringVar(value="90")
        self.crop_var = tk.BooleanVar(value=False)
        self.white_var = tk.BooleanVar(value=False)
        self.jpeg_background = tk.StringVar(value="White")
        self.destination = tk.StringVar(value="")
        self.naming_mode = tk.StringVar(value="Format")
        self.naming_kind = tk.StringVar(value="Name and Index")
        self.naming_custom = tk.StringVar(value="Drawing")
        self.naming_where = tk.StringVar(value="after")
        self.naming_start = tk.StringVar(value="1")
        self.naming_padding = tk.StringVar(value="3")
        self.naming_separator = tk.StringVar(value=" - ")
        self.naming_reset = tk.BooleanVar(value=True)
        self.naming_add = tk.StringVar(value="")
        self.naming_search = tk.StringVar(value="")
        self.naming_replace = tk.StringVar(value="")
        self.preview_text = tk.StringVar(value="Open a file to preview export paths.")

        self._create_widgets()
        for var in (self.keywords,):
            var.trace_add("write", lambda *_: self._refresh_discovery())
        for var in (self.separate, self.destination, self.format_var, self.scale_var,
                    self.quality_var, self.crop_var, self.white_var, self.jpeg_background,
                    self.naming_mode, self.naming_kind, self.naming_custom,
                    self.naming_where, self.naming_start, self.naming_padding,
                    self.naming_separator, self.naming_reset, self.naming_add,
                    self.naming_search, self.naming_replace):
            var.trace_add("write", lambda *_: self._on_setting_changed())
        self.after(100, self._poll)
        self.protocol("WM_DELETE_WINDOW", self._close)
        if len(sys.argv) > 1 and Path(sys.argv[1]).is_file():
            self.after(200, lambda: self._open(Path(sys.argv[1])))

    def _text(self, parent, value, small=False, bold=False, **kwargs):
        return tk.Label(parent, text=value, bg=FACE, fg=TEXT,
                        font=(self.font_heading if bold else self.font_small if small else self.font_ui),
                        anchor="w", **kwargs)

    def _panel(self, parent, title, **pack):
        panel = tk.Frame(parent, bg=FACE, relief="raised", bd=2)
        panel.pack(**pack)
        self._text(panel, title, bold=True).pack(anchor="w", padx=12, pady=(9, 7))
        return panel

    def _entry(self, parent, variable, width=18):
        entry = tk.Entry(parent, textvariable=variable, width=width, bg=ENTRY, fg=TEXT,
                         relief="sunken", bd=2, highlightthickness=0,
                         insertbackground=TEXT, font=self.font_ui)
        return entry

    def _choice(self, parent, variable, choices, width=15):
        # Readonly combobox is native-feeling on macOS and retains the Windows
        # classic raised/sunken control proportions.
        return ttk.Combobox(parent, textvariable=variable, values=choices,
                            state="readonly", width=width, font=self.font_ui)

    def _check(self, parent, caption, variable):
        return tk.Checkbutton(parent, text=caption, variable=variable, bg=FACE, fg=TEXT,
                              activebackground=FACE, selectcolor=FACE, anchor="w",
                              font=self.font_small, highlightthickness=0)

    def _field(self, parent, label, widget, column=0, row=0):
        self._text(parent, label, small=True).grid(row=row, column=column, sticky="w", padx=6, pady=4)
        widget.grid(row=row+1, column=column, sticky="ew", padx=6, pady=(0, 8))

    def _create_widgets(self):
        title = tk.Frame(self, bg=NAVY, height=38)
        title.pack(side="top", fill="x", padx=5, pady=(5, 3))
        title.pack_propagate(False)
        if self.folder_icon:
            tk.Label(title, image=self.folder_icon, bg=NAVY).pack(side="left", padx=8)
        tk.Label(title, text="FolderExporter", bg=NAVY, fg="white",
                 font=self.font_heading).pack(side="left", padx=2)
        tk.Label(title, text="  ◀  Classic Edition  ▶ ", bg=NAVY, fg="#DFE0F0",
                 font=self.font_small).pack(side="right", padx=12)

        footer = tk.Frame(self, bg=FACE, relief="raised", bd=2)
        footer.pack(side="bottom", fill="x", padx=7, pady=(2, 7))
        info = tk.Frame(footer, bg=FACE)
        info.pack(side="left", fill="both", expand=True, padx=11, pady=7)
        self._text(info, self.status, small=True, textvariable=self.status).pack(anchor="w")
        self.progress = ttk.Progressbar(info, orient="horizontal", mode="determinate",
                                        maximum=100, length=300)
        self.progress.pack(fill="x", pady=(4, 0))
        self.export_button = ClassicButton(footer, "Export All", self._export, primary=True)
        self.export_button.pack(side="right", padx=10, pady=10)

        body = tk.Frame(self, bg=FACE)
        body.pack(fill="both", expand=True, padx=7, pady=3)

        left = tk.Frame(body, bg=FACE)
        left.pack(side="left", fill="both", expand=True, padx=(0, 5))
        right = tk.Frame(body, bg=FACE)
        right.pack(side="left", fill="both", expand=True, padx=(5, 0))

        file_panel = self._panel(left, "01   FILE", fill="x", side="top")
        row = tk.Frame(file_panel, bg=FACE)
        row.pack(fill="x", padx=12, pady=(0, 5))
        self._text(row, "", small=True, textvariable=self.file_label, wraplength=260)            .pack(side="left", fill="x", expand=True)
        self.open_button = ClassicButton(row, "Choose File...", self._choose)
        self.open_button.pack(side="right")
        tk.Label(file_panel, text="This program works best with .psd files.",
                 bg=FACE, fg="#595959", font=self.font_small, anchor="w")            .pack(fill="x", padx=12, pady=(0, 11))

        folder_panel = self._panel(left, "02   FOLDERS FOUND", fill="both", expand=True, pady=(8, 0))
        filter_row = tk.Frame(folder_panel, bg=FACE)
        filter_row.pack(fill="x", padx=12, pady=(0, 7))
        self._text(filter_row, "Organizational folder keywords", small=True).pack(anchor="w")
        self._entry(filter_row, self.keywords).pack(fill="x", pady=(3, 1))
        self._text(filter_row, "Folders containing these words are opened, not exported.", small=True)            .pack(anchor="w")
        control = tk.Frame(folder_panel, bg=FACE)
        control.pack(fill="x", padx=10, pady=(5, 7))
        self._text(control, "", small=True, textvariable=self.selection_label).pack(side="left")
        ClassicButton(control, "All", lambda: self._select_all(True)).pack(side="right", padx=(5, 0))
        ClassicButton(control, "None", lambda: self._select_all(False)).pack(side="right")

        listing = tk.Frame(folder_panel, bg=ENTRY, relief="sunken", bd=2)
        listing.pack(fill="both", expand=True, padx=11, pady=(0, 11))
        style = ttk.Style(self)
        style.configure("Retro.Treeview", background=ENTRY, fieldbackground=ENTRY,
                        foreground=TEXT, rowheight=25, borderwidth=0, font=self.font_ui)
        style.configure("Retro.Treeview.Heading", background=FACE, foreground=TEXT, font=self.font_small)
        style.map("Retro.Treeview", background=[("selected", "#000080")],
                  foreground=[("selected", "white")])
        self.folder_tree = ttk.Treeview(listing, show="tree", selectmode="browse",
                                        style="Retro.Treeview")
        bar = ttk.Scrollbar(listing, orient="vertical", command=self.folder_tree.yview)
        self.folder_tree.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        self.folder_tree.pack(side="left", fill="both", expand=True)
        self.folder_tree.bind("<ButtonRelease-1>", self._tree_clicked)
        self.folder_tree.bind("<space>", self._tree_keyboard)

        # Right side is independently scrollable; bottom export button never moves.
        scroll_region = tk.Frame(right, bg=FACE)
        scroll_region.pack(fill="both", expand=True)
        canvas = tk.Canvas(scroll_region, bg=FACE, highlightthickness=0, bd=0)
        scrollbar = ttk.Scrollbar(scroll_region, command=canvas.yview)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        self.settings_content = tk.Frame(canvas, bg=FACE)
        window = canvas.create_window((0, 0), window=self.settings_content, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        self.settings_content.bind("<Configure>", lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window, width=e.width))

        self._settings_panels()
        self._update_mode()
        self._preview()

    def _settings_panels(self):
        settings = self._panel(self.settings_content, "03   EXPORT SETTINGS", fill="x")
        image_fields = tk.Frame(settings, bg=FACE)
        image_fields.pack(fill="x", padx=9)
        image_fields.columnconfigure(0, weight=1)
        image_fields.columnconfigure(1, weight=1)
        self._field(image_fields, "Image format", self._choice(image_fields, self.format_var,
                    ("PNG", "WEBP", "TIFF", "JPEG"), 16), 0, 0)
        self._field(image_fields, "Scale (%)", self._choice(image_fields, self.scale_var,
                    ("25", "50", "75", "100", "150", "200", "300"), 16), 1, 0)
        self._field(image_fields, "JPEG / WebP quality", self._choice(image_fields, self.quality_var,
                    ("70", "80", "90", "95", "100"), 16), 0, 2)
        self._field(image_fields, "JPEG background", self._choice(image_fields, self.jpeg_background,
                    ("White", "Black"), 16), 1, 2)
        flags = tk.Frame(settings, bg=FACE)
        flags.pack(fill="x", padx=14, pady=(0, 8))
        self._check(flags, "Crop to drawing bounds", self.crop_var).pack(anchor="w")
        self._check(flags, "White background instead of transparency", self.white_var).pack(anchor="w")

        naming_panel = tk.LabelFrame(settings, text=" File Naming ", bg=FACE, fg=TEXT,
                                     font=self.font_heading, relief="groove", bd=2)
        naming_panel.pack(fill="x", padx=11, pady=(4, 11))
        mode_row = tk.Frame(naming_panel, bg=FACE)
        mode_row.pack(fill="x", padx=9, pady=8)
        self._text(mode_row, "Rename mode", small=True).pack(side="left", padx=(0, 9))
        mode = self._choice(mode_row, self.naming_mode,
                            ("Format", "Add Text", "Replace Text"), 19)
        mode.pack(side="left", fill="x", expand=True)
        self.mode_container = tk.Frame(naming_panel, bg=FACE)
        self.mode_container.pack(fill="x", padx=6)
        self._check(naming_panel, "Restart numbering in each chapter", self.naming_reset)            .pack(anchor="w", padx=11, pady=(3, 10))

        destination_panel = self._panel(self.settings_content, "04   DESTINATION & PREVIEW",
                                       fill="x", pady=(8, 0))
        destination_row = tk.Frame(destination_panel, bg=FACE)
        destination_row.pack(fill="x", padx=12, pady=(0, 7))
        self._entry(destination_row, self.destination).pack(side="left", fill="x", expand=True)
        ClassicButton(destination_row, "Browse...", self._browse).pack(side="right", padx=(7, 0))
        self._check(destination_panel, "Separate exports into chapter folders", self.separate)            .pack(anchor="w", padx=13, pady=(0, 7))
        self._text(destination_panel, "Live filename preview", small=True, bold=True)            .pack(anchor="w", padx=13, pady=(2, 5))
        preview_frame = tk.Frame(destination_panel, bg=ENTRY, relief="sunken", bd=2)
        preview_frame.pack(fill="x", padx=12, pady=(0, 12))
        tk.Label(preview_frame, textvariable=self.preview_text, bg=ENTRY, fg=TEXT,
                 justify="left", anchor="nw", font=self.font_small, wraplength=375)            .pack(anchor="w", fill="x", padx=10, pady=8)

    def _update_mode(self):
        for widget in self.mode_container.winfo_children():
            widget.destroy()
        mode = self.naming_mode.get()
        grid = tk.Frame(self.mode_container, bg=FACE)
        grid.pack(fill="x")
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)
        if mode == "Format":
            self._field(grid, "Name format", self._choice(grid, self.naming_kind,
                        ("Name and Index", "Name and Counter", "Name and Date", "Name Only"), 18), 0, 0)
            self._field(grid, "Position", self._choice(grid, self.naming_where,
                        ("before", "after"), 16), 1, 0)
            self._field(grid, "Custom format", self._entry(grid, self.naming_custom), 0, 2)
            self._field(grid, "Start numbers at", self._entry(grid, self.naming_start), 1, 2)
            self._field(grid, "Zero padding", self._entry(grid, self.naming_padding), 0, 4)
            self._field(grid, "Separator", self._entry(grid, self.naming_separator), 1, 4)
        elif mode == "Add Text":
            self._field(grid, "Text to add", self._entry(grid, self.naming_add), 0, 0)
            self._field(grid, "Position", self._choice(grid, self.naming_where,
                        ("before", "after"), 16), 1, 0)
        else:
            self._field(grid, "Find", self._entry(grid, self.naming_search), 0, 0)
            self._field(grid, "Replace with", self._entry(grid, self.naming_replace), 1, 0)

    def _on_setting_changed(self):
        if self.naming_mode.get() != getattr(self, "_display_mode", None):
            self._display_mode = self.naming_mode.get()
            self._update_mode()
        self._refresh_discovery(refresh_tree=False)
        self._preview()

    def _choose(self):
        path = filedialog.askopenfilename(title="Choose a Clip Studio or Photoshop project",
                filetypes=[("Supported projects", "*.psd *.psb *.clip"),
                           ("Photoshop projects", "*.psd *.psb"),
                           ("Clip Studio projects (experimental)", "*.clip"),
                           ("All files", "*.*")])
        if path:
            self._open(Path(path))

    def _open(self, path: Path):
        if self._busy():
            return
        if not path.is_file() or path.suffix.lower() not in (".psd", ".psb", ".clip"):
            messagebox.showerror("Unsupported file", "Please choose a PSD, PSB, or CLIP file.")
            return
        self.loading = True
        self.open_button.configure(state="disabled")
        self.status.set("Reading source file (read-only)...")
        def work():
            try:
                doc = load_project(path)
                nodes = folder_tree(doc)
                self.events.put(("loaded", (path, doc, nodes)))
            except Exception as exc:
                self.events.put(("load_error", str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def _browse(self):
        directory = filedialog.askdirectory(title="Choose export destination",
                           initialdir=self.destination.get() or str(Path.home()))
        if directory:
            self.destination.set(directory)

    def _busy(self):
        return self.loading or (self.worker is not None and self.worker.is_alive())

    def _refresh_discovery(self, refresh_tree=True):
        if not self.tree_nodes:
            return
        old_selected = self.selected.copy()
        self.drawings = discover_drawings(self.tree_nodes, self.keywords.get(), self.separate.get())
        valid_keys = {d.key for d in self.drawings}
        if refresh_tree:
            self.selected = valid_keys if not old_selected else old_selected & valid_keys
            self._render_tree()
        else:
            self._preview()

    def _render_tree(self):
        self.folder_tree.delete(*self.folder_tree.get_children())
        keywords = self.keywords.get()
        def add(nodes, parent=""):
            for node in nodes:
                org = is_organizer(node, keywords)
                prefix = "[+] " if org else ("[x] " if node.key in self.selected else "[ ] ")
                state = " (hidden)" if not node.visible else ""
                self.folder_tree.insert(parent, "end", iid=node.key,
                                        text=prefix + node.name + state,
                                        open=True, image=self.folder_icon if self.folder_icon else "")
                if org:
                    add(node.children, node.key)
        add(self.tree_nodes)
        self.selection_label.set(f"{len(self.selected)} of {len(self.drawings)} drawings selected")
        self._preview()

    def _toggle_node(self, key):
        if self._busy():
            return
        drawings = [d.key for d in self.drawings if d.key == key or d.key.startswith(key + "/")]
        if not drawings:
            return
        if all(k in self.selected for k in drawings):
            self.selected.difference_update(drawings)
        else:
            self.selected.update(drawings)
        self._render_tree()

    def _tree_clicked(self, event):
        row = self.folder_tree.identify_row(event.y)
        if row and self.folder_tree.identify("element", event.x, event.y) != "Treeitem.indicator":
            self._toggle_node(row)

    def _tree_keyboard(self, event):
        selection = self.folder_tree.selection()
        if selection:
            self._toggle_node(selection[0])
        return "break"

    def _select_all(self, value: bool):
        if self._busy():
            return
        self.selected = {d.key for d in self.drawings} if value else set()
        self._render_tree()

    def _export_options(self):
        return Options(format=self.format_var.get(), scale=int(self.scale_var.get()),
                       quality=int(self.quality_var.get()), crop=self.crop_var.get(),
                       white_background=self.white_var.get(),
                       matte="black" if self.jpeg_background.get() == "Black" else "white")

    def _naming_options(self):
        return Naming(mode=self.naming_mode.get(), kind=self.naming_kind.get(),
                      custom=self.naming_custom.get(), where=self.naming_where.get(),
                      start=int(self.naming_start.get()), padding=int(self.naming_padding.get()),
                      separator=self.naming_separator.get(), reset=self.naming_reset.get(),
                      addition=self.naming_add.get(), search=self.naming_search.get(),
                      replacement=self.naming_replace.get())

    def _tasks(self):
        destination = Path(self.destination.get()).expanduser()
        if not self.destination.get().strip():
            raise ValueError("Choose an export destination.")
        options = self._export_options()
        if not 10 <= options.scale <= 400:
            raise ValueError("Scale must be between 10% and 400%.")
        if not 1 <= options.quality <= 100:
            raise ValueError("Quality must be between 1 and 100.")
        return make_plan(self.drawings, self.selected, destination,
                         self._naming_options(), options, self.separate.get())

    def _preview(self):
        if not hasattr(self, "preview_text"):
            return
        if not self.source:
            self.preview_text.set("Choose a source file to preview names and folders.")
            return
        try:
            tasks = self._tasks()
            if not tasks:
                self.preview_text.set("No drawings selected. Click folders on the left to select them.")
                return
            dest = Path(self.destination.get()).expanduser()
            lines = [str(task.path.relative_to(dest)) for task in tasks[:5]]
            if len(tasks) > 5:
                lines.append(f"... and {len(tasks) - 5} more")
            self.preview_text.set("\n".join(lines))
        except (ValueError, OSError, KeyError, Exception) as exc:
            self.preview_text.set(f"Check export settings: {exc}")

    def _export(self):
        if self._busy():
            if self.worker and self.worker.is_alive():
                self.cancel.set()
                self.status.set("Cancel requested. Finishing the current drawing...")
            return
        try:
            if not self.source:
                raise ValueError("Choose a source file first.")
            tasks = self._tasks()
            if not tasks:
                raise ValueError("Select at least one drawing folder.")
            destination = Path(self.destination.get()).expanduser()
            if destination.exists() and not destination.is_dir():
                raise ValueError("Destination is not a folder.")
            options = self._export_options()
        except (ValueError, OSError) as exc:
            messagebox.showwarning("Check export options", str(exc))
            return
        self.cancel.clear()
        self.progress["value"] = 0
        self.export_button.configure(text="Cancel Export")
        self.open_button.configure(state="disabled")
        self.status.set(f"Exporting {len(tasks)} drawings...")
        def work():
            try:
                # Load an independent read-only copy in the worker thread.
                project = load_project(self.source)
                new_tree = folder_tree(project)
                refs = {}
                def walk(nodes):
                    for node in nodes:
                        refs[node.key] = node.ref
                        walk(node.children)
                walk(new_tree)
                from dataclasses import replace
                rebound = [replace(task, drawing=replace(task.drawing, ref=refs[task.drawing.key]))
                           for task in tasks]
                result = export_plan(project, rebound, options, self._on_progress, self.cancel)
                self.events.put(("done", (result, destination)))
            except Exception as exc:
                self.events.put(("export_error", str(exc)))
        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def _on_progress(self, index, total, name, error):
        self.events.put(("progress", (index, total, name, error)))

    def _poll(self):
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "loaded":
                    self.source, self.project, self.tree_nodes = payload
                    self.loading = False
                    self.open_button.configure(state="normal")
                    self.file_label.set(self.source.name)
                    self.destination.set(str(self.source.parent / "FolderExporter Exports"))
                    self.selected.clear()
                    self._refresh_discovery(refresh_tree=True)
                    self.status.set(f"{self.source.name}  |  {self.project.width}x{self.project.height} px")
                    if not self.drawings:
                        messagebox.showwarning("No drawings found",
                            "No drawable folders matched these rules. Adjust the organizational folder keywords.")
                elif kind == "load_error":
                    self.loading = False
                    self.open_button.configure(state="normal")
                    self.status.set("Could not open source file.")
                    messagebox.showerror("File error", payload)
                elif kind == "progress":
                    i, total, name, error = payload
                    self.progress["value"] = round(i / total * 100)
                    self.status.set(f"{i}/{total}  {name}" + (f" | Error: {error}" if error else ""))
                elif kind == "done":
                    result, destination = payload
                    self._end_export()
                    self.status.set(f"Exported {len(result.created)} drawing(s). "
                                    f"{len(result.failures)} failure(s).")
                    message = (f"Exported: {len(result.created)}\nFailed: {len(result.failures)}"
                               f"\nDestination: {destination}")
                    if result.cancelled:
                        message = "Export cancelled.\n" + message
                    if result.failures:
                        message += "\n\n" + "\n".join(
                            f"{name}: {error}" for name, error in result.failures[:7])
                    messagebox.showinfo("Export report", message)
                    self._preview()
                elif kind == "export_error":
                    self._end_export()
                    self.status.set("Export failed.")
                    messagebox.showerror("Export error", payload)
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _end_export(self):
        self.export_button.configure(text="Export All")
        self.open_button.configure(state="normal")

    def _close(self):
        if self._busy():
            self.cancel.set()
            messagebox.showwarning("Export in progress",
                                   "The current operation is still running. Close the window after it finishes.")
            return
        self.destroy()
