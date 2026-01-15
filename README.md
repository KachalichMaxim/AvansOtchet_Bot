# Telegram Bot for Employee Advance Reports

A Telegram bot system for managing employee advance reports with Google Sheets integration.

## Features

- Personal advance reports for each employee
- FSM-based operation flow for adding transactions
- Automatic balance calculation
- Monthly summaries
- Audit logging
- Data isolation per employee

## Prerequisites

- Python 3.8+
- Google Cloud service account with Sheets API enabled
- Telegram Bot Token (from @BotFather)
- Google Sheet ID (from the sheet URL)

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

Or use a virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment

The bot token and Google Sheets ID are already configured in `bot/config.py` with defaults from your files. If you need to override them, create a `.env` file:

```bash
TELEGRAM_BOT_TOKEN=your_token_here
GOOGLE_SHEETS_ID=your_sheet_id_here
GOOGLE_CREDENTIALS_PATH=tonal-concord-464913-u3-2024741e839c.json
TIMEZONE=Europe/Moscow
```

### 3. Set Up Google Sheets

**Important:** Share your Google Sheet with the service account email:
`service-account-for-telegram-c@tonal-concord-464913-u3.iam.gserviceaccount.com`

Grant **Editor** permissions.

Run the setup script to create the required sheets structure:

```bash
python setup_sheets.py
```

This will create:
- `Справочник` - Reference data (OperationDirection, Категория, Тип, Активно)
- `Шаблон_Сотрудника` - Template for employee sheets with balance formulas
- `Audit_Log` - Audit trail
- `Итоги_Месяц` - Monthly summaries

### 4. Add Reference Data

Edit the `Справочник` sheet and add your categories and types:

| OperationDirection | Категория | Тип | Активно |
|-------------------|-----------|-----|---------|
| IN | Банковские | Перевод | TRUE |
| OUT | Банковские | Проценты | TRUE |
| OUT | Офисные | Доверенности | TRUE |

### 5. Run the Bot

For development:
```bash
python -m bot.main
```

For production (VPS), see Deployment section below.

## Usage

1. Start the bot: `/start`
2. Enter your name when prompted
3. Use the menu to:
   - ➕ Add operations (income/expense)
   - 📊 View monthly summaries
   - 💰 Check current balance

## Google Sheets Structure

### Employee Sheet Columns

| Дата | Поступление (+) | Списание (-) | Категория | Тип | Описание | Остаток после операции |
|------|----------------|--------------|-----------|-----|----------|----------------------|

The "Остаток после операции" column uses formulas to automatically calculate running balance.

### Audit Log Columns

| Timestamp | Пользователь | Лист | Действие | Поле | Старое значение | Новое значение |

## Deployment (VPS)

### Using systemd

1. Copy files to `/opt/avansi-bot/`:
```bash
sudo mkdir -p /opt/avansi-bot
sudo cp -r * /opt/avansi-bot/
```

2. Run deployment script:
```bash
cd /opt/avansi-bot
sudo ./deploy.sh
```

3. Edit service file if needed:
```bash
sudo nano /etc/systemd/system/avansi-bot.service
```

4. Start the service:
```bash
sudo systemctl start avansi-bot
sudo systemctl enable avansi-bot  # Auto-start on boot
```

5. Check status:
```bash
sudo systemctl status avansi-bot
sudo journalctl -u avansi-bot -f  # View logs
```

### Manual Deployment

1. Create virtual environment and install dependencies
2. Set up Google Sheets (run `setup_sheets.py`)
3. Configure `.env` file
4. Run: `python -m bot.main`

## Troubleshooting

- **Bot not responding**: Check if token is correct and bot is running
- **Sheets access denied**: Ensure service account email has Editor access
- **Balance not calculating**: Check formulas in employee sheets
- **Categories not showing**: Verify `Справочник` sheet has data with `Активно=TRUE`

## Security Notes

- Never commit `.env` file or service account JSON to git
- Keep service account credentials secure
- Regularly review audit logs
- Limit sheet access to authorized users only

