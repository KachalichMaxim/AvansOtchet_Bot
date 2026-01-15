#!/bin/bash
# Deployment script for Avansi Bot

set -e

echo "Deploying Avansi Bot..."

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Set up Google Sheets (if not already done)
echo "Setting up Google Sheets..."
python setup_sheets.py

# Create .env file if it doesn't exist (optional, bot uses defaults from config.py)
if [ ! -f ".env" ]; then
    echo "Creating .env file..."
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "Please edit .env file and set your TELEGRAM_BOT_TOKEN if needed"
    else
        # Create .env file with default values from config
        cat > .env << EOF
# Telegram Bot Token (get from @BotFather)
# Note: Default token is already set in bot/config.py
TELEGRAM_BOT_TOKEN=8538778789:AAEyEwR3h7HkVKHshli7eafd3Fchg9rRd_k

# Google Sheets
GOOGLE_SHEETS_ID=1TfF8PFjJ0cBOWLtod6OpNhRtOSGZDbOKCG7NIdudzoY
GOOGLE_CREDENTIALS_PATH=tonal-concord-464913-u3-2024741e839c.json

# Timezone
TIMEZONE=Europe/Moscow
EOF
        echo ".env file created with default values from config.py"
        echo "Note: Bot will use defaults from config.py if .env is not present"
    fi
fi

# Check if systemd service file exists
if [ -f "avansi-bot.service" ]; then
    echo "Installing systemd service..."
    sudo cp avansi-bot.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable avansi-bot.service
    echo "Service installed. Start with: sudo systemctl start avansi-bot"
fi

echo "Deployment completed!"
echo "To start the bot: sudo systemctl start avansi-bot"
echo "To check status: sudo systemctl status avansi-bot"
echo "To view logs: sudo journalctl -u avansi-bot -f"

