"""FolderExporter: interface de exportação em lote para Windows e macOS."""
from __future__ import annotations
import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from engine import Options, build_export_plan, export_groups, list_top_level_groups, load_psd, safe_stem

BG = "#f7f7f8"
CARD = "#ffffff"
TEXT = "#202329"
MUTED = "#6e7480"
ACCENT = "#bf315a"
BORDER = "#e6e7e9"
NAMING = {
    "Nome da pasta": "name",
    "001, 002, 003": "number",
    "001 - Nome": "number_name",
    "Nome - 001": "name_number",
    "Prefixo - 001": "prefix",
}
DESTINATIONS = ("Ao lado do PSD", "Subpasta do PSD", "Escolher destino")

class Application(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("FolderExporter")
        self.geometry("780x790")
        self.minsize(700, 690)
        self.configure(bg=BG)
        self.psd = None
        self.source: Path | None = None
        self.folders = []
        self.selected: set[int] = set()
        self.events = queue.Queue()
        self.worker = None
        self.cancel = threading.Event()
        self.source_text = tk.StringVar(value="Nenhum documento selecionado")
        self.status = tk.StringVar(value="Pronto")
        self.naming_text = tk.StringVar(value="Nome da pasta")
        self.format_text = tk.StringVar(value="PNG")
        self.scale_text = tk.StringVar(value="100")
        self.quality_text = tk.StringVar(value="90")
        self.prefix = tk.StringVar(value="imagem")
        self.crop = tk.BooleanVar(value=False)
        self.matte_text = tk.StringVar(value="Branco")
        self.destination_mode = tk.StringVar(value=DESTINATIONS[1])
        self.subfolder = tk.StringVar(value="Exportados")
        self.custom_directory = tk.StringVar(value="")
        self.preview_text = tk.StringVar(value="Escolha um PSD para visualizar os nomes.")
        self.info_text = tk.StringVar(value="0 pastas selecionadas")
        self._styles()
        self._layout()
        for var in (self.naming_text, self.format_text, self.prefix,
                    self.destination_mode, self.subfolder, self.custom_directory):
            var.trace_add("write", lambda *_: self._refresh_preview())
        self.after(120, self._poll)
        self.protocol("WM_DELETE_WINDOW", self._close)
        if len(sys.argv) > 1:
            self.after(200, lambda: self._open(Path(sys.argv[1])))

    def _styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        font = ("Arial", 10)
        style.configure(".", font=font)
        style.configure("Page.TFrame", background=BG)
        style.configure("Card.TFrame", background=CARD)
        style.configure("Page.TLabel", background=BG, foreground=TEXT)
        style.configure("Card.TLabel", background=CARD, foreground=TEXT)
        style.configure("Muted.TLabel", background=CARD, foreground=MUTED)
        style.configure("Title.TLabel", background=BG, foreground=TEXT, font=("Arial", 22, "bold"))
        style.configure("Section.TLabel", background=CARD, foreground=TEXT, font=("Arial", 10, "bold"))
        style.configure("Primary.TButton", padding=(16, 10), background=ACCENT, foreground="white", borderwidth=0)
        style.map("Primary.TButton", background=[("active", "#a8294e"), ("disabled", "#e2b5c2")])
        style.configure("Secondary.TButton", padding=(11, 8), background="#f1f1f3", foreground=TEXT, borderwidth=0)
        style.map("Secondary.TButton", background=[("active", "#e6e6e9")])
        style.configure("F.TEntry", padding=6, fieldbackground="white", foreground=TEXT)
        style.configure("F.TCombobox", padding=5, fieldbackground="white", foreground=TEXT)
        style.configure("F.TCheckbutton", background=CARD, foreground=TEXT)
        style.map("F.TCheckbutton", background=[("active", CARD)])
        style.configure("F.Treeview", background=CARD, fieldbackground=CARD, foreground=TEXT, rowheight=27, borderwidth=0)
        style.map("F.Treeview", background=[("selected", "#f8dce5")], foreground=[("selected", TEXT)])
        style.configure("F.Treeview.Heading", background="#f1f2f3", foreground=MUTED, padding=(8, 8), relief="flat")
        style.configure("F.Horizontal.TProgressbar", troughcolor="#ececf0", background=ACCENT, borderwidth=0)

    def _label(self, parent, title, muted=False):
        return ttk.Label(parent, text=title, style="Muted.TLabel" if muted else "Card.TLabel")

    def _section(self, parent, heading):
        frame = ttk.Frame(parent, style="Card.TFrame", padding=(16, 12))
        frame.pack(fill="x", pady=(0, 9))
        ttk.Label(frame, text=heading, style="Section.TLabel").pack(anchor="w", pady=(0, 9))
        return frame

    def _combo(self, parent, variable, choices, width=18):
        combo = ttk.Combobox(parent, textvariable=variable, values=choices, state="readonly", width=width, style="F.TCombobox")
        combo.pack(side="left", padx=(0, 12))
        return combo

    def _layout(self):
        root = ttk.Frame(self, style="Page.TFrame", padding=(19, 14))
        root.pack(fill="both", expand=True)
        ttk.Label(root, text="FolderExporter", style="Title.TLabel").pack(anchor="w")
        ttk.Label(root, text="Uma pasta do PSD, uma imagem. Tudo em um clique.", style="Page.TLabel", foreground=MUTED).pack(anchor="w", pady=(2, 14))

        source = self._section(root, "01    Arquivo")
        line = ttk.Frame(source, style="Card.TFrame")
        line.pack(fill="x")
        ttk.Label(line, textvariable=self.source_text, style="Muted.TLabel").pack(side="left", fill="x", expand=True)
        self.open_btn = ttk.Button(line, text="Abrir PSD/PSB", style="Secondary.TButton", command=self._choose)
        self.open_btn.pack(side="right")

        groups_card = self._section(root, "02    Pastas encontradas")
        tools = ttk.Frame(groups_card, style="Card.TFrame")
        tools.pack(fill="x", pady=(0, 6))
        ttk.Label(tools, textvariable=self.info_text, style="Muted.TLabel").pack(side="left")
        ttk.Button(tools, text="Todas", style="Secondary.TButton", command=lambda: self._mark_all(True)).pack(side="right")
        ttk.Button(tools, text="Nenhuma", style="Secondary.TButton", command=lambda: self._mark_all(False)).pack(side="right", padx=6)
        box = ttk.Frame(groups_card, style="Card.TFrame")
        box.pack(fill="both")
        self.tree = ttk.Treeview(box, columns=("check", "folder", "visibility"), show="headings", height=6, style="F.Treeview")
        for col, title, width in (("check", "✓", 50), ("folder", "Pasta", 430), ("visibility", "Estado", 110)):
            self.tree.heading(col, text=title)
            self.tree.column(col, width=width, stretch=(col == "folder"), anchor="center" if col != "folder" else "w")
        self.tree.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(box, orient="vertical", command=self.tree.yview)
        scroll.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<Button-1>", self._toggle)

        opts = self._section(root, "03    Saída")
        top = ttk.Frame(opts, style="Card.TFrame")
        top.pack(fill="x", pady=(0, 8))
        self._label(top, "Formato").pack(side="left", padx=(0, 8))
        self._combo(top, self.format_text, ("PNG", "WEBP", "TIFF", "JPEG"), 9)
        self._label(top, "Nomes").pack(side="left", padx=(8, 8))
        self._combo(top, self.naming_text, tuple(NAMING), 20)
        middle = ttk.Frame(opts, style="Card.TFrame")
        middle.pack(fill="x", pady=(0, 8))
        self._label(middle, "Escala (%)").pack(side="left", padx=(0, 8))
        self._combo(middle, self.scale_text, ("25", "50", "75", "100", "150", "200", "300"), 6)
        self._label(middle, "Qualidade JPEG/WebP").pack(side="left", padx=(8, 8))
        self._combo(middle, self.quality_text, ("70", "80", "90", "95", "100"), 6)
        third = ttk.Frame(opts, style="Card.TFrame")
        third.pack(fill="x")
        ttk.Checkbutton(third, text="Recortar transparência", variable=self.crop, style="F.TCheckbutton").pack(side="left")
        self._label(third, "Fundo JPEG").pack(side="left", padx=(20, 7))
        self._combo(third, self.matte_text, ("Branco", "Preto"), 9)
        custom = ttk.Frame(opts, style="Card.TFrame")
        custom.pack(fill="x", pady=(9, 0))
        self._label(custom, "Prefixo personalizado").pack(side="left", padx=(0, 10))
        ttk.Entry(custom, textvariable=self.prefix, width=22, style="F.TEntry").pack(side="left", fill="x", expand=True)
        self._label(opts, "PNG, WebP e TIFF preservam transparência; JPEG não.", muted=True).pack(anchor="w", pady=(8, 0))

        dest = self._section(root, "04    Destino")
        route = ttk.Frame(dest, style="Card.TFrame")
        route.pack(fill="x", pady=(0, 7))
        self._combo(route, self.destination_mode, DESTINATIONS, 22)
        ttk.Entry(route, textvariable=self.subfolder, width=20, style="F.TEntry").pack(side="left", fill="x", expand=True)
        custom_dest = ttk.Frame(dest, style="Card.TFrame")
        custom_dest.pack(fill="x")
        ttk.Entry(custom_dest, textvariable=self.custom_directory, style="F.TEntry").pack(side="left", fill="x", expand=True)
        self.choose_dir_btn = ttk.Button(custom_dest, text="Procurar...", style="Secondary.TButton", command=self._choose_dir)
        self.choose_dir_btn.pack(side="right", padx=(8, 0))
        self._label(dest, "A subpasta é criada automaticamente. Arquivos existentes nunca são substituídos.", muted=True).pack(anchor="w", pady=(7, 0))

        preview = ttk.Frame(root, style="Card.TFrame", padding=(15, 10))
        preview.pack(fill="x", pady=(0, 9))
        ttk.Label(preview, text="PRÉVIA", style="Section.TLabel").pack(anchor="w", pady=(0, 4))
        ttk.Label(preview, textvariable=self.preview_text, style="Muted.TLabel", justify="left", wraplength=680).pack(anchor="w")

        bottom = ttk.Frame(root, style="Page.TFrame")
        bottom.pack(fill="x")
        ttk.Label(bottom, textvariable=self.status, style="Page.TLabel").pack(side="left")
        self.export_btn = ttk.Button(bottom, text="Exportar tudo", style="Primary.TButton", command=self._export)
        self.export_btn.pack(side="right")
        self.progress = ttk.Progressbar(root, style="F.Horizontal.TProgressbar", maximum=100)
        self.progress.pack(fill="x", pady=(9, 0))

    def _choose(self):
        path = filedialog.askopenfilename(title="Abrir PSD/PSB", filetypes=[("Arquivos Photoshop", "*.psd *.psb"), ("Todos", "*.*")])
        if path:
            self._open(Path(path))

    def _open(self, path):
        if self._busy():
            return
        if path.suffix.lower() not in (".psd", ".psb") or not path.is_file():
            messagebox.showerror("Arquivo inválido", "Selecione um arquivo PSD ou PSB existente.")
            return
        self.open_btn.configure(state="disabled")
        self.status.set("Lendo camadas...")
        def work():
            try:
                doc = load_psd(path)
                self.events.put(("loaded", (path, doc, list_top_level_groups(doc))))
            except Exception as exc:
                self.events.put(("error_open", str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def _choose_dir(self):
        initial = self.custom_directory.get() or (str(self.source.parent) if self.source else str(Path.home()))
        picked = filedialog.askdirectory(initialdir=initial, title="Escolha a pasta de destino")
        if picked:
            self.custom_directory.set(picked)
            self.destination_mode.set(DESTINATIONS[2])

    def _busy(self):
        return bool(self.worker and self.worker.is_alive())

    def _mark_all(self, enabled):
        if self._busy():
            return
        self.selected = set(range(len(self.folders))) if enabled else set()
        self._redraw()

    def _toggle(self, event):
        if self._busy():
            return "break"
        row = self.tree.identify_row(event.y)
        if row:
            index = int(row)
            if index in self.selected:
                self.selected.remove(index)
            else:
                self.selected.add(index)
            self._redraw()
        return "break"

    def _redraw(self):
        self.tree.delete(*self.tree.get_children())
        for i, folder in enumerate(self.folders):
            self.tree.insert("", "end", iid=str(i), values=(
                "✓" if i in self.selected else "",
                folder.name, "Visível" if folder.visible else "Oculta"))
        self.info_text.set(f"{len(self.selected)} de {len(self.folders)} selecionadas")
        self._refresh_preview()

    def _export_options(self):
        return Options(
            naming=NAMING[self.naming_text.get()],
            format=self.format_text.get(),
            crop=self.crop.get(), scale=int(self.scale_text.get()),
            quality=int(self.quality_text.get()),
            matte="black" if self.matte_text.get() == "Preto" else "white",
            prefix=self.prefix.get())

    def _destination(self):
        if self.source is None:
            raise ValueError("Abra um PSD primeiro.")
        mode = self.destination_mode.get()
        if mode == DESTINATIONS[0]:
            return self.source.parent
        if mode == DESTINATIONS[1]:
            name = self.subfolder.get().strip()
            if not name or safe_stem(name) != name or name in (".", ".."):
                raise ValueError("Escolha um nome simples e válido para a subpasta.")
            return self.source.parent / name
        chosen = self.custom_directory.get().strip()
        if not chosen:
            raise ValueError("Escolha uma pasta de destino.")
        return Path(chosen).expanduser()

    def _refresh_preview(self):
        if not hasattr(self, "tree") or not self.folders:
            return
        try:
            chosen = [g for i, g in enumerate(self.folders) if i in self.selected]
            dest = self._destination()
            items = build_export_plan(chosen, dest, self._export_options())
            names = [p.name for _, p in items[:3]]
            if len(items) > 3:
                names.append(f"... e mais {len(items)-3} arquivos")
            self.preview_text.set(("  •  ".join(names) if names else "Nenhuma pasta selecionada.") + f"\nDestino: {dest}")
        except (ValueError, KeyError) as exc:
            self.preview_text.set(str(exc))

    def _export(self):
        if self._busy():
            self.cancel.set()
            self.status.set("Cancelando após a pasta atual...")
            return
        try:
            if self.psd is None:
                raise ValueError("Abra um PSD/PSB primeiro.")
            folders = [g for i, g in enumerate(self.folders) if i in self.selected]
            if not folders:
                raise ValueError("Selecione pelo menos uma pasta.")
            destination = self._destination()
            if not destination.exists() and self.destination_mode.get() == DESTINATIONS[1]:
                destination.mkdir(parents=False, exist_ok=True)
            if not destination.is_dir():
                raise ValueError("A pasta de destino não existe.")
            options = self._export_options()
        except (ValueError, OSError, KeyError) as exc:
            messagebox.showwarning("Verifique as opções", str(exc))
            return
        self.cancel.clear()
        self.progress["value"] = 0
        self.export_btn.configure(text="Cancelar")
        self.open_btn.configure(state="disabled")
        self.status.set("Exportando...")
        def work():
            try:
                result = export_groups(
                    self.psd, folders, destination, options,
                    progress=lambda current, total, name, outcome: self.events.put(("progress", (current, total, name, outcome))),
                    cancel=self.cancel)
                self.events.put(("done", (result, destination)))
            except Exception as exc:
                self.events.put(("error_export", str(exc)))
        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def _poll(self):
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "loaded":
                    self.source, self.psd, self.folders = payload
                    self.selected = set(range(len(self.folders)))
                    self.source_text.set(self.source.name)
                    self.status.set(f"{self.psd.width} × {self.psd.height} px · {len(self.folders)} pastas")
                    self.open_btn.configure(state="normal")
                    self._redraw()
                    if not self.folders:
                        messagebox.showwarning("Nenhuma pasta", "Não há pastas no primeiro nível do PSD.")
                elif kind == "error_open":
                    self.open_btn.configure(state="normal")
                    self.status.set("Falha ao abrir")
                    messagebox.showerror("Erro ao abrir", payload)
                elif kind == "progress":
                    current, total, name, outcome = payload
                    self.progress["value"] = 100 * current / total
                    self.status.set(f"{current}/{total} · {outcome}")
                elif kind == "done":
                    result, destination = payload
                    self._finish()
                    title = "Exportação cancelada" if result.cancelled else "Exportação concluída"
                    message = f"{len(result.created)} arquivo(s) criado(s).\n{len(result.failures)} falha(s).\n\nDestino: {destination}"
                    if result.failures:
                        message += "\n\n" + "\n".join(f"{name}: {error}" for name, error in result.failures[:8])
                    self.status.set(f"{len(result.created)} exportados · {len(result.failures)} falhas")
                    messagebox.showinfo(title, message)
                    self._refresh_preview()
                elif kind == "error_export":
                    self._finish()
                    self.status.set("Falha na exportação")
                    messagebox.showerror("Erro ao exportar", payload)
        except queue.Empty:
            pass
        self.after(120, self._poll)

    def _finish(self):
        self.export_btn.configure(text="Exportar tudo")
        self.open_btn.configure(state="normal")

    def _close(self):
        if self._busy():
            self.cancel.set()
            messagebox.showinfo("Exportação em andamento", "A exportação será cancelada após a imagem atual. Feche novamente quando terminar.")
            return
        self.destroy()

if __name__ == "__main__":
    Application().mainloop()
