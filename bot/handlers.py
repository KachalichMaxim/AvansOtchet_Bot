"""Telegram bot handlers."""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from datetime import datetime
from bot.fsm import FSM, State
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
    elif data.startswith("month_"):
        month = data.replace("month_", "")
        await show_monthly_summary_result(query, context, month)
    elif data == "back_to_menu":
        await show_main_menu(update, context)
    elif data == "go_back":
        await handle_go_back(query, context)


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
    type_display = context_obj.type if context_obj.type else "—"
    
    text = (
        f"📋 Подтверждение операции\n\n"
        f"Тип: {direction_text}\n"
        f"Дата: {context_obj.date}\n"
        f"Сумма: {amount_text}\n"
        f"Категория: {context_obj.category}\n"
        f"Тип: {type_display}\n"
    )
    
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
    
    # Save operation
    if sheets_client.add_operation(employee_name, operation_data):
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
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = (
            f"✅ Операция сохранена!\n\n"
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
    # Generate last 12 months
    keyboard = []
    current_month = get_current_month()
    month_num, year = map(int, current_month.split('.'))
    
    for i in range(12):
        m = month_num - i
        y = year
        while m <= 0:
            m += 12
            y -= 1
        
        month_str = f"{m:02d}.{y}"
        month_label = f"{m:02d}.{y}"
        if i == 0:
            month_label += " (текущий)"
        
        keyboard.append([
            InlineKeyboardButton(month_label, callback_data=f"month_{month_str}")
        ])
    
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="back_to_menu")])
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
    net_text = format_balance(summary["net"])
    
    text = (
        f"📊 Итоги за {month}\n\n"
        f"Поступления: {income_text}\n"
        f"Списания: {expense_text}\n"
        f"Чистый результат: {net_text}"
    )
    
    keyboard = [
        [InlineKeyboardButton("📋 Главное меню", callback_data="back_to_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup)


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

