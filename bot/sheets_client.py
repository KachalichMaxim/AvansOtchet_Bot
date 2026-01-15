"""Google Sheets API client for managing employee advance reports."""
import gspread
from google.oauth2.service_account import Credentials
from typing import Optional, Dict, List, Any
from bot.config import (
    GOOGLE_SHEETS_ID,
    GOOGLE_CREDENTIALS_PATH,
    SHEET_REFERENCE,
    SHEET_TEMPLATE,
    SHEET_AUDIT_LOG,
    SHEET_MONTHLY_SUMMARY,
    SHEET_USERS,
)
from bot.utils import get_current_timestamp


class SheetsClient:
    """Client for interacting with Google Sheets."""
    
    def __init__(self):
        """Initialize Google Sheets client with service account credentials."""
        scope = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_file(GOOGLE_CREDENTIALS_PATH, scopes=scope)
        self.client = gspread.authorize(creds)
        self.spreadsheet = self.client.open_by_key(GOOGLE_SHEETS_ID)
        self._sheet_cache = {}
    
    def _get_sheet(self, sheet_name: str):
        """Get sheet by name with caching."""
        if sheet_name not in self._sheet_cache:
            try:
                self._sheet_cache[sheet_name] = self.spreadsheet.worksheet(sheet_name)
            except gspread.exceptions.WorksheetNotFound:
                return None
        return self._sheet_cache[sheet_name]
    
    def get_or_create_employee_sheet(self, employee_name: str) -> bool:
        """
        Get existing employee sheet or create from template.
        
        Returns:
            True if sheet exists or was created, False on error
        """
        # Check if sheet already exists
        try:
            sheet = self.spreadsheet.worksheet(employee_name)
            return True
        except gspread.exceptions.WorksheetNotFound:
            pass
        
        # Create from template
        try:
            template = self._get_sheet(SHEET_TEMPLATE)
            if not template:
                return False
            
            # Copy template
            new_sheet = self.spreadsheet.duplicate_sheet(
                template.id,
                new_sheet_name=employee_name
            )
            self._sheet_cache[employee_name] = new_sheet
            
            # Log creation
            self.log_audit({
                "user": employee_name,
                "sheet": employee_name,
                "action": "CREATE_SHEET",
                "field": None,
                "old_value": None,
                "new_value": employee_name,
            })
            
            return True
        except Exception as e:
            print(f"Error creating sheet for {employee_name}: {e}")
            return False
    
    def get_reference_data(self) -> List[Dict[str, Any]]:
        """Read Справочник sheet and return all reference data."""
        sheet = self._get_sheet(SHEET_REFERENCE)
        if not sheet:
            return []
        
        try:
            # Get all values (skip header row)
            values = sheet.get_all_values()[1:]  # Skip header
            
            result = []
            for row in values:
                if len(row) >= 4 and row[0]:  # Ensure row has required columns
                    result.append({
                        "direction": row[0].strip(),
                        "category": row[1].strip() if len(row) > 1 else "",
                        "type": row[2].strip() if len(row) > 2 else "",
                        "active": row[3].strip().upper() == "TRUE" if len(row) > 3 else True,
                    })
            return result
        except Exception as e:
            print(f"Error reading reference data: {e}")
            return []
    
    def get_categories(self, direction: str) -> List[str]:
        """Get unique categories filtered by direction."""
        reference_data = self.get_reference_data()
        categories = set()
        
        for item in reference_data:
            if item["direction"] == direction and item["active"] and item["category"]:
                categories.add(item["category"])
        
        # Always add "Прочее" as fallback option
        categories.add("Прочее")
        
        return sorted(list(categories))
    
    def get_types(self, direction: str, category: str) -> List[str]:
        """Get types filtered by direction and category."""
        reference_data = self.get_reference_data()
        types = []
        has_empty_type = False
        
        for item in reference_data:
            if (item["direction"] == direction and 
                item["category"] == category and 
                item["active"]):
                if item["type"]:
                    types.append(item["type"])
                else:
                    # Track if there's an entry with empty type
                    has_empty_type = True
        
        # If we have entries with empty type, add empty string option
        if has_empty_type:
            types.append("")  # Empty type option
        
        # If no types found at all, add "Прочее" as fallback
        if not types and not has_empty_type:
            types = ["Прочее"]
        
        return types
    
    def add_operation(
        self,
        employee_name: str,
        operation_data: Dict[str, Any]
    ) -> bool:
        """
        Append operation to employee sheet.
        
        operation_data should contain:
        - date: str (dd.mm.yyyy)
        - direction: str ("IN" or "OUT")
        - amount: float
        - category: str
        - type: str
        - description: str (optional)
        """
        sheet = self._get_sheet(employee_name)
        if not sheet:
            if not self.get_or_create_employee_sheet(employee_name):
                return False
            sheet = self._get_sheet(employee_name)
        
        try:
            # Prepare row data
            date = operation_data["date"]
            direction = operation_data["direction"]
            amount = operation_data["amount"]
            category = operation_data["category"]
            type_name = operation_data["type"]
            description = operation_data.get("description", "")
            
            # Determine which column gets the amount
            if direction == "IN":
                row_data = [date, amount, "", category, type_name, description]
            else:  # OUT
                row_data = [date, "", amount, category, type_name, description]
            
            # Parse the operation date for sorting
            day, month, year = map(int, date.split('.'))
            op_date = (year, month, day)
            
            # Get all existing operations to find insertion point
            all_values = sheet.get_all_values()
            
            # Find the correct row to insert (chronological order)
            insert_row = 2  # Start after header
            if len(all_values) > 1:  # Has data rows
                for i, row in enumerate(all_values[1:], start=2):  # Skip header
                    if len(row) >= 1 and row[0]:  # Has date
                        try:
                            row_day, row_month, row_year = map(int, row[0].split('.'))
                            row_date = (row_year, row_month, row_day)
                            if op_date >= row_date:
                                insert_row = i + 1  # Insert after this row
                            else:
                                break  # Found insertion point
                        except (ValueError, IndexError):
                            # Invalid date, skip
                            continue
            
            # Insert row at the correct position
            sheet.insert_row(row_data, insert_row)
            
            # Recalculate all balance formulas to maintain correct running balance
            self._recalculate_balance_formulas(sheet)
            
            # Log audit
            self.log_audit({
                "user": employee_name,
                "sheet": employee_name,
                "action": "ADD_OPERATION",
                "field": "operation",
                "old_value": None,
                "new_value": f"{direction} {amount} {category}/{type_name}",
            })
            
            # Update monthly summary
            self._update_monthly_summary(employee_name, operation_data)
            
            return True
        except Exception as e:
            print(f"Error adding operation: {e}")
            return False
    
    def get_balance(self, employee_name: str) -> Optional[float]:
        """
        Calculate current balance from employee sheet.
        Operations are sorted by date to handle out-of-order additions.
        """
        sheet = self._get_sheet(employee_name)
        if not sheet:
            return None
        
        try:
            # Get all values
            all_values = sheet.get_all_values()
            if len(all_values) <= 1:  # Only header or empty
                return 0.0
            
            # Parse and sort operations by date
            operations = []
            for i, row in enumerate(all_values[1:], start=2):  # Skip header, start from row 2
                if len(row) >= 1 and row[0]:  # Has date
                    try:
                        # Parse date (dd.mm.yyyy)
                        date_str = row[0].strip()
                        if date_str and date_str != "":
                            day, month, year = map(int, date_str.split('.'))
                            date_tuple = (year, month, day)  # For sorting
                            
                            # Column B is income (index 1), Column C is expense (index 2)
                            income_str = row[1].strip() if len(row) > 1 and row[1] else ""
                            expense_str = row[2].strip() if len(row) > 2 and row[2] else ""
                            
                            # Convert to float, handle empty strings, commas, and non-breaking spaces
                            income = 0.0
                            if income_str:
                                # Remove all spaces (including non-breaking spaces \xa0), replace comma with dot
                                income_str = income_str.replace("\xa0", "").replace(" ", "").replace(",", ".")
                                try:
                                    income = float(income_str)
                                except ValueError:
                                    print(f"Could not parse income: '{income_str}'")
                                    income = 0.0
                            
                            expense = 0.0
                            if expense_str:
                                # Remove all spaces (including non-breaking spaces \xa0), replace comma with dot
                                expense_str = expense_str.replace("\xa0", "").replace(" ", "").replace(",", ".")
                                try:
                                    expense = float(expense_str)
                                except ValueError:
                                    print(f"Could not parse expense: '{expense_str}'")
                                    expense = 0.0
                            
                            operations.append({
                                'date': date_tuple,
                                'date_str': date_str,
                                'income': income,
                                'expense': expense,
                                'row_num': i
                            })
                    except (ValueError, IndexError) as e:
                        print(f"Error parsing row {i}: {row}, error: {e}")
                        continue
            
            # Sort by date (chronological order)
            operations.sort(key=lambda x: x['date'])
            
            # Calculate balance chronologically
            balance = 0.0
            for op in operations:
                balance += op['income'] - op['expense']
            
            return balance
        except Exception as e:
            print(f"Error getting balance: {e}")
            return None
    
    def get_monthly_summary(
        self,
        employee_name: str,
        month: str  # MM.YYYY format
    ) -> Optional[Dict[str, float]]:
        """Get monthly totals for an employee."""
        sheet = self._get_sheet(employee_name)
        if not sheet:
            return None
        
        try:
            # Parse month
            month_num, year = map(int, month.split('.'))
            
            # Get all operations
            all_values = sheet.get_all_values()
            if len(all_values) <= 1:
                return {"income": 0.0, "expense": 0.0, "net": 0.0}
            
            income = 0.0
            expense = 0.0
            
            for row in all_values[1:]:  # Skip header
                if len(row) >= 3 and row[0]:  # Has date
                    try:
                        # Parse date
                        day, row_month, row_year = map(int, row[0].split('.'))
                        
                        # Check if matches requested month
                        if row_month == month_num and row_year == year:
                            if row[1]:  # Income
                                income += float(row[1])
                            if row[2]:  # Expense
                                expense += float(row[2])
                    except (ValueError, IndexError):
                        continue
            
            return {
                "income": income,
                "expense": expense,
                "net": income - expense,
            }
        except Exception as e:
            print(f"Error getting monthly summary: {e}")
            return None
    
    def _update_monthly_summary(
        self,
        employee_name: str,
        operation_data: Dict[str, Any]
    ):
        """Update monthly summary sheet with new operation."""
        try:
            summary_sheet = self._get_sheet(SHEET_MONTHLY_SUMMARY)
            if not summary_sheet:
                return
            
            # Parse date to get month
            date_str = operation_data["date"]
            day, month, year = map(int, date_str.split('.'))
            month_str = f"{month:02d}.{year}"
            
            direction = operation_data["direction"]
            amount = operation_data["amount"]
            
            # Check if row exists for this employee and month
            all_values = summary_sheet.get_all_values()
            row_index = None
            
            for i, row in enumerate(all_values[1:], start=2):  # Skip header
                if len(row) >= 2 and row[0] == employee_name and row[1] == month_str:
                    row_index = i
                    break
            
            if row_index:
                # Update existing row
                current_income = float(summary_sheet.cell(row_index, 3).value or 0)
                current_expense = float(summary_sheet.cell(row_index, 4).value or 0)
                
                if direction == "IN":
                    new_income = current_income + amount
                    summary_sheet.update_cell(row_index, 3, new_income)
                else:
                    new_expense = current_expense + amount
                    summary_sheet.update_cell(row_index, 4, new_expense)
                
                # Update net
                net = new_income - new_expense if direction == "IN" else current_income - new_expense
                summary_sheet.update_cell(row_index, 5, net)
            else:
                # Create new row
                income = amount if direction == "IN" else 0.0
                expense = amount if direction == "OUT" else 0.0
                net = income - expense
                
                summary_sheet.append_row([
                    employee_name,
                    month_str,
                    income,
                    expense,
                    net,
                ])
        except Exception as e:
            print(f"Error updating monthly summary: {e}")
    
    def log_audit(self, action_data: Dict[str, Any]):
        """Write to Audit_Log sheet."""
        try:
            audit_sheet = self._get_sheet(SHEET_AUDIT_LOG)
            if not audit_sheet:
                return
            
            timestamp = get_current_timestamp()
            row_data = [
                timestamp,
                action_data.get("user", ""),
                action_data.get("sheet", ""),
                action_data.get("action", ""),
                action_data.get("field", ""),
                str(action_data.get("old_value", "")),
                str(action_data.get("new_value", "")),
            ]
            
            audit_sheet.append_row(row_data)
        except Exception as e:
            print(f"Error logging audit: {e}")
    
    def _recalculate_balance_formulas(self, sheet):
        """Recalculate all balance formulas in the sheet after insertion."""
        try:
            all_values = sheet.get_all_values()
            if len(all_values) <= 1:
                return
            
            # Update formulas for all data rows (starting from row 2)
            for row_num in range(2, len(all_values) + 1):
                formula = f'=IF(ROW()={row_num}; IF(B{row_num}<>""; B{row_num}; -C{row_num}); INDIRECT("G"&ROW()-1) + IF(B{row_num}<>""; B{row_num}; 0) - IF(C{row_num}<>""; C{row_num}; 0))'
                sheet.update(f"G{row_num}", [[formula]], value_input_option="USER_ENTERED")
        except Exception as e:
            print(f"Error recalculating balance formulas: {e}")
    
    def create_sheet_from_template(self, template_name: str, new_name: str) -> bool:
        """Copy template sheet with new name."""
        try:
            template = self._get_sheet(template_name)
            if not template:
                return False
            
            new_sheet = self.spreadsheet.duplicate_sheet(
                template.id,
                new_sheet_name=new_name
            )
            self._sheet_cache[new_name] = new_sheet
            return True
        except Exception as e:
            print(f"Error creating sheet from template: {e}")
            return False
    
    def get_or_create_users_sheet(self):
        """Get or create Users sheet."""
        try:
            sheet = self._get_sheet(SHEET_USERS)
            if sheet:
                return True
        except Exception:
            pass
        
        try:
            users_sheet = self.spreadsheet.add_worksheet(
                title=SHEET_USERS, rows=100, cols=10
            )
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
            self._sheet_cache[SHEET_USERS] = users_sheet
            return True
        except Exception as e:
            print(f"Error creating Users sheet: {e}")
            return False
    
    def register_user(self, user_id: int, employee_name: str, sheet_name: str) -> bool:
        """Register user in Users sheet."""
        if not self.get_or_create_users_sheet():
            return False
        
        sheet = self._get_sheet(SHEET_USERS)
        if not sheet:
            return False
        
        try:
            # Check if user already exists
            all_values = sheet.get_all_values()
            for i, row in enumerate(all_values[1:], start=2):
                if len(row) > 0 and str(row[0]) == str(user_id):
                    # Update existing user
                    sheet.update_cell(i, 2, employee_name)
                    sheet.update_cell(i, 3, sheet_name)
                    sheet.update_cell(i, 5, "TRUE")
                    return True
            
            # Add new user
            from bot.utils import get_current_timestamp
            timestamp = get_current_timestamp()
            sheet.append_row([
                str(user_id),
                employee_name,
                sheet_name,
                timestamp,
                "TRUE"
            ])
            return True
        except Exception as e:
            print(f"Error registering user: {e}")
            return False
    
    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user info by Telegram user ID."""
        if not self.get_or_create_users_sheet():
            return None
        
        sheet = self._get_sheet(SHEET_USERS)
        if not sheet:
            return None
        
        try:
            all_values = sheet.get_all_values()
            for row in all_values[1:]:  # Skip header
                if len(row) > 0 and str(row[0]) == str(user_id):
                    return {
                        "user_id": str(row[0]),
                        "employee_name": row[1] if len(row) > 1 else "",
                        "sheet_name": row[2] if len(row) > 2 else "",
                        "registration_date": row[3] if len(row) > 3 else "",
                        "active": row[4].upper() == "TRUE" if len(row) > 4 else True,
                    }
            return None
        except Exception as e:
            print(f"Error getting user: {e}")
            return None

