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

class EdinetB1PrecisionTool:
    def __init__(self, root):
        self.root = root
        self.root.title("EDINET B1 Pipeline v23.1 - Precision Sync")
        self.root.geometry("1150x950")
        self.root.configure(bg=UITheme.BG_MAIN)
        
        self.api_key = None
        self.base_url = "https://api.edinet-fsa.go.jp/api/v2/documents"
        self.code_to_alias_map = {}
        self.code_metadata = {}
        self.alias_last_found_dates = {}
        
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

        tk.Label(search_card, text="Target Aliases:", font=UITheme.FONT_BODY, bg=UITheme.BG_CARD).pack(anchor="w", pady=(15, 5))
        self.target_input = tk.Text(search_card, height=3, font=UITheme.FONT_BODY)
        self.target_input.pack(fill="x")
        self.target_input.insert("1.0", "7354; SHIFT")

        self.btn_frame = tk.Frame(self.container, bg=UITheme.ACCENT_BLUE, cursor="hand2")
        self.btn_frame.pack(fill="x", pady=10)
        self.run_btn_lbl = tk.Label(self.btn_frame, text="START EXTRACTION ENGINE", fg="white", bg=UITheme.ACCENT_BLUE,
                                    font=("Helvetica", 12, "bold"), pady=15)
        self.run_btn_lbl.pack(fill="both")
        self.run_btn_lbl.bind("<Button-1>", lambda e: self.start_thread())
        self.run_btn_lbl.bind("<Enter>", lambda e: self.btn_frame.config(bg=UITheme.ACCENT_BLUE_HOVER))
        self.run_btn_lbl.bind("<Leave>", lambda e: self.btn_frame.config(bg=UITheme.ACCENT_BLUE))

        self.log_box = scrolledtext.ScrolledText(self.container, height=20, font=UITheme.FONT_LOG, bg="#1C1E21", fg="#A8B1C1")
        self.log_box.pack(fill="both", expand=True)

    def log(self, message):
        self.log_box.config(state="normal")
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

    def get_history_path(self):
        return os.path.join(self.folder_input.get().strip(), "search_history.json")

    def load_history(self):
        path = self.get_history_path()
        if os.path.exists(path):
            with open(path, 'r') as f: return json.load(f)
        return {}

    def update_history_entry(self, alias, last_doc_date):
        history = self.load_history()
        if alias not in history or last_doc_date > history[alias]:
            history[alias] = last_doc_date
            with open(self.get_history_path(), 'w') as f:
                json.dump(history, f, indent=4)

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
                    if len(cells) > 2 and cells[1].text.strip() == ticker:
                        return cells[2].text.strip()
            except: continue
        return None

    def get_codes_by_aliases(self, excel_path, aliases):
        if not os.path.exists(excel_path):
            self.log("ERROR: EdinetcodeDlInfo.xlsx missing.")
            return []
        
        # 1. Capture the UI Start Date for new targets
        try:
            ui_start_dt = datetime.strptime(self.start_date.get().strip(), "%Y-%m-%d")
        except:
            ui_start_dt = datetime.now() - timedelta(days=7)

        self.code_to_alias_map = {}
        processed_targets = []
        history = self.load_history()

        for a in aliases:
            # 2. Use History OR UI Start Date - 1 day
            if a in history:
                self.log(f"[TRACKER] {a} existing. High-water mark: {history[a]}")
                self.alias_last_found_dates[a] = datetime.strptime(history[a], "%Y-%m-%d")
            else:
                self.alias_last_found_dates[a] = ui_start_dt - timedelta(days=1)
                self.log(f"[TRACKER] {a} is new. Starting from chosen date: {ui_start_dt.strftime('%Y-%m-%d')}")

            norm_a = self.smart_normalize(a)
            if norm_a.isdigit() and len(norm_a) == 4:
                name = self.scrape_web_name(norm_a)
                if name: processed_targets.append((a, self.clean_keyword(name)))
                else: self.root.after(0, lambda t=a: messagebox.showwarning("Alert: No Match", f"Ticker {t} not found."))
            else:
                processed_targets.append((a, norm_a))

        try:
            df = pd.read_excel(excel_path, skiprows=1)
            for _, row in df.iterrows():
                ed_code = str(row.iloc[0]).strip()
                raw_jp, raw_en = str(row.iloc[6]), str(row.iloc[7])
                name_jp, name_en = self.smart_normalize(raw_jp), self.smart_normalize(raw_en)
                ticker_5 = str(row.iloc[11]).strip()

                for original, keyword in processed_targets:
                    if keyword in name_en or keyword in name_jp or keyword == ticker_5:
                        if ed_code not in self.code_to_alias_map:
                            self.code_to_alias_map[ed_code] = original
                            self.code_metadata[ed_code] = {"jp": raw_jp, "en": raw_en}
                            # TRANSPARENCY LOG
                            self.log(f"   [MAPPED] {original} -> {ed_code}")
                            self.log(f"            - JP: {raw_jp}")
                            self.log(f"            - EN: {raw_en}")
        except Exception as e: self.log(f"Excel Error: {e}")
        return list(self.code_to_alias_map.keys())

    def start_thread(self):
        if not self.api_key:
            messagebox.showerror("Error", "Load key.json first.")
            return
        threading.Thread(target=self.execute_workflow, daemon=True).start()

    def translate_doc_type(self, jp_desc):
        for jp_key, en_val in self.doc_map.items():
            if jp_key in jp_desc: return en_val
        return "General_Filing"

    def execute_workflow(self):
        master_dir = self.folder_input.get().strip()
        excel_path = os.path.join(master_dir, "EdinetcodeDlInfo.xlsx")
        try:
            self.run_btn_lbl.config(text="SCANNING...", state="disabled")
            raw_input = self.target_input.get("1.0", "end").split(";")
            aliases = [a.strip() for a in raw_input if a.strip()]
            
            target_codes = self.get_codes_by_aliases(excel_path, aliases)
            if not target_codes: return

            ui_start = datetime.strptime(self.start_date.get().strip(), "%Y-%m-%d")
            history_min = min(self.alias_last_found_dates.values())
            
            # Global scan starts from the earliest point needed by any target
            effective_start = min(ui_start, history_min + timedelta(days=1))
            end_dt = datetime.strptime(self.end_date.get().strip(), "%Y-%m-%d")
            
            self.log(f"Sync range: {effective_start.strftime('%Y-%m-%d')} to {end_dt.strftime('%Y-%m-%d')}")
            
            curr = effective_start
            while curr <= end_dt:
                date_str = curr.strftime("%Y-%m-%d")
                
                # --- FEATURE RESTORED: PROGRESS TRACKING ---
                self.log(f"--- Processing Date: {date_str} ---")
                
                r = requests.get(f"{self.base_url}.json", params={"date": date_str, "type": "2", "Subscription-Key": self.api_key}, timeout=20)
                if r.status_code == 200:
                    results = r.json().get("results", [])
                    for doc in results:
                        roles = [doc.get("edinetCode"), doc.get("issuerEdinetCode"), doc.get("subjectEdinetCode")]
                        matched_alias = next((self.code_to_alias_map[c] for c in roles if c in self.code_to_alias_map), None)
                        
                        if matched_alias:
                            if curr > self.alias_last_found_dates[matched_alias]:
                                self.download_and_extract(doc, master_dir, date_str, matched_alias)
                                self.update_history_entry(matched_alias, date_str)
                curr += timedelta(days=1)
                time.sleep(1)
            
            self.log("PRECISION SYNC COMPLETED.")
        finally:
            self.run_btn_lbl.config(text="START EXTRACTION ENGINE", state="normal")

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
                self.log(f"   [SAVED] {alias} - {en_desc}")

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
    root = tk.Tk(); app = EdinetB1PrecisionTool(root); root.mainloop()