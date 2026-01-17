"""Script to set up Google Sheets structure."""
import gspread
from google.oauth2.service_account import Credentials
from bot.config import (
    GOOGLE_SHEETS_ID,
    GOOGLE_CREDENTIALS_PATH,
    SHEET_REFERENCE,
    SHEET_TEMPLATE,
    SHEET_AUDIT_LOG,
    SHEET_MONTHLY_SUMMARY,
    SHEET_USERS,
    SHEET_RENTAL,
)


def setup_sheets():
    """Set up Google Sheets with required structure."""
    # Initialize client
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(GOOGLE_CREDENTIALS_PATH, scopes=scope)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(GOOGLE_SHEETS_ID)
    
    print("Setting up Google Sheets structure...")
    
    # 1. Create Справочник sheet
    try:
        ref_sheet = spreadsheet.worksheet(SHEET_REFERENCE)
        print(f"✓ Sheet '{SHEET_REFERENCE}' already exists")
    except gspread.exceptions.WorksheetNotFound:
        ref_sheet = spreadsheet.add_worksheet(title=SHEET_REFERENCE, rows=100, cols=10)
        # Set headers
        ref_sheet.update("A1:D1", [["OperationDirection", "Категория", "Тип", "Активно"]])
        # Add example data
        ref_sheet.update("A2:D5", [
            ["IN", "Банковские", "Перевод", "TRUE"],
            ["OUT", "Банковские", "Проценты", "TRUE"],
            ["OUT", "Офисные", "Доверенности", "TRUE"],
            ["IN", "Прочие", "Прочее", "TRUE"],
        ])
        print(f"✓ Created sheet '{SHEET_REFERENCE}'")
    
    # 2. Create Шаблон_Сотрудника sheet
    try:
        template_sheet = spreadsheet.worksheet(SHEET_TEMPLATE)
        print(f"✓ Sheet '{SHEET_TEMPLATE}' already exists")
    except gspread.exceptions.WorksheetNotFound:
        template_sheet = spreadsheet.add_worksheet(title=SHEET_TEMPLATE, rows=100, cols=15)
        # Set headers - add Address (H) and М/М (I) columns
        headers = ["Дата", "Поступление (+)", "Списание (-)", "Категория", "Тип", "Описание", "Остаток после операции", "Адрес", "М/М"]
        template_sheet.update("A1:I1", [headers])
        
        # Format header row
        template_sheet.format("A1:I1", {
            "backgroundColor": {"red": 0.2, "green": 0.6, "blue": 0.9},
            "textFormat": {"bold": True},
        })
        
        # Set M1 placeholder (will be filled with employee name when sheet is created)
        template_sheet.update("M1", [["Имя сотрудника"]])
        
        # Add balance formula in G2 (first data row)
        # Formula uses semicolons for Russian locale: =IF(ROW()=2; IF(B2<>""; B2; -C2); INDIRECT("G"&ROW()-1) + IF(B2<>""; B2; 0) - IF(C2<>""; C2; 0))
        formula = '=IF(ROW()=2; IF(B2<>""; B2; -C2); INDIRECT("G"&ROW()-1) + IF(B2<>""; B2; 0) - IF(C2<>""; C2; 0))'
        template_sheet.update("G2", [[formula]], value_input_option="USER_ENTERED")
        
        # Copy formula to more rows (for when data is added)
        # We'll handle this dynamically, but set up a few rows
        for row in range(3, 11):
            formula_row = f'=IF(ROW()={row}; IF(B{row}<>""; B{row}; -C{row}); INDIRECT("G"&ROW()-1) + IF(B{row}<>""; B{row}; 0) - IF(C{row}<>""; C{row}; 0))'
            template_sheet.update(f"G{row}", [[formula_row]], value_input_option="USER_ENTERED")
        
        print(f"✓ Created sheet '{SHEET_TEMPLATE}'")
    
    # 3. Create Audit_Log sheet
    try:
        audit_sheet = spreadsheet.worksheet(SHEET_AUDIT_LOG)
        print(f"✓ Sheet '{SHEET_AUDIT_LOG}' already exists")
    except gspread.exceptions.WorksheetNotFound:
        audit_sheet = spreadsheet.add_worksheet(title=SHEET_AUDIT_LOG, rows=1000, cols=10)
        # Set headers
        headers = ["Timestamp", "Пользователь", "Лист", "Действие", "Поле", "Старое значение", "Новое значение"]
        audit_sheet.update("A1:G1", [headers])
        
        # Format header row
        audit_sheet.format("A1:G1", {
            "backgroundColor": {"red": 0.9, "green": 0.2, "blue": 0.2},
            "textFormat": {"bold": True},
        })
        
        print(f"✓ Created sheet '{SHEET_AUDIT_LOG}'")
    
    # 4. Create Итоги_Месяц sheet
    try:
        summary_sheet = spreadsheet.worksheet(SHEET_MONTHLY_SUMMARY)
        print(f"✓ Sheet '{SHEET_MONTHLY_SUMMARY}' already exists")
    except gspread.exceptions.WorksheetNotFound:
        summary_sheet = spreadsheet.add_worksheet(title=SHEET_MONTHLY_SUMMARY, rows=1000, cols=10)
        # Set headers
        headers = ["Сотрудник", "Месяц", "Поступления", "Списания", "Чистый результат"]
        summary_sheet.update("A1:E1", [headers])
        
        # Format header row
        summary_sheet.format("A1:E1", {
            "backgroundColor": {"red": 0.2, "green": 0.8, "blue": 0.2},
            "textFormat": {"bold": True},
        })
        
        print(f"✓ Created sheet '{SHEET_MONTHLY_SUMMARY}'")
    
    # 5. Create Users sheet
    try:
        users_sheet = spreadsheet.worksheet(SHEET_USERS)
        print(f"✓ Sheet '{SHEET_USERS}' already exists")
    except gspread.exceptions.WorksheetNotFound:
        users_sheet = spreadsheet.add_worksheet(title=SHEET_USERS, rows=100, cols=10)
        # Set headers
        headers = [
            "Telegram User ID",
            "Имя сотрудника",
            "Название листа",
            "Дата регистрации",
            "Активен"
        ]
        users_sheet.update("A1:E1", [headers])
        
        # Format header row
        users_sheet.format("A1:E1", {
            "backgroundColor": {"red": 0.3, "green": 0.5, "blue": 0.8},
            "textFormat": {"bold": True},
        })
        
        print(f"✓ Created sheet '{SHEET_USERS}'")
    
    print("\n✓ Google Sheets setup completed!")
    print("\nNext steps:")
    print("1. Share the Google Sheet with the service account email")
    print("2. Grant Editor permissions")
    print("3. Add reference data to 'Справочник' sheet")
    print("4. Run the bot: python -m bot.main")


if __name__ == "__main__":
    setup_sheets()

