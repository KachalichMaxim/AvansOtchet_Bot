"""Script to fix formulas in existing employee sheets."""
import gspread
from google.oauth2.service_account import Credentials
from bot.config import (
    GOOGLE_SHEETS_ID,
    GOOGLE_CREDENTIALS_PATH,
    SHEET_TEMPLATE,
)


def fix_formulas_in_sheet(sheet_name: str):
    """Fix balance formulas in a sheet to use semicolons."""
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(GOOGLE_CREDENTIALS_PATH, scopes=scope)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(GOOGLE_SHEETS_ID)
    
    try:
        sheet = spreadsheet.worksheet(sheet_name)
        print(f"Fixing formulas in sheet: {sheet_name}")
        
        # Get all values to find data rows
        all_values = sheet.get_all_values()
        if len(all_values) <= 1:
            print(f"  No data rows found")
            return
        
        # Fix formulas starting from row 2 (first data row)
        for row_num in range(2, len(all_values) + 1):
            # Formula with semicolons for Russian locale
            formula = f'=IF(ROW()={row_num}; IF(B{row_num}<>""; B{row_num}; -C{row_num}); INDIRECT("G"&ROW()-1) + IF(B{row_num}<>""; B{row_num}; 0) - IF(C{row_num}<>""; C{row_num}; 0))'
            sheet.update(f"G{row_num}", [[formula]], value_input_option="USER_ENTERED")
            print(f"  Fixed formula in row {row_num}")
        
        print(f"✓ Completed fixing formulas in {sheet_name}")
    except Exception as e:
        print(f"Error fixing {sheet_name}: {e}")


def fix_all_employee_sheets():
    """Fix formulas in all employee sheets."""
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(GOOGLE_CREDENTIALS_PATH, scopes=scope)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(GOOGLE_SHEETS_ID)
    
    # Get all worksheets
    worksheets = spreadsheet.worksheets()
    
    # System sheets to skip
    system_sheets = ["Справочник", "Шаблон_Сотрудника", "Audit_Log", "Итоги_Месяц"]
    
    employee_sheets = [ws for ws in worksheets if ws.title not in system_sheets]
    
    print(f"Found {len(employee_sheets)} employee sheet(s)")
    
    for sheet in employee_sheets:
        fix_formulas_in_sheet(sheet.title)
    
    # Also fix template
    print("\nFixing template sheet...")
    fix_formulas_in_sheet(SHEET_TEMPLATE)


if __name__ == "__main__":
    fix_all_employee_sheets()
    print("\nDone! All formulas have been updated to use semicolons.")

