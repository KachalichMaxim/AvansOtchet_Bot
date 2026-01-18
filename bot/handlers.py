"""Telegram bot handlers."""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from datetime import datetime
from bot.fsm import FSM, State
from bot.rental_models import add_days_to_date
from bot.sheets_client import SheetsClient
from bot.utils import (
    validate_date,
    validate_amount,
    format_balance,
    get_current_month,
    parse_month,
    get_current_timestamp,
)
from bot.config import TIMEZONE
from pytz import timezone

TZ = timezone(TIMEZONE)

# Global instances
fsm = FSM()
sheets_client = SheetsClient()


def get_employee_name(user_id: int) -> str:
    """Get employee name for user from Users sheet."""
    user_info = sheets_client.get_user_by_id(user_id)
    if user_info:
        return user_info.get("employee_name", f"User_{user_id}")
    return f"User_{user_id}"


def get_sheet_name(user_id: int) -> str:
    """Get sheet name for user from Users sheet."""
    user_info = sheets_client.get_user_by_id(user_id)
    if user_info:
        return user_info.get("sheet_name", f"User_{user_id}")
    return f"User_{user_id}"


def is_user_registered(user_id: int) -> bool:
    """Check if user is registered in Users sheet."""
    user_info = sheets_client.get_user_by_id(user_id)
    return user_info is not None and user_info.get("active", True)


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    user_id = update.effective_user.id
    
    # Check if user is already registered
    if is_user_registered(user_id):
        await show_main_menu(update, context)
        return
    
    # Request employee name
    await update.message.reply_text(
        "Добро пожаловать! 👋\n\n"
        "Для начала работы укажите ваше имя (ФИО или короткое имя):"
    )
    # Store that we're waiting for name
    fsm.set_state(user_id, State.SELECT_OPERATION_TYPE)  # Temporary state
    context.user_data["waiting_for_name"] = True


async def handle_name_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle employee name input."""
    user_id = update.effective_user.id
    name = update.message.text.strip()
    
    if not name or len(name) < 2:
        await update.message.reply_text(
            "Имя слишком короткое. Пожалуйста, введите ваше имя:"
        )
        return
    
    # Create or get employee sheet
    if sheets_client.get_or_create_employee_sheet(name):
        # Register user in Users sheet
        sheets_client.register_user(user_id, name, name)
        fsm.reset(user_id)
        await update.message.reply_text(
            f"Отлично, {name}! Ваш лист готов.\n\n"
            "Теперь вы можете начать работу."
        )
        await show_main_menu(update, context)
    else:
        await update.message.reply_text(
            "Ошибка при создании листа. Попробуйте еще раз или обратитесь к администратору."
        )


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show main menu with balance and options."""
    user_id = update.effective_user.id
    
    if not is_user_registered(user_id):
        # If called from callback query, send a message instead
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.message.reply_text(
                "Добро пожаловать! 👋\n\n"
                "Для начала работы укажите ваше имя (ФИО или короткое имя):"
            )
            context.user_data["waiting_for_name"] = True
            fsm.set_state(user_id, State.SELECT_OPERATION_TYPE)  # Temporary state
        else:
            await start_handler(update, context)
        return
    
    employee_name = get_employee_name(user_id)
    balance = sheets_client.get_balance(employee_name)
    
    balance_text = format_balance(balance) if balance is not None else "0 ₽"
    
    keyboard = [
        [InlineKeyboardButton("➕ Добавить операцию", callback_data="add_operation")],
        [InlineKeyboardButton("📊 Итоги за месяц", callback_data="monthly_summary")],
        [InlineKeyboardButton("💰 Текущий остаток", callback_data="show_balance")],
    ]
    
    # Add rental button if employee has rental objects
    if sheets_client.has_rental_objects(employee_name):
        keyboard.append([InlineKeyboardButton("🏠 Аренда", callback_data="rental_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        f"📋 Главное меню\n\n"
        f"Сотрудник: {employee_name}\n"
        f"Текущий остаток: {balance_text}\n\n"
        f"Выберите действие:"
    )
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline button callbacks."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    if data == "add_operation":
        fsm.start_operation(user_id)
        await show_operation_type_selection(query, context)
    elif data == "monthly_summary":
        await show_monthly_summary_menu(query, context)
    elif data == "show_balance":
        await show_balance(query, context)
    elif data == "cancel":
        await cancel_operation(query, context)
    elif data.startswith("op_type_"):
        direction = data.split("_")[-1]
        fsm.set_direction(user_id, direction)
        await show_date_selection(query, context)
    elif data == "date_today":
        today = datetime.now(TZ).strftime("%d.%m.%Y")
        fsm.set_date(user_id, today)
        await request_amount(query, context)
    elif data == "date_manual":
        await request_manual_date(query, context)
    elif data.startswith("category_"):
        category = data.replace("category_", "").replace("_", " ")
        fsm.set_category(user_id, category)
        # If category is "Доходы от аренды", show address selection instead of type
        if category == "Доходы от аренды":
            await show_rental_addresses(query, context)
        else:
            await show_type_selection(query, context)
    elif data.startswith("type_"):
        type_name = data.replace("type_", "").replace("_", " ")
        # Handle empty type
        if type_name == "EMPTY":
            type_name = ""
        fsm.set_type(user_id, type_name)
        await request_description(query, context)
    elif data == "skip_description":
        fsm.skip_description(user_id)
        await show_confirmation(query, context)
    elif data == "confirm_operation":
        await save_operation(query, context)
    elif data == "confirm_rental_amount":
        # Confirm rental amount and go to operation confirmation
        user_id = query.from_user.id
        context_obj = fsm.get_context(user_id)
        if context_obj.amount is not None:
            fsm.set_state(user_id, State.CONFIRM)
            await show_confirmation(query, context)
        else:
            await query.answer("Ошибка: сумма не установлена")
    elif data.startswith("month_"):
        month = data.replace("month_", "")
        await show_monthly_summary_result(query, context, month)
    elif data == "back_to_menu":
        await show_main_menu(update, context)
    elif data == "go_back":
        await handle_go_back(query, context)
    elif data == "rental_menu":
        await show_rental_objects(query, context)
    elif data == "rental_add_payment":
        await show_rental_addresses(query, context)
    elif data.startswith("rental_address_"):
        address = data.replace("rental_address_", "").replace("_", " ")
        fsm.set_rental_address(user_id, address)
        await show_rental_mm(query, context, address)
    elif data.startswith("rental_mm_"):
        mm_data = data.replace("rental_mm_", "")
        # Format: address_mm_number (need to decode)
        parts = mm_data.rsplit("_", 1)
        if len(parts) == 2:
            address = parts[0].replace("_", " ")
            mm_number = parts[1]
            fsm.set_rental_mm(user_id, mm_number)
            context_obj = fsm.get_context(user_id)
            # Check if this is rental payment flow (no category set) or category flow
            if not context_obj.category:
                # Rental payment flow: set date to today, direction to IN, category and type
                today = datetime.now(TZ).strftime("%d.%m.%Y")
                fsm.set_date(user_id, today)
                fsm.set_direction(user_id, "IN")
                # Set category and type for rental payment
                fsm.set_category(user_id, "Доходы от аренды")
                # Get type for rental category - try to find "Перевод от арендатора" or use first available
                types = sheets_client.get_types("IN", "Доходы от аренды")
                if types and "Перевод от арендатора" in types:
                    fsm.set_type(user_id, "Перевод от арендатора")
                elif types:
                    fsm.set_type(user_id, types[0])
                else:
                    fsm.set_type(user_id, "")
                fsm.set_state(user_id, State.INPUT_RENTAL_AMOUNT)
                await request_rental_amount(query, context)
            else:
                # Category flow: continue to description
                await request_description(query, context)


async def show_operation_type_selection(query, context: ContextTypes.DEFAULT_TYPE):
    """Show operation type selection."""
    keyboard = [
        [InlineKeyboardButton("➕ Поступление", callback_data="op_type_IN")],
        [InlineKeyboardButton("➖ Списание", callback_data="op_type_OUT")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "Выберите тип операции:",
        reply_markup=reply_markup
    )


async def handle_go_back(query, context: ContextTypes.DEFAULT_TYPE):
    """Handle go back button."""
    user_id = query.from_user.id
    
    if fsm.go_back(user_id):
        # Show previous state
        new_state = fsm.get_state(user_id)
        if new_state == State.SELECT_OPERATION_TYPE:
            await show_operation_type_selection(query, context)
        elif new_state == State.SELECT_DATE:
            await show_date_selection(query, context)
        elif new_state == State.INPUT_AMOUNT:
            await request_amount(query, context)
        elif new_state == State.SELECT_CATEGORY:
            await show_category_selection(query, context)
        elif new_state == State.SELECT_TYPE:
            await show_type_selection(query, context)
        elif new_state == State.INPUT_DESCRIPTION:
            await request_description(query, context)
    else:
        # Already at first state, go to main menu
        await query.answer("Вы уже на первом шаге")
        await show_main_menu(query, context)


async def show_date_selection(query, context: ContextTypes.DEFAULT_TYPE):
    """Show date selection."""
    keyboard = [
        [InlineKeyboardButton("📅 Сегодня", callback_data="date_today")],
        [InlineKeyboardButton("✏️ Ввести дату", callback_data="date_manual")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="go_back")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "Укажите дату операции:",
        reply_markup=reply_markup
    )


async def request_manual_date(target, context: ContextTypes.DEFAULT_TYPE):
    """Request manual date input."""
    keyboard = [
        [InlineKeyboardButton("⬅️ Назад", callback_data="go_back")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = "Введите дату в формате dd.mm.yyyy (например, 02.01.2026):"
    if hasattr(target, 'edit_message_text'):
        await target.edit_message_text(text, reply_markup=reply_markup)
    else:
        await target.reply_text(text, reply_markup=reply_markup)


async def request_amount(target, context: ContextTypes.DEFAULT_TYPE):
    """Request amount input."""
    keyboard = [
        [InlineKeyboardButton("⬅️ Назад", callback_data="go_back")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = "Введите сумму (положительное число):"
    if hasattr(target, 'edit_message_text'):
        await target.edit_message_text(text, reply_markup=reply_markup)
    else:
        await target.reply_text(text, reply_markup=reply_markup)


async def show_category_selection(query, context: ContextTypes.DEFAULT_TYPE):
    """Show category selection."""
    user_id = query.from_user.id
    context_obj = fsm.get_context(user_id)
    direction = context_obj.direction
    
    categories = sheets_client.get_categories(direction)
    
    # Categories should always have at least "Прочее" now
    if not categories:
        categories = ["Прочее"]
    
    keyboard = []
    for category in categories:
        callback_data = f"category_{category.replace(' ', '_')}"
        keyboard.append([InlineKeyboardButton(category, callback_data=callback_data)])
    
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="go_back")])
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "Выберите категорию:",
        reply_markup=reply_markup
    )


async def show_type_selection(query, context: ContextTypes.DEFAULT_TYPE):
    """Show type selection."""
    user_id = query.from_user.id
    context_obj = fsm.get_context(user_id)
    direction = context_obj.direction
    category = context_obj.category
    
    types = sheets_client.get_types(direction, category)
    
    # Types should always have at least "Прочее" now
    if not types:
        types = ["Прочее"]
    
    keyboard = []
    for type_name in types:
        # Handle empty type - show as "—" or "Пусто"
        display_name = type_name if type_name else "—"
        callback_data = f"type_{type_name.replace(' ', '_') if type_name else 'EMPTY'}"
        keyboard.append([InlineKeyboardButton(display_name, callback_data=callback_data)])
    
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="go_back")])
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "Выберите тип:",
        reply_markup=reply_markup
    )


async def request_description(query, context: ContextTypes.DEFAULT_TYPE):
    """Request description input."""
    keyboard = [
        [InlineKeyboardButton("⏭ Пропустить", callback_data="skip_description")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="go_back")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "Добавить описание? (необязательно)\n\n"
        "Введите текст описания или нажмите 'Пропустить':",
        reply_markup=reply_markup
    )


async def show_confirmation(query, context: ContextTypes.DEFAULT_TYPE):
    """Show operation confirmation."""
    user_id = query.from_user.id
    context_obj = fsm.get_context(user_id)
    
    direction_text = "Поступление" if context_obj.direction == "IN" else "Списание"
    amount_text = format_balance(context_obj.amount)
    category_display = context_obj.category if context_obj.category else "—"
    type_display = context_obj.type if context_obj.type else "—"
    
    text = (
        f"📋 Подтверждение операции\n\n"
        f"Тип: {direction_text}\n"
        f"Дата: {context_obj.date}\n"
        f"Сумма: {amount_text}\n"
        f"Категория: {category_display}\n"
        f"Тип: {type_display}\n"
    )
    
    # Show rental info if present
    if context_obj.rental_address:
        text += f"Адрес: {context_obj.rental_address}\n"
    if context_obj.rental_mm:
        text += f"М/М: {context_obj.rental_mm}\n"
    
    if context_obj.description:
        text += f"Описание: {context_obj.description}\n"
    
    keyboard = [
        [InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_operation")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="go_back")],
        [InlineKeyboardButton("❌ Отменить", callback_data="cancel")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup)


async def save_operation(query, context: ContextTypes.DEFAULT_TYPE):
    """Save operation to sheets."""
    user_id = query.from_user.id
    employee_name = get_employee_name(user_id)
    
    operation_data = fsm.get_operation_data(user_id)
    if not operation_data:
        await query.edit_message_text(
            "Ошибка: неполные данные операции. Попробуйте еще раз."
        )
        fsm.reset(user_id)
        return
    
    # Check if this is a rental payment (has rental address and MM)
    context_obj = fsm.get_context(user_id)
    is_rental_payment = bool(context_obj.rental_address and context_obj.rental_mm)
    
    # If rental payment, update operation data to include category and type
    if context_obj.rental_address and context_obj.rental_mm:
        if not operation_data.get("category") or operation_data["category"] != "Доходы от аренды":
            operation_data["category"] = "Доходы от аренды"
        if not operation_data.get("type"):
            operation_data["type"] = f"{context_obj.rental_address} {context_obj.rental_mm}"
    
    # Save operation
    if sheets_client.add_operation(employee_name, operation_data):
        # If rental payment, update next payment date (+30 days) in Справочник М/М
        if is_rental_payment and context_obj.rental_address and context_obj.rental_mm:
            payment_date = context_obj.date
            success = sheets_client.update_rental_payment_date(
                context_obj.rental_address,
                context_obj.rental_mm,
                payment_date
            )
            if not success:
                print(f"Warning: Failed to update rental payment date for {context_obj.rental_address}, М/М {context_obj.rental_mm}")
        
        # Get new balance
        balance = sheets_client.get_balance(employee_name)
        balance_text = format_balance(balance) if balance is not None else "0 ₽"
        
        fsm.reset(user_id)
        
        # Show success message and main menu
        await query.answer("✅ Операция сохранена!")
        
        # Show main menu with success message
        user_id = query.from_user.id
        employee_name = get_employee_name(user_id)
        balance = sheets_client.get_balance(employee_name)
        balance_text = format_balance(balance) if balance is not None else "0 ₽"
        
        keyboard = [
            [InlineKeyboardButton("➕ Добавить операцию", callback_data="add_operation")],
            [InlineKeyboardButton("📊 Итоги за месяц", callback_data="monthly_summary")],
            [InlineKeyboardButton("💰 Текущий остаток", callback_data="show_balance")],
        ]
        
        # Add rental button if employee has rental objects
        if sheets_client.has_rental_objects(employee_name):
            keyboard.append([InlineKeyboardButton("🏠 Аренда", callback_data="rental_menu")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        success_text = "✅ Операция сохранена!"
        if is_rental_payment:
            from bot.rental_models import add_days_to_date
            new_date = add_days_to_date(context_obj.date, 30)
            success_text += f"\n\n📅 Следующий платеж: {new_date}"
        
        text = (
            f"{success_text}\n\n"
            f"📋 Главное меню\n\n"
            f"Сотрудник: {employee_name}\n"
            f"Текущий остаток: {balance_text}\n\n"
            f"Выберите действие:"
        )
        
        await query.edit_message_text(text, reply_markup=reply_markup)
    else:
        await query.edit_message_text(
            "❌ Ошибка при сохранении операции. Попробуйте еще раз или обратитесь к администратору."
        )


async def cancel_operation(query, context: ContextTypes.DEFAULT_TYPE):
    """Cancel current operation."""
    user_id = query.from_user.id
    fsm.reset(user_id)
    
    keyboard = [
        [InlineKeyboardButton("📋 Главное меню", callback_data="back_to_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "Операция отменена.",
        reply_markup=reply_markup
    )


async def show_balance(query, context: ContextTypes.DEFAULT_TYPE):
    """Show current balance."""
    user_id = query.from_user.id
    employee_name = get_employee_name(user_id)
    balance = sheets_client.get_balance(employee_name)
    balance_text = format_balance(balance) if balance is not None else "0 ₽"
    
    keyboard = [
        [InlineKeyboardButton("📋 Главное меню", callback_data="back_to_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"💰 Текущий остаток: {balance_text}",
        reply_markup=reply_markup
    )


async def show_monthly_summary_menu(query, context: ContextTypes.DEFAULT_TYPE):
    """Show monthly summary month selection."""
    user_id = query.from_user.id
    employee_name = get_employee_name(user_id)
    
    # Get months with operations
    months = sheets_client.get_months_with_operations(employee_name)
    
    if not months:
        keyboard = [
            [InlineKeyboardButton("📋 Главное меню", callback_data="back_to_menu")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "У вас нет операций за какой-либо период.",
            reply_markup=reply_markup
        )
        return
    
    # Month names in Russian
    month_names = {
        1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель", 5: "Май", 6: "Июнь",
        7: "Июль", 8: "Август", 9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь"
    }
    
    keyboard = []
    for month_str in months:
        month_num, year = map(int, month_str.split('.'))
        month_label = f"{month_names[month_num]} {year}"
        keyboard.append([
            InlineKeyboardButton(month_label, callback_data=f"month_{month_str}")
        ])
    
    keyboard.append([InlineKeyboardButton("📋 Главное меню", callback_data="back_to_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "Выберите месяц для просмотра итогов:",
        reply_markup=reply_markup
    )


async def show_monthly_summary_result(query, context: ContextTypes.DEFAULT_TYPE, month: str):
    """Show monthly summary result."""
    user_id = query.from_user.id
    employee_name = get_employee_name(user_id)
    
    summary = sheets_client.get_monthly_summary(employee_name, month)
    
    if summary is None:
        await query.edit_message_text(
            "Ошибка при получении данных. Попробуйте еще раз."
        )
        return
    
    income_text = format_balance(summary["income"])
    expense_text = format_balance(summary["expense"])
    ending_balance_text = format_balance(summary["ending_balance"])
    
    text = (
        f"📊 Итоги за {month}\n\n"
        f"Поступления: {income_text}\n"
        f"Списания: {expense_text}\n"
        f"Остаток на конец месяца: {ending_balance_text}"
    )
    
    keyboard = [
        [InlineKeyboardButton("📋 Главное меню", callback_data="back_to_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup)


async def show_rental_objects(query, context: ContextTypes.DEFAULT_TYPE):
    """Show rental objects with upcoming payments."""
    user_id = query.from_user.id
    employee_name = get_employee_name(user_id)
    
    objects = sheets_client.get_rental_objects_for_employee(employee_name)
    
    if not objects:
        keyboard = [
            [InlineKeyboardButton("📋 Главное меню", callback_data="back_to_menu")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "У вас нет объектов аренды с предстоящими платежами.",
            reply_markup=reply_markup
        )
        return
    
    # Format table: Объект | Дата | Сумма (with code formatting for monospace)
    header = "🏠 Объекты аренды\n\n"
    
    # Build table with fixed-width columns for proper alignment
    table_lines = []
    table_lines.append("Объект         | Дата      | Сумма")
    table_lines.append("─" * 40)
    
    for obj in objects:
        date_display = obj.next_payment_date if obj.next_payment_date else "—"
        amount_display = format_balance(obj.payment_amount) if obj.payment_amount else "—"
        # Format object as "Адрес(5 букв) М/М номер" (e.g., "Кетче 180")
        address_short = obj.address[:5] if obj.address else ""
        object_name = f"{address_short} {obj.mm_number}" if address_short and obj.mm_number else (address_short or obj.mm_number or "—")
        # Ensure consistent width
        object_name = object_name.ljust(15)
        date = date_display.ljust(10)
        amount = amount_display.ljust(12)
        table_lines.append(f"{object_name} | {date} | {amount}")
    
    # Combine header with code-formatted table
    table_text = "\n".join(table_lines)
    text = f"{header}```\n{table_text}\n```"
    
    keyboard = [
        [InlineKeyboardButton("➕ Добавить оплату", callback_data="rental_add_payment")],
        [InlineKeyboardButton("📋 Главное меню", callback_data="back_to_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")


async def show_rental_addresses(query, context: ContextTypes.DEFAULT_TYPE):
    """Show rental addresses for selection."""
    user_id = query.from_user.id
    employee_name = get_employee_name(user_id)
    
    # Get addresses - if category is "Доходы от аренды", show only unpaid
    context_obj = fsm.get_context(user_id)
    if context_obj.category == "Доходы от аренды":
        mm_list = sheets_client.get_rental_mm_without_payments(employee_name)
        addresses = sorted(list(set([mm['address'] for mm in mm_list])))
    else:
        addresses = sheets_client.get_rental_addresses_for_employee(employee_name)
    
    if not addresses:
        keyboard = [
            [InlineKeyboardButton("⬅️ Назад", callback_data="go_back")],
            [InlineKeyboardButton("📋 Главное меню", callback_data="back_to_menu")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "Нет доступных адресов для выбора.",
            reply_markup=reply_markup
        )
        return
    
    keyboard = []
    for address in addresses:
        callback_data = f"rental_address_{address.replace(' ', '_')}"
        keyboard.append([InlineKeyboardButton(address, callback_data=callback_data)])
    
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="go_back")])
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "Выберите адрес:",
        reply_markup=reply_markup
    )


async def show_rental_mm(query, context: ContextTypes.DEFAULT_TYPE, address: str):
    """Show М/М numbers for selected address."""
    user_id = query.from_user.id
    employee_name = get_employee_name(user_id)
    context_obj = fsm.get_context(user_id)
    
    # Get М/М - if category is "Доходы от аренды", show only unpaid
    if context_obj.category == "Доходы от аренды":
        mm_list = sheets_client.get_rental_mm_without_payments(employee_name)
        mm_numbers = [mm['mm_number'] for mm in mm_list if mm['address'] == address]
    else:
        mm_numbers = sheets_client.get_rental_mm_for_address(employee_name, address)
    
    if not mm_numbers:
        keyboard = [
            [InlineKeyboardButton("⬅️ Назад", callback_data="go_back")],
            [InlineKeyboardButton("❌ Отмена", callback_data="cancel")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"Нет доступных М/М для адреса {address}.",
            reply_markup=reply_markup
        )
        return
    
    keyboard = []
    for mm_number in mm_numbers:
        # Encode address and mm in callback data
        callback_data = f"rental_mm_{address.replace(' ', '_')}_{mm_number}"
        keyboard.append([InlineKeyboardButton(f"М/М {mm_number}", callback_data=callback_data)])
    
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="go_back")])
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"Выберите М/М для адреса {address}:",
        reply_markup=reply_markup
    )


async def show_rental_mm_for_text(message, context: ContextTypes.DEFAULT_TYPE, address: str):
    """Show М/М selection as message (for text flow)."""
    user_id = message.from_user.id
    employee_name = get_employee_name(user_id)
    context_obj = fsm.get_context(user_id)
    
    if context_obj.category == "Доходы от аренды":
        mm_list = sheets_client.get_rental_mm_without_payments(employee_name)
        mm_numbers = [mm['mm_number'] for mm in mm_list if mm['address'] == address]
    else:
        mm_numbers = sheets_client.get_rental_mm_for_address(employee_name, address)
    
    keyboard = []
    for mm_number in mm_numbers:
        callback_data = f"rental_mm_{address.replace(' ', '_')}_{mm_number}"
        keyboard.append([InlineKeyboardButton(f"М/М {mm_number}", callback_data=callback_data)])
    
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="go_back")])
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await message.reply_text(
        f"Выберите М/М для адреса {address}:",
        reply_markup=reply_markup
    )


async def request_rental_amount(query, context: ContextTypes.DEFAULT_TYPE):
    """Request rental payment amount."""
    keyboard = [
        [InlineKeyboardButton("⬅️ Назад", callback_data="go_back")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    context_obj = fsm.get_context(query.from_user.id)
    # Get payment amount from Справочник М/М
    payment_amount = sheets_client.get_rental_payment_amount(
        context_obj.rental_address,
        context_obj.rental_mm
    )
    
    amount_display = format_balance(payment_amount) if payment_amount else "—"
    
    # If amount found, set it automatically in context and show it
    # But don't change state here - it should be already set to INPUT_RENTAL_AMOUNT
    if payment_amount:
        context_obj.amount = payment_amount
    
    text = (
        f"💰 Сумма оплаты:\n"
        f"Адрес {context_obj.rental_address}\n"
        f"М/М {context_obj.rental_mm}\n"
        f"Сумма : {amount_display}"
    )
    
    # If amount is set, allow user to confirm directly
    if payment_amount:
        keyboard = [
            [InlineKeyboardButton("✅ Подтвердить сумму", callback_data="confirm_rental_amount")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="go_back")],
            [InlineKeyboardButton("❌ Отмена", callback_data="cancel")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        text += "\n\nСумма автоматически подставлена из справочника. Нажмите 'Подтвердить сумму' или введите другую сумму."
    else:
        keyboard = [
            [InlineKeyboardButton("⬅️ Назад", callback_data="go_back")],
            [InlineKeyboardButton("❌ Отмена", callback_data="cancel")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup)


async def request_rental_amount_for_text(message, context: ContextTypes.DEFAULT_TYPE):
    """Request rental payment amount as message."""
    keyboard = [
        [InlineKeyboardButton("⬅️ Назад", callback_data="go_back")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    user_id = message.from_user.id
    context_obj = fsm.get_context(user_id)
    
    # Get payment amount from Справочник М/М
    payment_amount = sheets_client.get_rental_payment_amount(
        context_obj.rental_address,
        context_obj.rental_mm
    )
    
    amount_display = format_balance(payment_amount) if payment_amount else "—"
    
    # If amount found, set it automatically in context
    if payment_amount:
        context_obj.amount = payment_amount
    
    text = (
        f"💰 Сумма оплаты:\n"
        f"Адрес {context_obj.rental_address}\n"
        f"М/М {context_obj.rental_mm}\n"
        f"Сумма : {amount_display}"
    )
    await message.reply_text(text, reply_markup=reply_markup)


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages."""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    state = fsm.get_state(user_id)
    
    # Check if waiting for name
    if context.user_data.get("waiting_for_name"):
        context.user_data["waiting_for_name"] = False
        await handle_name_input(update, context)
        return
    
    # Handle cancel command
    if text.lower() in ["/cancel", "отмена", "cancel"]:
        if fsm.can_cancel(user_id):
            fsm.reset(user_id)
            await update.message.reply_text("Операция отменена. Используйте /menu для возврата в главное меню.")
        return
    
    # Handle menu command
    if text.lower() in ["/menu", "меню", "menu"]:
        await show_main_menu(update, context)
        return
    
    # Handle FSM states
    if state == State.SELECT_DATE:
        # Manual date input
        is_valid, error = validate_date(text)
        if is_valid:
            fsm.set_date(user_id, text)
            # Move to amount input state
            fsm.set_state(user_id, State.INPUT_AMOUNT)
            await request_amount(update.message, context)
        else:
            await update.message.reply_text(error + "\n\nПопробуйте еще раз.")
    
    elif state == State.INPUT_AMOUNT:
        is_valid, amount, error = validate_amount(text)
        if is_valid:
            fsm.set_amount(user_id, amount)
            await show_category_selection_for_text(update.message, context)
        else:
            await update.message.reply_text(error + "\n\nПопробуйте еще раз.")
    
    elif state == State.INPUT_DESCRIPTION:
        fsm.set_description(user_id, text)
        await show_confirmation_for_text(update.message, context)
    elif state == State.INPUT_RENTAL_AMOUNT:
        # If amount is already set from справочник, skip validation
        context_obj = fsm.get_context(user_id)
        if context_obj.amount is not None:
            # Amount already set, proceed to confirmation
            fsm.set_state(user_id, State.CONFIRM)
            await show_confirmation_for_text(update.message, context)
        else:
            # User entered amount manually, validate it
            is_valid, amount, error = validate_amount(text)
            if is_valid:
                fsm.set_rental_amount(user_id, amount)
                await show_confirmation_for_text(update.message, context)
            else:
                await update.message.reply_text(error + "\n\nПопробуйте еще раз.")
    
    else:
        await update.message.reply_text(
            "Неизвестная команда. Используйте /menu для главного меню."
        )


async def show_category_selection_for_text(message, context: ContextTypes.DEFAULT_TYPE):
    """Show category selection as message (for text flow)."""
    user_id = message.from_user.id
    context_obj = fsm.get_context(user_id)
    direction = context_obj.direction
    
    categories = sheets_client.get_categories(direction)
    
    if not categories:
        await message.reply_text(
            "Ошибка: не найдены категории для данного типа операции.\n"
            "Обратитесь к администратору."
        )
        fsm.reset(user_id)
        return
    
    # For text flow, we'll use inline keyboard anyway for better UX
    keyboard = []
    for category in categories:
        callback_data = f"category_{category.replace(' ', '_')}"
        keyboard.append([InlineKeyboardButton(category, callback_data=callback_data)])
    
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await message.reply_text(
        "Выберите категорию:",
        reply_markup=reply_markup
    )


async def show_confirmation_for_text(message, context: ContextTypes.DEFAULT_TYPE):
    """Show confirmation as message."""
    user_id = message.from_user.id
    context_obj = fsm.get_context(user_id)
    
    direction_text = "Поступление" if context_obj.direction == "IN" else "Списание"
    amount_text = format_balance(context_obj.amount)
    
    text = (
        f"📋 Подтверждение операции\n\n"
        f"Тип: {direction_text}\n"
        f"Дата: {context_obj.date}\n"
        f"Сумма: {amount_text}\n"
        f"Категория: {context_obj.category}\n"
        f"Тип: {context_obj.type}\n"
    )
    
    if context_obj.description:
        text += f"Описание: {context_obj.description}\n"
    
    keyboard = [
        [InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_operation")],
        [InlineKeyboardButton("❌ Отменить", callback_data="cancel")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await message.reply_text(text, reply_markup=reply_markup)

