import json
import os
import threading
import time
from collections import Counter
from datetime import datetime, timedelta
from math import log2
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
import secrets, string

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Small utility app: To-Do Manager, Text Analyzer, Password Generator
# Single-file Tkinter application. Saves todos to JSON (todos.json).
# Works with standard library only. Optional word cloud requires 'wordcloud' and 'matplotlib'.


APP_TITLE = "Wallye - Utility App v1.0"
TODO_FILE = "todos.json"
DEADLINE_NOTICE_MINUTES = 10  # avvisa se la scadenza è entro questo numero di minuti

# Private releases (read-only for the app)
PRIVATE_RELEASE_HOME = os.path.join(os.path.expanduser("~"), ".wallye_releases")
PRIVATE_RELEASES_FILE = os.path.join(PRIVATE_RELEASE_HOME, "releases.json")
PRIVATE_RELEASES_DIR = os.path.join(PRIVATE_RELEASE_HOME, "releases")

def load_private_releases():
    if os.path.exists(PRIVATE_RELEASES_FILE):
        try:
            with open(PRIVATE_RELEASES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def get_private_release_path(version):
    safe_ver = str(version).replace("/", "_").replace("\\", "_")
    return os.path.join(PRIVATE_RELEASES_DIR, f"RELEASE_{safe_ver}.md")

# ---------------------------
# Utility functions
# ---------------------------
def load_todos():
    if os.path.exists(TODO_FILE):
        try:
            with open(TODO_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_todos(todos):
    with open(TODO_FILE, "w", encoding="utf-8") as f:
        json.dump(todos, f, ensure_ascii=False, indent=2)

def parse_deadline(text):
    text = text.strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except Exception:
            pass
    return None

def deadline_to_str(dt):
    return dt.strftime("%Y-%m-%d %H:%M") if dt else ""


# syllable estimation (simple heuristic)
def estimate_syllables(word):
    word = word.lower()
    vowels = "aeiouy"
    count = 0
    prev_v = False
    for ch in word:
        is_v = ch in vowels
        if is_v and not prev_v:
            count += 1
        prev_v = is_v
    if word.endswith("e"):
        count = max(1, count - 1)
    return max(1, count)

def flesch_reading_ease(text):
    words = [w for w in ''.join(ch if ch.isalnum() or ch.isspace() else ' ' for ch in text).split() if w]
    if not words:
        return None
    sentences = max(1, sum(1 for ch in text if ch in ".!?"))
    syllables = sum(estimate_syllables(w) for w in words)
    words_count = len(words)
    # Flesch Reading Ease
    score = 206.835 - 1.015 * (words_count / sentences) - 84.6 * (syllables / words_count)
    return round(score, 2)

# ---------------------------
# GUI Application
# ---------------------------
class App:
    def __init__(self, root):
        self.root = root
        root.title(APP_TITLE)
        root.geometry("900x600")
        self.todos = load_todos()
        # Track notified tasks to avoid repeat notifications
        self.notified = set()

        self.tab_control = ttk.Notebook(root)
        self.tab_todo = ttk.Frame(self.tab_control)
        self.tab_text = ttk.Frame(self.tab_control)
        self.tab_pass = ttk.Frame(self.tab_control)
        self.tab_updates_available = ttk.Frame(self.tab_control)

        self.tab_control.add(self.tab_todo, text="To-Do")
        self.tab_control.add(self.tab_text, text="Analizzatore Testo")
        self.tab_control.add(self.tab_pass, text="Generatore Password")
        self.tab_control.add(self.tab_updates_available, text="Aggiornamenti disponibili")
        self.tab_control.pack(expand=1, fill="both")

        self.build_todo_tab()
        self.build_text_tab()
        self.build_pass_tab()
        self.build_updates_available_tab()

        # Start periodic deadline checker
        self.root.after(5000, self.check_deadlines)

    # ---------------------------
    # To-Do Tab
    # ---------------------------
    def build_todo_tab(self):
        frame = self.tab_todo
        left = ttk.Frame(frame)
        left.pack(side="left", fill="y", padx=8, pady=8)
        right = ttk.Frame(frame)
        right.pack(side="left", expand=1, fill="both", padx=8, pady=8)

        lbl = ttk.Label(left, text="Tasks")
        lbl.pack(anchor="w")
        self.lb_tasks = tk.Listbox(left, width=36)
        self.lb_tasks.pack(expand=1, fill="y")
        self.lb_tasks.bind("<<ListboxSelect>>", self.on_select_task)

        btn_frame = ttk.Frame(left)
        btn_frame.pack(fill="x", pady=6)
        ttk.Button(btn_frame, text="Aggiungi", command=self.add_task_dialog).pack(side="left", padx=2)
        ttk.Button(btn_frame, text="Rimuovi", command=self.remove_task).pack(side="left", padx=2)
        ttk.Button(btn_frame, text="Modifica", command=self.edit_task_dialog).pack(side="left", padx=2)
        ttk.Button(btn_frame, text="Salva manuale", command=lambda: save_todos(self.todos)).pack(side="left", padx=2)

        # Right: details
        ttk.Label(right, text="Dettagli task").pack(anchor="w")
        self.txt_details = tk.Text(right, height=5)
        self.txt_details.pack(fill="x")
        ttk.Label(right, text="Scadenza (YYYY-MM-DD HH:MM)").pack(anchor="w", pady=(8,0))
        self.entry_deadline = ttk.Entry(right)
        self.entry_deadline.pack(fill="x")
        ttk.Label(right, text="Stato").pack(anchor="w", pady=(8,0))
        self.status_var = tk.StringVar()
        self.cb_status = ttk.Combobox(right, textvariable=self.status_var, values=["pending","done"], state="readonly")
        self.cb_status.pack(fill="x")
        ttk.Button(right, text="Aggiorna", command=self.update_selected_task).pack(pady=6)

        self.refresh_task_list()

    def refresh_task_list(self):
        self.lb_tasks.delete(0, tk.END)
        for i, t in enumerate(self.todos):
            title = t.get("title","(No title)")
            dl = t.get("deadline")
            mark = "[done] " if t.get("status")=="done" else ""
            dlstr = f" ({dl})" if dl else ""
            self.lb_tasks.insert(tk.END, f"{i+1}. {mark}{title}{dlstr}")

    def on_select_task(self, _ev):
        sel = self.lb_tasks.curselection()
        if not sel:
            return
        idx = sel[0]
        item = self.todos[idx]
        self.txt_details.delete("1.0", tk.END)
        self.txt_details.insert(tk.END, item.get("desc",""))
        self.entry_deadline.delete(0, tk.END)
        self.entry_deadline.insert(0, item.get("deadline",""))
        self.status_var.set(item.get("status","pending"))

    def add_task_dialog(self):
        title = simpledialog.askstring("Nuovo task", "Titolo:")
        if not title:
            return
        desc = simpledialog.askstring("Nuovo task", "Descrizione (opzionale):") or ""
        dl = simpledialog.askstring("Nuovo task", "Scadenza (YYYY-MM-DD HH:MM) (opzionale):") or ""
        t = {"title": title, "desc": desc, "deadline": dl, "status": "pending"}
        self.todos.append(t)
        save_todos(self.todos)
        self.refresh_task_list()

    def remove_task(self):
        sel = self.lb_tasks.curselection()
        if not sel:
            return
        idx = sel[0]
        if messagebox.askyesno("Conferma", "Rimuovere il task selezionato?"):
            self.todos.pop(idx)
            save_todos(self.todos)
            self.refresh_task_list()

    def edit_task_dialog(self):
        sel = self.lb_tasks.curselection()
        if not sel:
            return
        idx = sel[0]
        t = self.todos[idx]
        title = simpledialog.askstring("Modifica task", "Titolo:", initialvalue=t.get("title",""))
        if title is None:
            return
        desc = simpledialog.askstring("Modifica task", "Descrizione (opzionale):", initialvalue=t.get("desc","")) or ""
        dl = simpledialog.askstring("Modifica task", "Scadenza (YYYY-MM-DD HH:MM) (opzionale):", initialvalue=t.get("deadline","")) or ""
        status = simpledialog.askstring("Modifica task", "Stato (pending/done):", initialvalue=t.get("status","pending")) or "pending"
        t.update({"title": title, "desc": desc, "deadline": dl, "status": status})
        save_todos(self.todos)
        self.refresh_task_list()

    def update_selected_task(self):
        sel = self.lb_tasks.curselection()
        if not sel:
            return
        idx = sel[0]
        desc = self.txt_details.get("1.0", tk.END).strip()
        dl = self.entry_deadline.get().strip()
        status = self.status_var.get() or "pending"
        self.todos[idx].update({"desc": desc, "deadline": dl, "status": status})
        save_todos(self.todos)
        self.refresh_task_list()

    # Deadline checker using after (main thread)
    def check_deadlines(self):
        now = datetime.now()
        soon = now + timedelta(minutes=DEADLINE_NOTICE_MINUTES)
        for i, t in enumerate(self.todos):
            dl_text = t.get("deadline","")
            if not dl_text:
                continue
            try:
                dl = parse_deadline(dl_text)
            except Exception:
                dl = None
            if not dl:
                continue
            key = f"{i}-{dl_text}"
            if key in self.notified:
                continue
            if now <= dl <= soon and t.get("status")!="done":
                # show notice
                messagebox.showinfo("Scadenza vicina", f"Task in scadenza entro {DEADLINE_NOTICE_MINUTES} min:\n{t.get('title')}\nScadenza: {dl_text}")
                self.notified.add(key)
        # schedule next check
        self.root.after(60 * 1000, self.check_deadlines)

    # ---------------------------
    # Text Analyzer Tab
    # ---------------------------
    def build_text_tab(self):
        frame = self.tab_text
        top = ttk.Frame(frame)
        top.pack(fill="both", expand=1, padx=8, pady=8)
        bottom = ttk.Frame(frame)
        bottom.pack(fill="x", padx=8, pady=4)

        lbl = ttk.Label(top, text="Inserisci testo da analizzare:")
        lbl.pack(anchor="w")
        self.txt_input = tk.Text(top)
        self.txt_input.pack(expand=1, fill="both")

        btns = ttk.Frame(bottom)
        btns.pack(fill="x")
        ttk.Button(btns, text="Analizza", command=self.analyze_text).pack(side="left", padx=4)
        ttk.Button(btns, text="Apri file...", command=self.open_text_file).pack(side="left", padx=4)
        ttk.Button(btns, text="Salva output", command=self.save_analysis).pack(side="left", padx=4)

        self.analysis_output = tk.Text(bottom, height=8)
        self.analysis_output.pack(expand=0, fill="x", pady=6)

    def open_text_file(self):
        path = filedialog.askopenfilename(filetypes=[("Text files","*.txt;*.md;*.py;*.csv"),("All files","*.*")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                txt = f.read()
            self.txt_input.delete("1.0", tk.END)
            self.txt_input.insert(tk.END, txt)
        except Exception as e:
            messagebox.showerror("Errore", str(e))

    def save_analysis(self):
        path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text files","*.txt")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.analysis_output.get("1.0", tk.END))
            messagebox.showinfo("Salvato", "Analisi salvata.")
        except Exception as e:
            messagebox.showerror("Errore", str(e))

    def analyze_text(self):
        text = self.txt_input.get("1.0", tk.END).strip()
        if not text:
            self.analysis_output.delete("1.0", tk.END)
            self.analysis_output.insert(tk.END, "Nessun testo.")
            return
        # counts
        chars = len(text)
        words = [w.lower() for w in ''.join(ch if ch.isalnum() or ch.isspace() else ' ' for ch in text).split() if w]
        words_count = len(words)
        sentences = max(0, sum(1 for ch in text if ch in ".!?"))
        most_common = Counter(words).most_common(10)
        readability = flesch_reading_ease(text)
        # prepare output
        out_lines = []
        out_lines.append(f"Caratteri: {chars}")
        out_lines.append(f"Parole: {words_count}")
        out_lines.append(f"Frasi (approx): {sentences}")
        out_lines.append("")
        out_lines.append("Parole più frequenti:")
        for w, c in most_common:
            out_lines.append(f"  {w}: {c}")
        out_lines.append("")
        out_lines.append(f"Leggibilità (Flesch Reading Ease): {readability if readability is not None else 'N/A'}")
        out_lines.append("")
        out_lines.append("Suggerimenti:")
        if readability is not None:
            if readability >= 90:
                out_lines.append("  Molto facile (scuola elementare).")
            elif readability >= 60:
                out_lines.append("  Facile/Moderato.")
            else:
                out_lines.append("  Difficile - considerare frasi più brevi e parole più semplici.")
        self.analysis_output.delete("1.0", tk.END)
        self.analysis_output.insert(tk.END, "\n".join(out_lines))

    # ---------------------------
    # Password Generator Tab
    # ---------------------------
    def build_pass_tab(self):
        frame = self.tab_pass
        left = ttk.Frame(frame)
        left.pack(side="left", fill="y", padx=8, pady=8)
        right = ttk.Frame(frame)
        right.pack(side="left", expand=1, fill="both", padx=8, pady=8)

        ttk.Label(left, text="Opzioni").pack(anchor="w")
        self.len_var = tk.IntVar(value=16)
        ttk.Label(left, text="Lunghezza").pack(anchor="w")
        ttk.Spinbox(left, from_=4, to=128, textvariable=self.len_var, width=6).pack(anchor="w")
        self.use_lower = tk.BooleanVar(value=True)
        self.use_upper = tk.BooleanVar(value=True)
        self.use_digits = tk.BooleanVar(value=True)
        self.use_symbols = tk.BooleanVar(value=True)
        ttk.Checkbutton(left, text="Lettere minuscole", variable=self.use_lower).pack(anchor="w")
        ttk.Checkbutton(left, text="Lettere maiuscole", variable=self.use_upper).pack(anchor="w")
        ttk.Checkbutton(left, text="Cifre", variable=self.use_digits).pack(anchor="w")
        ttk.Checkbutton(left, text="Simboli", variable=self.use_symbols).pack(anchor="w")
        ttk.Button(left, text="Genera", command=self.generate_password).pack(pady=6)
        ttk.Button(left, text="Copia clipboard", command=self.copy_password).pack(pady=2)

        ttk.Label(right, text="Password generata").pack(anchor="w")
        self.entry_password = ttk.Entry(right, font=("Courier", 12))
        self.entry_password.pack(fill="x")
        ttk.Label(right, text="Valutazione").pack(anchor="w", pady=(8,0))
        self.eval_text = tk.Text(right, height=6)
        self.eval_text.pack(fill="x")

    def generate_password(self):
        charset = ""
        if self.use_lower.get():
            charset += string.ascii_lowercase
        if self.use_upper.get():
            charset += string.ascii_uppercase
        if self.use_digits.get():
            charset += string.digits
        if self.use_symbols.get():
            # choose a reasonable subset of symbols
            charset += "!@#$%^&*()-_=+[]{};:,.<>/?"
        if not charset:
            messagebox.showwarning("Attenzione", "Seleziona almeno un tipo di carattere.")
            return
        length = max(4, min(256, int(self.len_var.get())))
        pw = ''.join(secrets.choice(charset) for _ in range(length))
        self.entry_password.delete(0, tk.END)
        self.entry_password.insert(0, pw)
        self.evaluate_password(pw, len(charset))

    def evaluate_password(self, pw, charset_size):
        # estimate entropy
        entropy = len(pw) * log2(charset_size) if charset_size > 0 else 0
        score = ""
        if entropy < 28:
            score = "Molto debole"
        elif entropy < 36:
            score = "Debole"
        elif entropy < 60:
            score = "Moderata"
        elif entropy < 128:
            score = "Forte"
        else:
            score = "Molto forte"
        lines = [
            f"Lunghezza: {len(pw)}",
            f"Charset size stimata: {charset_size}",
            f"Entropia stimata: {entropy:.1f} bit",
            f"Valutazione: {score}"
        ]
        # simple checks
        checks = []
        if any(c.islower() for c in pw): checks.append("minuscole OK")
        if any(c.isupper() for c in pw): checks.append("maiuscole OK")
        if any(c.isdigit() for c in pw): checks.append("cifre OK")
        if any(c in "!@#$%^&*()-_=+[]{};:,.<>/?\\" for c in pw): checks.append("simboli OK")
        lines.append("Caratteristiche: " + ", ".join(checks))
        self.eval_text.delete("1.0", tk.END)
        self.eval_text.insert(tk.END, "\n".join(lines))

    def copy_password(self):
        pw = self.entry_password.get()
        if not pw:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(pw)
        messagebox.showinfo("Copia", "Password copiata negli appunti.")
    

    # ---------------------------
    # Aggiornamenti disponibili (read-only)
    # ---------------------------
    def build_updates_available_tab(self):
        frame = self.tab_updates_available
        left = ttk.Frame(frame)
        left.pack(side="left", fill="y", padx=8, pady=8)
        right = ttk.Frame(frame)
        right.pack(side="left", expand=1, fill="both", padx=8, pady=8)

        ttk.Label(left, text="Aggiornamenti disponibili").pack(anchor="w")
        self.lb_avail = tk.Listbox(left, width=36)
        self.lb_avail.pack(expand=1, fill="y")
        self.lb_avail.bind("<<ListboxSelect>>", self.on_select_avail)

        btns = ttk.Frame(left)
        btns.pack(fill="x", pady=6)
        ttk.Button(btns, text="Aggiorna", command=self.refresh_available_updates).pack(side="left", padx=2)
        ttk.Button(btns, text="Apri release", command=self.open_selected_release).pack(side="left", padx=2)
        ttk.Button(btns, text="Installa", command=self.install_selected_update).pack(side="left", padx=2)

        ttk.Label(right, text="Dettagli release").pack(anchor="w")
        self.txt_avail_details = tk.Text(right, height=12)
        self.txt_avail_details.pack(fill="both", expand=1)

        self.available_releases = []
        self.selected_release_path = None
        self.refresh_available_updates()

    def refresh_available_updates(self):
        # load private releases and show only released entries that are not installed
        releases = load_private_releases()
        available = [r for r in releases if r.get('released') and not r.get('installed')]
        self.available_releases = available
        self.lb_avail.delete(0, tk.END)
        for i, r in enumerate(available):
            v = r.get('version') or '(draft)'
            t = r.get('title') or ''
            d = r.get('date') or ''
            self.lb_avail.insert(tk.END, f"{i+1}. {v} - {t} ({d})")

    def on_select_avail(self, _ev):
        sel = self.lb_avail.curselection()
        if not sel:
            return
        idx = sel[0]
        r = self.available_releases[idx]
        notes = r.get('notes', '')
        self.txt_avail_details.delete('1.0', tk.END)
        self.txt_avail_details.insert(tk.END, notes)
        # store path to release file if exists
        ver = r.get('version')
        path = get_private_release_path(ver) if ver else None
        self.selected_release_path = path if path and os.path.exists(path) else None

    def open_selected_release(self):
        if not self.selected_release_path:
            messagebox.showinfo('Info', 'Nessun file di release disponibile per l' + "'elemento selezionato")
            return
        try:
            os.startfile(self.selected_release_path)
        except Exception as e:
            messagebox.showerror('Errore', str(e))
            
    def install_selected_update(self):
        sel = self.lb_avail.curselection()
        if not sel:
            messagebox.showinfo('Info', 'Seleziona un aggiornamento da installare')
            return
        
        idx = sel[0]
        release = self.available_releases[idx]
        version = release.get('version', 'sconosciuta')
        
        if messagebox.askyesno('Conferma installazione', 
                             f'Vuoi installare la versione {version}?\n\n' +
                             'Nota: questa operazione non può essere annullata.'):
            try:
                # Qui andrà la logica di installazione effettiva
                # Per ora simuliamo solo la rimozione dalla lista
                
                # Marca come installato nel file releases.json
                releases = load_private_releases()
                for r in releases:
                    if r.get('version') == version:
                        r['installed'] = True
                        
                # Salva il file aggiornato
                if not os.path.exists(PRIVATE_RELEASE_HOME):
                    os.makedirs(PRIVATE_RELEASE_HOME)
                with open(PRIVATE_RELEASES_FILE, 'w', encoding='utf-8') as f:
                    json.dump(releases, f, ensure_ascii=False, indent=2)
                
                # Rimuovi dalla lista visuale
                self.available_releases.pop(idx)
                self.lb_avail.delete(idx)
                self.txt_avail_details.delete('1.0', tk.END)
                
                messagebox.showinfo('Successo', f'Versione {version} installata con successo!')
                
            except Exception as e:
                messagebox.showerror('Errore', f'Errore durante l\'installazione: {str(e)}')

# ---------------------------
# Main
# ---------------------------
def main():
    root = tk.Tk()
    app = App(root)
    root.mainloop()

if __name__ == "__main__":
    main()