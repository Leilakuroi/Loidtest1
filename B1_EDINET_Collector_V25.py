import os
import time
import json
import shutil
import zipfile
import threading
import requests
import pandas as pd
import re
import unicodedata
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

# --- THEME & STYLES ---
class UITheme:
    BG_MAIN = "#F0F2F5"
    BG_CARD = "#FFFFFF"
    PRIMARY = "#1A2B3C"
    SECONDARY = "#606770"
    ACCENT_BLUE = "#0056B3"
    ACCENT_BLUE_HOVER = "#004494"
    ACCENT_GREEN = "#28A745"
    FONT_HEAD = ("Helvetica", 12, "bold")
    FONT_BODY = ("Helvetica", 10)
    FONT_LOG = ("Menlo", 11)

class EdinetB1SequentialTool:
    def __init__(self, root):
        self.root = root
        self.root.title("EDINET B1 Pipeline v25.0 - Sequential Engine")
        self.root.geometry("1150x950")
        self.root.configure(bg=UITheme.BG_MAIN)
        
        self.api_key = None
        self.base_url = "https://api.edinet-fsa.go.jp/api/v2/documents"
        self.is_running = False # Execution Lock
        self.api_cache = {}    # Prevents redundant API hits during sequential runs
        
        self.doc_map = {
            "有価証券報告書": "Annual_Securities_Report",
            "半期報告書": "Semi_Annual_Report",
            "四半期報告書": "Quarterly_Report",
            "大量保有報告書": "Large_Volume_Holding_Report",
            "臨時報告書": "Extraordinary_Report",
            "変更報告書": "Amendment_Report",
            "訂正報告書": "Correction_Report"
        }
        self.setup_ui()

    def setup_ui(self):
        header = tk.Frame(self.root, bg=UITheme.PRIMARY, height=60)
        header.pack(fill="x", side="top")
        tk.Label(header, text="ODIN B1 DATA ENGINE", fg="white", bg=UITheme.PRIMARY, 
                 font=("Helvetica", 16, "bold"), pady=15).pack()

        self.container = tk.Frame(self.root, bg=UITheme.BG_MAIN, padx=30, pady=20)
        self.container.pack(fill="both", expand=True)

        # CONFIGURATION
        config_card = tk.Frame(self.container, bg=UITheme.BG_CARD, padx=15, pady=15, highlightthickness=1, highlightbackground="#DCDFE3")
        config_card.pack(fill="x", pady=(0, 20))

        tk.Label(config_card, text="API Key:", font=UITheme.FONT_HEAD, bg=UITheme.BG_CARD).grid(row=0, column=0, sticky="w")
        self.key_status = tk.Label(config_card, text="JSON Not Loaded", fg="#D93025", bg=UITheme.BG_CARD, font=UITheme.FONT_BODY)
        self.key_status.grid(row=0, column=1, sticky="w", padx=10)
        tk.Button(config_card, text="Load key.json", command=self.load_config).grid(row=0, column=2, sticky="e")

        tk.Label(config_card, text="Master Folder:", font=UITheme.FONT_HEAD, bg=UITheme.BG_CARD).grid(row=1, column=0, sticky="w", pady=(15,0))
        self.folder_input = tk.Entry(config_card, width=75, font=UITheme.FONT_BODY)
        self.folder_input.grid(row=1, column=1, pady=(15,0), padx=10)
        tk.Button(config_card, text="Browse", command=self.browse_folder).grid(row=1, column=2, pady=(15,0))

        # SEARCH CRITERIA
        search_card = tk.Frame(self.container, bg=UITheme.BG_CARD, padx=15, pady=15, highlightthickness=1, highlightbackground="#DCDFE3")
        search_card.pack(fill="x", pady=(0, 20))

        date_box = tk.Frame(search_card, bg=UITheme.BG_CARD)
        date_box.pack(fill="x")
        tk.Label(date_box, text="Fallback Start Date:", bg=UITheme.BG_CARD).pack(side="left")
        self.start_date = tk.Entry(date_box, width=12, font=UITheme.FONT_BODY)
        self.start_date.pack(side="left", padx=5)
        self.start_date.insert(0, (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d"))

        tk.Label(date_box, text="To:", bg=UITheme.BG_CARD, padx=10).pack(side="left")
        self.end_date = tk.Entry(date_box, width=12, font=UITheme.FONT_BODY)
        self.end_date.pack(side="left")
        self.end_date.insert(0, datetime.now().strftime("%Y-%m-%d"))

        tk.Label(search_card, text="Target Aliases (e.g., 7354; SHIFT):", font=UITheme.FONT_BODY, bg=UITheme.BG_CARD).pack(anchor="w", pady=(15, 5))
        self.target_input = tk.Text(search_card, height=3, font=UITheme.FONT_BODY)
        self.target_input.pack(fill="x")
        self.target_input.insert("1.0", "SHIFT; 7354")

        # BLUE BUTTON
        self.btn_frame = tk.Frame(self.container, bg=UITheme.ACCENT_BLUE, cursor="hand2")
        self.btn_frame.pack(fill="x", pady=10)
        self.run_btn_lbl = tk.Label(self.btn_frame, text="START SEQUENTIAL EXTRACTION", fg="white", bg=UITheme.ACCENT_BLUE,
                                    font=("Helvetica", 12, "bold"), pady=15)
        self.run_btn_lbl.pack(fill="both")
        self.run_btn_lbl.bind("<Button-1>", lambda e: self.start_thread())

        # LOGGING
        self.log_box = scrolledtext.ScrolledText(self.container, height=20, font=UITheme.FONT_LOG, bg="#1C1E21", fg="#A8B1C1")
        self.log_box.pack(fill="both", expand=True)

    def log(self, message, clear=False):
        self.log_box.config(state="normal")
        if clear: self.log_box.delete("1.0", tk.END)
        self.log_box.insert(tk.END, f" {datetime.now().strftime('%H:%M:%S')} > {message}\n")
        self.log_box.see(tk.END)
        self.log_box.config(state="disabled")

    def browse_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.folder_input.delete(0, tk.END)
            self.folder_input.insert(0, folder)

    def load_config(self):
        file_path = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")])
        if not file_path: return
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                self.api_key = config.get("api_key")
                self.key_status.config(text="Authenticated", fg=UITheme.ACCENT_GREEN)
                self.log("Authentication Validated.")
        except Exception as e: messagebox.showerror("Error", str(e))

    def get_stock_history(self, alias):
        master_dir = self.folder_input.get().strip()
        stock_dir = os.path.join(master_dir, f"B1_{alias}")
        history_file = os.path.join(stock_dir, "sync_history.json")
        if os.path.exists(history_file):
            with open(history_file, 'r') as f: return json.load(f)
        return {}

    def update_stock_history(self, alias, ed_code, last_doc_date):
        master_dir = self.folder_input.get().strip()
        stock_dir = os.path.join(master_dir, f"B1_{alias}")
        os.makedirs(stock_dir, exist_ok=True)
        history_file = os.path.join(stock_dir, "sync_history.json")
        history = self.get_stock_history(alias)
        if ed_code not in history or last_doc_date > history[ed_code]:
            history[ed_code] = last_doc_date
            with open(history_file, 'w') as f: json.dump(history, f, indent=4)

    def smart_normalize(self, text):
        if not isinstance(text, str) or text == "nan": return ""
        return unicodedata.normalize('NFKC', text).upper().strip()

    def clean_keyword(self, name):
        suffixes = [r"\bCO\b", r"\bLTD\b", r"\bINC\b", r"\bCORP\b", r"\bPLC\b", r"\bK\.K\.\b", r"\bG\.K\.\b", r"\.", r","]
        clean = self.smart_normalize(name)
        for s in suffixes: clean = re.sub(s, "", clean)
        return clean.strip()

    def scrape_web_name(self, ticker):
        headers = {'User-Agent': 'Mozilla/5.0'}
        for page in range(1, 9):
            url = f"https://stockanalysis.com/list/tokyo-stock-exchange/{'' if page == 1 else '?page=' + str(page)}"
            try:
                r = requests.get(url, headers=headers, timeout=10)
                soup = BeautifulSoup(r.text, 'lxml')
                table = soup.find("table", id="main-table")
                if not table: continue
                for row in table.find_all("tr")[1:]:
                    cells = row.find_all("td")
                    if len(cells) > 2 and cells[1].text.strip() == ticker: return cells[2].text.strip()
            except: continue
        return None

    def get_targets(self, excel_path, raw_aliases):
        """Resolves aliases and returns a mapping of Code -> (Alias, Start Date, JP Name)."""
        if not os.path.exists(excel_path):
            self.log("ERROR: Master Excel missing.")
            return {}
        
        ui_start_dt = datetime.strptime(self.start_date.get().strip(), "%Y-%m-%d")
        processed_keywords = []
        for a in raw_aliases:
            norm_a = self.smart_normalize(a)
            if norm_a.isdigit() and len(norm_a) == 4:
                name = self.scrape_web_name(norm_a)
                if name: processed_keywords.append((a, self.clean_keyword(name)))
                else: self.root.after(0, lambda t=a: messagebox.showwarning("No Match", f"Ticker {t} not found."))
            else: processed_keywords.append((a, norm_a))

        resolved_map = {}
        try:
            df = pd.read_excel(excel_path, skiprows=1)
            for _, row in df.iterrows():
                ed_code = str(row.iloc[0]).strip()
                raw_jp = str(row.iloc[6])
                name_jp, name_en = self.smart_normalize(raw_jp), self.smart_normalize(str(row.iloc[7]))
                ticker_5 = str(row.iloc[11]).strip()

                for orig_alias, keyword in processed_keywords:
                    if keyword in name_en or keyword in name_jp or keyword == ticker_5:
                        if ed_code not in resolved_map:
                            history = self.get_stock_history(orig_alias)
                            last_found = history.get(ed_code)
                            start_dt = datetime.strptime(last_found, "%Y-%m-%d") + timedelta(days=1) if last_found else ui_start_dt
                            resolved_map[ed_code] = {"alias": orig_alias, "start_date": start_dt, "jp_name": raw_jp}
                            self.log(f"   [MAPPED] {orig_alias} -> {ed_code} ({raw_jp}) | Start: {start_dt.strftime('%Y-%m-%d')}")
        except Exception as e: self.log(f"Excel Error: {e}")
        return resolved_map

    def start_thread(self):
        if self.is_running: return # Execution Lock
        if not self.api_key:
            messagebox.showerror("Error", "Load key.json first.")
            return
        self.is_running = True
        self.run_btn_lbl.config(text="PROCESSING...", bg=UITheme.SECONDARY)
        self.btn_frame.config(bg=UITheme.SECONDARY)
        threading.Thread(target=self.execute_workflow, daemon=True).start()

    def translate_doc_type(self, jp_desc):
        for jp_key, en_val in self.doc_map.items():
            if jp_key in jp_desc: return en_val
        return "General_Filing"

    def fetch_api_with_cache(self, date_str):
        if date_str in self.api_cache: return self.api_cache[date_str]
        try:
            r = requests.get(f"{self.base_url}.json", params={"date": date_str, "type": "2", "Subscription-Key": self.api_key}, timeout=20)
            if r.status_code == 200:
                self.api_cache[date_str] = r.json().get("results", [])
                return self.api_cache[date_str]
        except: pass
        return []

    def execute_workflow(self):
        master_dir = self.folder_input.get().strip()
        excel_path = os.path.join(master_dir, "EdinetcodeDlInfo.xlsx")
        self.api_cache = {} # Reset cache per session
        try:
            self.log("STARTING SEQUENTIAL SESSION...", clear=True)
            raw_input = self.target_input.get("1.0", "end").split(";")
            aliases = [a.strip() for a in raw_input if a.strip()]
            
            target_map = self.get_targets(excel_path, aliases)
            if not target_map: return

            ui_end = datetime.strptime(self.end_date.get().strip(), "%Y-%m-%d")

            # OUTER LOOP: Processing Stock by Stock
            for ed_code, meta in target_map.items():
                alias = meta["alias"]
                curr = meta["start_date"]
                self.log(f"--- Processing Stock: {alias} ({ed_code}) ---")
                
                if curr > ui_end:
                    self.log(f"   [SKIPPED] {alias} is already up to date.")
                    continue

                # INNER LOOP: Date range for this specific stock
                while curr <= ui_end:
                    date_str = curr.strftime("%Y-%m-%d")
                    self.log(f"   Scanning: {date_str}")
                    
                    results = self.fetch_api_with_cache(date_str)
                    for doc in results:
                        roles = [doc.get("edinetCode"), doc.get("issuerEdinetCode"), doc.get("subjectEdinetCode")]
                        if ed_code in roles:
                            self.download_and_extract(doc, master_dir, date_str, alias)
                            self.update_stock_history(alias, ed_code, date_str)
                    
                    curr += timedelta(days=1)
                    time.sleep(0.5) # Prevent rapid fire

            self.log("SEQUENTIAL SYNC COMPLETED.")
        except Exception as e: self.log(f"CRITICAL ERROR: {e}")
        finally:
            self.is_running = False
            self.run_btn_lbl.config(text="START EXTRACTION ENGINE", bg=UITheme.ACCENT_BLUE)
            self.btn_frame.config(bg=UITheme.ACCENT_BLUE)

    def download_and_extract(self, doc, master_dir, date_str, alias):
        doc_id, jp_desc = doc.get("docID"), str(doc.get("docDescription"))
        en_desc = self.translate_doc_type(jp_desc)
        stock_dir = os.path.join(master_dir, f"B1_{alias}")
        os.makedirs(stock_dir, exist_ok=True)
        ts = doc.get('submissionDatetime', date_str).replace(':','').replace('-','').replace(' ','_')[:12]
        prefix = f"B1_{ts}_{doc_id}_{en_desc}"

        if doc.get("pdfFlag") == "1":
            r = requests.get(f"{self.base_url}/{doc_id}", params={"type": 2, "Subscription-Key": self.api_key}, stream=True)
            if r.status_code == 200:
                with open(os.path.join(stock_dir, f"{prefix}_Report.pdf"), 'wb') as f: shutil.copyfileobj(r.raw, f)
                self.log(f"      [SAVED] {en_desc}")

        if doc.get("csvFlag") == "1":
            zip_p = os.path.join(stock_dir, f"{prefix}_Temp.zip")
            r = requests.get(f"{self.base_url}/{doc_id}", params={"type": 5, "Subscription-Key": self.api_key}, stream=True)
            if r.status_code == 200:
                with open(zip_p, 'wb') as f: shutil.copyfileobj(r.raw, f)
                try:
                    with zipfile.ZipFile(zip_p, 'r') as z:
                        for m in z.namelist():
                            if m.endswith('.csv'):
                                ext = z.extract(m, stock_dir)
                                shutil.move(ext, os.path.join(stock_dir, f"{prefix}_{os.path.basename(m)}"))
                    os.remove(zip_p)
                    shutil.rmtree(os.path.join(stock_dir, 'XBRL_TO_CSV'), ignore_errors=True)
                except: pass

if __name__ == "__main__":
    root = tk.Tk(); app = EdinetB1SequentialTool(root); root.mainloop()