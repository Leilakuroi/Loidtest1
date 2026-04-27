

1. Master Database Preparation
The script relies on an Excel version of the official EDINET Submitter List to resolve aliases (like "MAMEZO") into machine-readable codes.

Download: Visit the EDINET Website and scroll to the bottom.

https://disclosure2.edinet-fsa.go.jp/weee0010.aspx

Locate: Click the link for EDINETコードリスト (EDINET Code List) to download the .zip file.

Extract: Open the zip and extract the .csv file.

Convert to Excel:

Encoding: The raw CSV is encoded in Shift-JIS (CP932). Open it in Excel (import data from CSV) and ensure the file origin is set to 932: Japanese (Shift-JIS) to prevent garbled text.

Save As: Save the file as an Excel Workbook (.xlsx) format.

Naming: Name the file exactly EdinetcodeDlInfo.xlsx.

Placement: Save this Excel file in your designated Master Folder (e.g., D:\Trade Test or /Users/Documents/Trade_Data).

2. API Configuration
You must provide your EDINET API key in a JSON format. Create a file named key.json with the following structure:

JSON
{
    "api_key": "YOUR_LONG_API_KEY_HERE"
}
Keep this file in a secure location; you will select it when the application starts.

3. How to Use
Launch: Run the script using python your_script_name.py.

Configuration: * Click Load key.json and select your API key file.

Click Browse and select the Master Folder containing your EdinetcodeDlInfo.xlsx.

Define Search:

Date Range: Set the Start and End dates in YYYY-MM-DD format.

Target Aliases: Enter tickers (e.g., 7203), company names (e.g., MAMEZO), or EDINET codes (e.g., E05041) separated by semicolons (;).

Execute: Click START EXTRACTION ENGINE.

5. Output Structure
The script automatically organizes files into subfolders within your Master Folder:

Folders: Named B1_FilerName (e.g., B1_Roodhalsgans_1).

PDFs: Named B1_Timestamp_docID_DocumentType_Report.pdf.

CSVs: The script automatically unzips the data packages and saves the raw .csv files directly in the folder, using the same descriptive naming convention.