import os
import time
import json
import shutil
import zipfile
import threading
import requests
import pandas as pd
from datetime import datetime, timedelta

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

# --- THEME & STYLES ---
class UITheme:
    BG_MAIN = "#F0F2F5"
    BG_CARD = "#FFFFFF"
    PRIMARY = "#1A2B3C"
    SECONDARY = "#606770"
    ACCENT_BLUE = "#0056B3"
    ACCENT_GREEN = "#28A745"
    FONT_HEAD = ("Helvetica", 12, "bold")
    FONT_BODY = ("Helvetica", 10)
    FONT_LOG = ("Menlo", 11)

class EdinetB1AliasGroupingTool:
    def __init__(self, root):
        self.root = root
        self.root.title("EDINET B1 Pipeline v18.0 - Alias Grouping")
        self.root.geometry("1100x950")
        self.root.configure(bg=UITheme.BG_MAIN)
        
        self.api_key = None
        self.base_url = "https://api.edinet-fsa.go.jp/api/v2/documents"
        self.code_to_alias_map = {} # Maps E-code back to your typed alias
        
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
        tk.Label(header, text="EDINET B1 DATA ENGINE", fg="white", bg=UITheme.PRIMARY, 
                 font=("Helvetica", 16, "bold"), pady=15).pack()

        self.container = tk.Frame(self.root, bg=UITheme.BG_MAIN, padx=30, pady=20)
        self.container.pack(fill="both", expand=True)

        # CONFIGURATION CARD
        self.create_section_label("1. CONFIGURATION")
        config_card = tk.Frame(self.container, bg=UITheme.BG_CARD, padx=15, pady=15, highlightthickness=1, highlightbackground="#DCDFE3")
        config_card.pack(fill="x", pady=(0, 20))

        tk.Label(config_card, text="API Key:", font=UITheme.FONT_HEAD, bg=UITheme.BG_CARD).grid(row=0, column=0, sticky="w")
        self.key_status = tk.Label(config_card, text="JSON Not Loaded", fg="#D93025", bg=UITheme.BG_CARD, font=UITheme.FONT_BODY)
        self.key_status.grid(row=0, column=1, sticky="w", padx=10)
        tk.Button(config_card, text="Load key.json", command=self.load_config).grid(row=0, column=2, sticky="e")

        tk.Label(config_card, text="Master Folder:", font=UITheme.FONT_HEAD, bg=UITheme.BG_CARD).grid(row=1, column=0, sticky="w", pady=(15,0))
        self.folder_input = tk.Entry(config_card, width=70, font=UITheme.FONT_BODY)
        self.folder_input.grid(row=1, column=1, pady=(15,0), padx=10)
        tk.Button(config_card, text="Browse", command=self.browse_folder).grid(row=1, column=2, pady=(15,0))

        # SEARCH CRITERIA CARD
        self.create_section_label("2. SEARCH CRITERIA")
        search_card = tk.Frame(self.container, bg=UITheme.BG_CARD, padx=15, pady=15, highlightthickness=1, highlightbackground="#DCDFE3")
        search_card.pack(fill="x", pady=(0, 20))

        date_box = tk.Frame(search_card, bg=UITheme.BG_CARD)
        date_box.pack(fill="x")
        self.start_date = tk.Entry(date_box, width=12, font=UITheme.FONT_BODY)
        self.start_date.pack(side="left")
        self.start_date.insert(0, (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d"))
        tk.Label(date_box, text="to", bg=UITheme.BG_CARD, padx=10).pack(side="left")
        self.end_date = tk.Entry(date_box, width=12, font=UITheme.FONT_BODY)
        self.end_date.pack(side="left")
        self.end_date.insert(0, datetime.now().strftime("%Y-%m-%d"))

        tk.Label(search_card, text="Target Aliases (e.g., MAMEZO; 7203):", font=UITheme.FONT_BODY, bg=UITheme.BG_CARD).pack(anchor="w", pady=(15, 5))
        self.target_input = tk.Text(search_card, height=3, font=UITheme.FONT_BODY, highlightthickness=1, highlightbackground="#DCDFE3")
        self.target_input.pack(fill="x")
        self.target_input.insert("1.0", "MAMEZO")

        self.run_btn = tk.Button(self.container, text="START EXTRACTION ENGINE", bg=UITheme.ACCENT_BLUE, fg="white", 
                                 font=("Helvetica", 12, "bold"), pady=12, command=self.start_thread)
        self.run_btn.pack(fill="x", pady=10)

        self.log_box = scrolledtext.ScrolledText(self.container, height=18, font=UITheme.FONT_LOG, bg="#1C1E21", fg="#A8B1C1")
        self.log_box.pack(fill="both", expand=True)

    def create_section_label(self, text):
        tk.Label(self.container, text=text, font=("Helvetica", 10, "bold"), fg=UITheme.SECONDARY, bg=UITheme.BG_MAIN).pack(anchor="w", pady=(0, 5))

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
                self.key_status.config(text="Key Active", fg=UITheme.ACCENT_GREEN)
                self.log("Authenticated.")
        except Exception as e: messagebox.showerror("Error", f"JSON Error: {e}")

    def get_codes_by_aliases(self, excel_path, aliases):
        if not os.path.exists(excel_path):
            self.log("ERROR: EdinetcodeDlInfo.xlsx not found.")
            return []
        
        self.code_to_alias_map = {}
        self.log("Mapping aliases to official IDs...")
        try:
            df = pd.read_excel(excel_path, skiprows=1)
            for _, row in df.iterrows():
                ed_code = str(row.iloc[0]).strip()
                name_jp, name_en = str(row.iloc[6]).upper(), str(row.iloc[7]).upper()
                ticker = str(row.iloc[11]).strip() if len(row) > 11 else ""
                
                for a in aliases:
                    if a == ed_code or a == ticker or a in name_jp or a in name_en:
                        self.code_to_alias_map[ed_code] = a # Link ID to YOUR alias
                        self.log(f"   [MAPPED] {a} -> {ed_code}")
        except Exception as e: self.log(f"Excel Error: {e}")
        return list(self.code_to_alias_map.keys())

    def translate_doc_type(self, jp_desc):
        for jp_key, en_val in self.doc_map.items():
            if jp_key in jp_desc: return en_val
        return "General_Filing"

    def start_thread(self):
        if not self.api_key:
            messagebox.showerror("Error", "Load key.json first.")
            return
        threading.Thread(target=self.execute_workflow, daemon=True).start()

    def execute_workflow(self):
        master_dir = self.folder_input.get().strip()
        excel_path = os.path.join(master_dir, "EdinetcodeDlInfo.xlsx")
        try:
            self.run_btn.config(state="disabled")
            aliases = [a.strip().upper() for a in self.target_input.get("1.0", "end").split(";") if a.strip()]
            target_codes = self.get_codes_by_aliases(excel_path, aliases)
            
            start_dt = datetime.strptime(self.start_date.get().strip(), "%Y-%m-%d")
            end_dt = datetime.strptime(self.end_date.get().strip(), "%Y-%m-%d")

            curr = start_dt
            while curr <= end_dt:
                date_str = curr.strftime("%Y-%m-%d")
                self.log(f"Scanning: {date_str}")
                res = requests.get(f"{self.base_url}.json", params={"date": date_str, "type": "2", "Subscription-Key": self.api_key}, timeout=20)
                
                if res.status_code == 200:
                    for doc in res.json().get("results", []):
                        roles = [doc.get("edinetCode"), doc.get("issuerEdinetCode"), doc.get("subjectEdinetCode")]
                        
                        # Find which alias triggered the match
                        matched_alias = None
                        for code in roles:
                            if code in self.code_to_alias_map:
                                matched_alias = self.code_to_alias_map[code]
                                break
                        
                        # Fallback to direct name string match if no ID match
                        if not matched_alias:
                            filer_name = str(doc.get("filerName")).upper()
                            for a in aliases:
                                if a in filer_name:
                                    matched_alias = a
                                    break

                        if matched_alias:
                            self.download_and_extract(doc, master_dir, date_str, matched_alias)
                curr += timedelta(days=1)
                time.sleep(1)
            self.log("FINISH.")
        finally: self.run_btn.config(state="normal")

    def download_and_extract(self, doc, master_dir, date_str, alias):
        doc_id = doc.get("docID")
        en_desc = self.translate_doc_type(str(doc.get("docDescription")))
        
        # USE THE ALIAS FOR THE FOLDER NAME
        stock_dir = os.path.join(master_dir, f"B1_{alias}")
        os.makedirs(stock_dir, exist_ok=True)
        
        ts = doc.get('submissionDatetime', date_str).replace(':','').replace('-','').replace(' ','_')[:12]
        prefix = f"B1_{ts}_{doc_id}_{en_desc}"

        # PDF Download
        if doc.get("pdfFlag") == "1":
            r = requests.get(f"{self.base_url}/{doc_id}", params={"type": 2, "Subscription-Key": self.api_key}, stream=True)
            if r.status_code == 200:
                with open(os.path.join(stock_dir, f"{prefix}_Report.pdf"), 'wb') as f:
                    shutil.copyfileobj(r.raw, f)
                self.log(f"   [SAVED] {alias} - {en_desc}")

        # CSV Zip + Direct Extraction
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
                    self.log(f"   [EXTRACTED] {alias} - {en_desc}")
                except Exception: pass

if __name__ == "__main__":
    root = tk.Tk(); app = EdinetB1AliasGroupingTool(root); root.mainloop()