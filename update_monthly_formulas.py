"""Script to update all existing rows in Итоги_месяца with formulas."""
from bot.sheets_client import SheetsClient

def main():
    print("Updating all monthly summary rows with formulas...")
    client = SheetsClient()
    client.update_all_monthly_summary_formulas()
    print("Done!")

if __name__ == "__main__":
    main()

