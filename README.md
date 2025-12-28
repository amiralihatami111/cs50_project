# cs50_project
A Python GUI application built with Tkinter, designed to provide a simple and user-friendly interface for working with data. The project includes robust error handling and packaging with PyInstaller, making it easy to distribute as a portable executable without extra setup.
-----
# Trade Panel

#### 🎥 Video Demo
<URL https://www.aparat.com/v/dbzm9kj >

---

### 📌 Description
Trade Panel is a **simulation environment** designed for beginner traders.
It allows users to practice trading strategies with **no real money involved**,
using live crypto prices, interactive charts, and a simulated wallet system.
The project is intended for **educational purposes only** and helps users understand how trading works in a safe environment.

---

### 🚀 Features
- **Real-Time Prices**
  - Priority order: CoinGecko → Binance Public API → CoinDesk → CoinCap.
  - WebSocket feeds for instant updates.
  - Automatic fallback to REST polling every 3 seconds if live feeds are unavailable.

- **Trading Simulation**
  - Buy and sell crypto assets with simulated balance.
  - Error handling for insufficient funds or invalid inputs.
  - Transactions logged in user-specific history files.

- **Interactive Charts**
  - Line, Bar, Indicator, and Candlestick charts.
  - Powered by Matplotlib and mplfinance.
  - Displays last ~200 data points for performance optimization.

- **User Data Management**
  - Tracks username, sign-in date, starting balance, current balance, and percentage gain/loss.
  - Updates automatically after each trade.
  - Data stored in CSV files for persistence.

- **History Tab**
  - Scrollable table of all trades.
  - Color-coded rows (green for buy, red for sell).
  - Reverse chronological order for easy tracking.

- **Error Logging**
  - All errors logged in `date/erorrs.log`.
  - User-friendly popup messages for invalid actions.

---

### 🛠️ Technologies Used
- **Python 3.x**
- **Tkinter** → GUI framework
- **Matplotlib & mplfinance** → chart visualization
- **Pandas** → CSV data management
- **Requests** → REST API calls
- **WebSocket-client** → real-time price updates
- **ThreadPoolExecutor** → efficient background tasks

---

### 📂 Project Structure
date/ ├── user_date.csv          # User profile and balances ├── wallets.csv            # Wallet balances per asset ├── <username>_history.csv # Trade history per user ├── erorrs.log             # Error logs └── general.log            # Tab change logs main.py                     # Main application entry point

---

### ⚙️ Installation
1. Clone the repository:
   ```bash
   git clone <REPO_URL>
   cd trade-panel
2. Install dependencies:
    pip install requests pandas matplotlib mplfinance websocket-client
▶️ Usage
Run the application:
    python main.py
- Login with your username (e.g., "amir").
- Navigate between tabs: Prices, Trade, History, User Data.
- Start trading in the simulated environment.
🎯 Purpose
This project is intended for educational purposes only.
It helps beginners understand:
• 	How crypto prices change in real-time.
• 	How to interpret different chart types.
• 	How trading decisions affect balance and history.
No real money is involved.

📌 Notes
• 	Data is stored locally in CSV files.
• 	APIs are public and free, but may have rate limits.
• 	The project is a test panel and not suitable for real trading.
• 	Error logs and general logs are maintained for debugging and tracking user actions.
