"""Script to update all existing rows in Итоги_месяца with formulas."""
from bot.sheets_client import SheetsClient

def main():
    print("Updating all monthly summary rows with new formulas...")
    client = SheetsClient()
    
    # Force update all rows (even if they already have formulas)
    summary_sheet = client._get_sheet("Итоги_месяца")
    if not summary_sheet:
        print("Sheet 'Итоги_месяца' not found")
        return
    
    values = summary_sheet.get_all_values()
    if len(values) <= 1:
        print("No data rows found")
        return
    
    updated_count = 0
    for i, row in enumerate(values[1:], start=2):
        if len(row) < 2:
            continue
        
        employee_name = row[0].strip() if row[0] else ""
        month = row[1].strip() if len(row) > 1 and row[1] else ""
        
        if not employee_name or not month:
            continue
        
        print(f"Updating row {i} for {employee_name}, {month}")
        client._ensure_monthly_summary_row(employee_name, month)
        updated_count += 1
    
    print(f"Updated {updated_count} rows with new formulas")
    print("Done!")

if __name__ == "__main__":
    main()

