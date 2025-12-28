import tkinter as tk
from tkinter import ttk
import requests, threading
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import mplfinance as mpf
import pandas as pd
from datetime import datetime
from queue import Queue
import csv
from user_panel import *
import os
import tempfile

folder_path = os.path.join(tempfile.gettempdir(), "date")
if not os.path.exists(folder_path):
    os.makedirs(folder_path)

# ======================================================================
# Configuration: supported crypto assets
# - These identifiers are used with CoinCap REST API.
# - Do not modify display names or count; UI depends on this list.
# ======================================================================
crypto_list = [
    "bitcoin","ethereum","tether","binance-coin","xrp",
    "usd-coin","solana","tron","dogecoin","cardano",
    "bitcoin-cash","chainlink","unus-sed-leo","monero",
    "stellar","zcash","litecoin","sui"
]

# ======================================================================
# Global runtime flags
# - ntbok: gate for notebook-triggered tab rebuild logic
# - is_fetching: prevents overlapping price fetch cycles
# - Do NOT change names used in display; these are internal-only.
# ======================================================================
ntbok = True
is_fetching = False

# ======================================================================
# API Authorization (CoinCap)
# - Token is used for authenticated requests.
# - Keep as provided; do not mutate the header or string literal.
# ======================================================================
header = {"Authorization": "Bearer cd56c1d7d1ae7b2f3b9ccb2fa13c6d388d3bbba9c710ceea66ac44d9fd849c17"}


def get_price(asset: str) -> float | None:
    """
    Retrieve the current USD price for the given crypto asset via CoinCap API.

    Behavior:
    - Sends a GET request to 'https://rest.coincap.io/v3/assets/{asset}' with a 10s timeout.
    - Raises for HTTP errors; extracts 'data.priceUsd' and converts it to float.
    - Returns the float price on success; on failure, writes a log entry to 'date/erorrs.log' and returns None.

    Threading:
    - Pure network I/O; does not touch Tk widgets. Safe for worker thread invocation.

    Parameters:
    - asset: CoinCap asset slug (e.g., 'bitcoin', 'ethereum').

    Returns:
    - float price in USD on success, or None if any exception occurs.
    """
    try:
        r = requests.get(f"https://rest.coincap.io/v3/assets/{asset}", headers=header, timeout=10)
        r.raise_for_status()
        return float(r.json()["data"]["priceUsd"])
    except Exception as e:
        # Log with user context if available; do not change file path or message format.
        try:
            user_for_log = Username
        except NameError:
            user_for_log = "unknown_user"
        with open("date/erorrs.log","a") as file:
            file.write(f"{datetime.now()} @{user_for_log}/ Error fetching price: {e}\n")
        return None


def user_panel(username: str) -> None:
    """
    Build and run the main application window with a ttk.Notebook.

    Tabs:
    - Prices: shows a per-asset line of name, live price, and a 'Trade Now' button.
    - Trade: shows controls for buying/selling the selected asset and a chart area.
    - History: shows a scrollable grid of the user's trade history.
    - User Data: shows profile info, balances, and percentage.

    Concurrency & Safety:
    - A worker thread fetches prices and enqueues UI tasks.
    - The main thread processes the queue and updates Tk widgets.
    - Recurring jobs are tracked by IDs and canceled on close to prevent invalid callbacks.

    Do NOT change any displayed texts, coordinates, sizes, or UI strings.
    Only comments may be altered; internal variable names are preserved for stability.
    """
    # Expose username to other helpers for logging. Do not rename 'Username'.
    global Username
    Username = username

    # ------------------------------------------------------------------
    # Root window and Notebook with four tabs
    # ------------------------------------------------------------------
    root = tk.Tk()
    root.geometry("900x700")
    root.title(f"Main Page - {username}")

    notebook = ttk.Notebook(root)
    notebook.pack(expand=True, fill=tk.BOTH)

    price_tab = ttk.Frame(notebook)
    trade_tab = ttk.Frame(notebook)
    history_tab = ttk.Frame(notebook)
    user_tab = ttk.Frame(notebook)

    notebook.add(price_tab, text="Prices")
    notebook.add(trade_tab, text="Trade")
    notebook.add(history_tab, text="History")
    notebook.add(user_tab, text="User Data")

    # ------------------------------------------------------------------
    # Reactive state and caches for Prices tab
    # - price_vars: asset -> StringVar bound to price Label text
    # - labels:     asset -> Label widget (for color updates)
    # - last_prices: asset -> last numeric price (for ▲/▼ state)
    # - price_history: asset -> rolling price list (max ~300)
    # - running: lifecycle flag preventing reschedules after close
    # ------------------------------------------------------------------
    price_vars: dict[str, tk.StringVar] = {}
    labels: dict[str, tk.Label] = {}
    last_prices: dict[str, float] = {}
    price_history: dict[str, list[float]] = {asset: [] for asset in crypto_list}
    running = True

    # Timer/job IDs and UI task queue (main-thread processor)
    trade_tab_timer_id = None
    update_prices_timer_id = None
    queue_timer_id = None
    ui_queue: Queue = Queue()

    # Chart references managed for cleanup on close
    trade_fig = None
    trade_canvas = None

    # ------------------------------------------------------------------
    # Build Prices tab: per-asset row with name, reactive price, and button
    # Do NOT change any geometry or texts.
    # ------------------------------------------------------------------
    y = 1
    for crypto_name in crypto_list:
        tk.Label(price_tab, text=crypto_name, font=('Arial', 13, 'bold')).place(x=15, y=y * 29)

        var = tk.StringVar(value="---")
        lbl = tk.Label(price_tab, textvariable=var, font=('Arial', 14),
                       width=28, height=1, borderwidth=2, relief="raised")
        lbl.place(x=160, y=y * 29)

        price_vars[crypto_name] = var
        labels[crypto_name] = lbl

        tk.Button(price_tab, text="Trade Now", font=('Arial', 11),
                  width=10, height=1, borderwidth=2, relief="raised",
                  command=lambda name=crypto_name, notbok=False: open_trade_tab(name, notbok)).place(x=650, y=y * 29)
        y += 1

    # ------------------------------------------------------------------
    # Queue processor: apply enqueued UI updates in main thread
    # - Single recurring 'after' job to keep CPU usage modest.
    # - No per-asset timers; this minimizes event churn.
    # ------------------------------------------------------------------
    def process_ui_queue():
        """
        Consume UI tasks from 'ui_queue' and apply them on Tk widgets.

        Task formats:
        - ('update', asset, text, color): sets StringVar text and label fg color.
        - ('error', asset): sets label text to 'error'.

        Scheduling:
        - Reschedules itself every ~200 ms while the app is running.
        """
        nonlocal queue_timer_id
        try:
            while not ui_queue.empty():
                task = ui_queue.get()
                if not (running and root.winfo_exists()):
                    continue
                if task[0] == 'update':
                    _, asset, text, color = task
                    if asset in labels and labels[asset].winfo_exists():
                        price_vars[asset].set(text)
                        labels[asset].config(fg=color)
                elif task[0] == 'error':
                    _, asset = task
                    if asset in labels and labels[asset].winfo_exists():
                        price_vars[asset].set("error")
        except Exception as e:
            with open("date/erorrs.log","a") as file:
                file.write(f"{datetime.now()} @{username}/ Error in process_ui_queue: {e}\n")

        if running and root.winfo_exists():
            queue_timer_id = root.after(200, process_ui_queue)

    # ------------------------------------------------------------------
    # Periodic price update loop: worker thread fetch + enqueue
    # - Uses 'is_fetching' to avoid overlapping cycles.
    # - Reschedules itself via root.after every ~3000 ms.
    # ------------------------------------------------------------------
    def update_prices():
        """
        Fetch prices for all assets on a background thread and enqueue UI updates.

        For each asset:
        - Calls get_price(asset).
        - Derives direction (▲/▼) and color vs last price.
        - Updates 'last_prices' and appends to 'price_history[asset]' (cap ~300).
        - Enqueues ('update', asset, text, color) or ('error', asset).

        Rescheduling:
        - After the worker completes, schedules the next run if 'running' and root exist.
        """
        def worker():
            global is_fetching
            is_fetching = True
            try:
                for asset, var in price_vars.items():
                    if not (running and root.winfo_exists()):
                        break

                    price = get_price(asset)
                    if price is None:
                        ui_queue.put(('error', asset))
                        continue

                    arrow, color = "", "black"
                    last = last_prices.get(asset)
                    if last is not None:
                        if price > last:
                            arrow, color = " ▲", "green"
                        elif price < last:
                            arrow, color = " ▼", "red"

                    last_prices[asset] = price
                    history = price_history[asset]
                    history.append(price)
                    if len(history) > 300:
                        # keep last ~300 entries to limit memory churn
                        del history[:-300]

                    text = f"${price:.4f} USDT{arrow}"
                    ui_queue.put(('update', asset, text, color))
            finally:
                is_fetching = False

            nonlocal update_prices_timer_id
            if running and root.winfo_exists():
                update_prices_timer_id = root.after(3000, update_prices)
            else:
                update_prices_timer_id = None

        if not running or is_fetching:
            return
        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------------
    # Shared error popup: unify all small error windows
    # - Preserves size, placement, and message content usage in buy/sell.
    # ------------------------------------------------------------------
    def show_error(message: str):
        """
        Display a small Tk window with the given error message.
        - Geometry and layout match the existing error windows in buy/sell.
        - Keeps UI text and dimensions consistent with current behavior.
        """
        error_win = tk.Tk()
        error_win.geometry("300x100")
        tk.Label(error_win, text=message).place(x=15, y=15)
        # No modal behavior; consistent with original simple popups.
        return

    # ------------------------------------------------------------------
    # Trade: buy operation
    # - Strictly preserves messages and UI texts; now uses show_error().
    # ------------------------------------------------------------------
    def buy():
        """
        Execute a 'buy' transaction:
        - Validates input amount and balance.
        - Updates wallet CSV and user money CSV.
        - Appends the transaction to per-user history.
        - Refreshes the History tab.

        Errors:
        - NameError: current price absent (label shows 'erorr').
        - KeyError: insufficient funds.
        - Other exceptions: invalid input parsing.
        """
        try :
            select = selected_var.get()
            used_mony = float(buy_mony.get())
            if used_mony == 0.0 or used_mony<0 : raise ValueError
            if used_mony > mony.get() : raise KeyError
            price_var = price_vars[select].get()
            if price_var == "erorr":raise NameError

        except NameError:
            with open("date/erorrs.log","a") as file:
                file.write(f"{datetime.now()} @{username}/ Error canceling buy : {used_mony} but the price isnt to be: {price_var}\n")
            show_error("Cheak Connection or try again")
            return
        except KeyError:
            with open("date/erorrs.log","a") as file:
                file.write(f"{datetime.now()} @{username}/ Error canceling buy : {used_mony} but his mony is {mony.get()}\n")
            show_error("your mony is not enogh to buy")
            return

        except :
            with open("date/erorrs.log","a") as file:
                file.write(f"{datetime.now()} @{username}/ Error canceling buy : {used_mony}\n")
            show_error("your enter isnt intiger")
            return

        price_ = float(str(price_var).replace("$","").replace(" USDT","").replace(" ▼","").replace(" ▲",""))
        new_crypto =crypto.get() + float(used_mony/price_)
        new_crypto = float(f"{new_crypto:.5f}")
        crypto.set(new_crypto)
        filtered.loc[0,select] = new_crypto
        filtered.to_csv("date/wallets.csv", index=False)
        new_many = mony.get()-used_mony
        filtere.loc[0, "now_mony"] = new_many
        filtere.to_csv("date/user_date.csv", index=False)
        new_many = float(f"{new_many:.5f}")
        mony.set(new_many)
        with open(f"date/{username}_history.csv","a", newline='', encoding="utf-8") as history:
            writer =csv.DictWriter(history,fieldnames=["name","time","crypto_name","type","price","used_mony","crypto_value"])
            writer.writerow({"name": username ,"time":datetime.now(), "crypto_name":select
                             ,"type":"buy" ,"price":price_, "used_mony": used_mony,"crypto_value":float(used_mony/price_)})
        open_history_tab()

    # ------------------------------------------------------------------
    # Trade: sell operation
    # - Strictly preserves messages and UI texts; now uses show_error().
    # ------------------------------------------------------------------
    def sell():
        """
        Execute a 'sell' transaction:
        - Validates input amount and available crypto.
        - Updates wallet CSV and user money CSV.
        - Appends the transaction to per-user history.
        - Refreshes the History tab.

        Errors:
        - NameError: current price absent (label shows 'erorr').
        - KeyError: insufficient crypto.
        - Other exceptions: invalid input parsing.
        """
        try :
            select = selected_var.get()
            sell_mony_1 = float(sell_mony.get())
            if sell_mony_1 == 0.0 or sell_mony_1<0 : raise ValueError
            if sell_mony_1 >crypto.get()  : raise KeyError
            price_var = price_vars[select].get()
            if price_var == "erorr":raise NameError

        except NameError:
            with open("date/erorrs.log","a") as file:
                file.write(f"{datetime.now()} @{username}/ Error canceling buy : {sell_mony_1} but the price isnt to be: {price_var}\n")
            show_error("Cheak Connection or try again")
            return
        except KeyError:
            with open("date/erorrs.log","a") as file:
                file.write(f"{datetime.now()} @{username}/ Error canceling buy : {sell_mony_1} but his crypto({select}\n")
            show_error(f"your crypto({select}) is not enogh to buy")
            return

        except :
            with open("date/erorrs.log","a") as file:
                file.write(f"{datetime.now()} @{username}/ Error canceling buy : {sell_mony_1}\n")
            show_error("your enter isnt intiger")
            return

        new_crypto =crypto.get()-sell_mony_1
        new_crypto = float(f"{new_crypto:.5f}")
        crypto.set(new_crypto)
        filtered.loc[0,select] = new_crypto
        filtered.to_csv("date/wallets.csv", index=False)
        used_mony=float(sell_mony_1*float(str(price_var).replace("$","")
                    .replace(" USDT","").replace(" ▼","").replace(" ▲","")))
        new_many = mony.get() + used_mony
        filtere.loc[0, "now_mony"] = new_many
        filtere.to_csv("date/user_date.csv", index=False)
        new_many = float(f"{new_many:.5f}")
        mony.set(new_many)
        with open(f"date/{username}_history.csv","a", newline='', encoding="utf-8") as history:
            writer =csv.DictWriter(history,fieldnames=["name","time","crypto_name","type","price","used_mony","crypto_value"])
            writer.writerow({"name": username ,"time":datetime.now(), "crypto_name":select
                             ,"type":"sell" ,"price":price_var, "used_mony": used_mony,"crypto_value":sell_mony_1})
        open_history_tab()

    # ------------------------------------------------------------------
    # Trade tab: build UI and start periodic sync
    # - Do NOT change control texts or geometry.
    # ------------------------------------------------------------------
    def open_trade_tab(name: str = "bitcoin", notbok: bool = True):
        """
        Build the Trade tab UI and start periodic syncing.

        Behavior:
        - Safely cancels any previous periodic sync job if one exists.
        - Rebuilds trade_tab contents: asset ComboBox, price Label, chart frame,
          buy/sell entries and buttons, and money/crypto labels.
        - Binds selection changes to sync the price label and chart.
        - Starts periodic_sync using a named function stored in trade_tab_timer_id.

        Notes:
        - 'notbok' distinguishes Notebook-driven opens from button-driven ones and controls ntbok.
        - No geometry or label text changes are allowed.
        """
        global ntbok
        ntbok = notbok

        nonlocal trade_tab_timer_id, trade_fig, trade_canvas

        # Cancel previous periodic sync job safely
        if trade_tab_timer_id:
            try:
                root.after_cancel(trade_tab_timer_id)
            except Exception as e:
                with open("date/erorrs.log","a") as file:
                    file.write(f"{datetime.now()} @{username}/ Error canceling trade_tab previous timer: {e}\n")
            trade_tab_timer_id = None

        # Rebuild Trade tab UI
        for widget in trade_tab.winfo_children():
            try:
                widget.destroy()
            except:
                pass

        notebook.select(trade_tab)

        # Asset selection combobox (value set to provided name)
        global selected_var
        selected_var = tk.StringVar(value=name)
        combo = ttk.Combobox(trade_tab, textvariable=selected_var,
                             values=crypto_list, state="readonly",
                             font=('Arial', 15, 'bold'))
        combo.place(x=25, y=35)

        # Live price label for the selected asset
        trade_price_label = tk.Label(trade_tab, text="---",
                                     font=('Arial', 15, 'bold'),
                                     borderwidth=2, relief="solid")
        trade_price_label.place(x=405, y=35)

        # Chart type selector
        chart_type_var = tk.StringVar(value="Line")
        chart_type_combo = ttk.Combobox(trade_tab, textvariable=chart_type_var,
                                        values=["Line", "Bar", "Indicator", "Candlestick"],
                                        state="readonly", font=('Arial', 12))
        chart_type_combo.place(x=25, y=80 )

        # Chart container frame (Matplotlib embeds into this)
        chart_frame = tk.Frame(trade_tab, borderwidth=1, relief="groove")
        chart_frame.place(x=25, y=130, width=860, height=400)

        # Create chart resources and keep references for teardown
        trade_fig, ax = plt.subplots(figsize=(8.5, 5))
        trade_canvas = FigureCanvasTkAgg(trade_fig, master=chart_frame)
        trade_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # Entry for buy
        global buy_mony
        buy_mony = tk.StringVar(value="")
        buy_entry = tk.Entry(trade_tab, bd =5,textvariable = buy_mony , font=('calibre',10,'normal'))
        buy_entry.place(x=50,y=550 ,width=145, height=33)

        # Entry for sell
        global sell_mony
        sell_mony = tk.StringVar(value="")
        sell_entry = tk.Entry(trade_tab, bd =5,textvariable = sell_mony, font=('calibre',10,'normal'))
        sell_entry.place(x=400,y=550, width=145, height=33)

        # Create trade button(sell and buy)
        buy_button = tk.Button(trade_tab, text="buy",
                                     font=('Arial', 22),
                                     bg = "green",command=lambda:buy())
        buy_button.place(x=210, y=550, width=80, height=66)
        sell_button = tk.Button(trade_tab, text="sell",
                                     font=('Arial', 22),
                                     bg="red",command=lambda:sell())
        sell_button.place(x=570, y=550, width=80, height=66)

        # Read money and crypto value from CSV
        data = pd.read_csv("date/user_date.csv")
        global filtere
        filtere = data[data["name"] == Username]

        # Money value as DoubleVar
        global mony
        mony = tk.DoubleVar(value=float(filtere["now_mony"].iloc[0]))

        # ------------------------------------------------------------------
        # Wallet balance loader for selected asset; sets 'crypto' DoubleVar.
        # ------------------------------------------------------------------
        def walet(crypto_name):
            """
            Load the user's wallet balance for the given asset and set 'crypto' DoubleVar.
            - Reads 'date/wallets.csv' and filters by Username.
            - Converts the balance to a formatted float with 5 decimals.
            - If missing, sets 0.0.
            """
            data_crypto = pd.read_csv("date/wallets.csv")
            global filtered
            filtered = data_crypto[data_crypto["name"] == Username]
            try :
                crypto_str = filtered[crypto_name].iloc[0]
                crypto_str = f"{float(crypto_str):.5f}"
                global crypto
                crypto.set(float(crypto_str))
            except :
                crypto.set(0.0)

        global crypto
        crypto=tk.DoubleVar(value=0.0)
        walet(selected_var.get())

        # Money and crypto display labels (bound to the corresponding DoubleVars)
        mony_label = tk.Label(trade_tab, textvariable= mony,
                                     font=('Arial', 11),
                                     borderwidth=1, relief="solid")
        mony_label.place(x=50, y=585,width=145, height=33)
        crypto_label = tk.Label(trade_tab, textvariable=crypto,
                                     font=('Arial', 11),
                                     borderwidth=1, relief="solid")
        crypto_label.place(x=400, y=585,width=145, height=33)

        # ------------------------------------------------------------------
        # Chart drawing: renders Line/Bar/Indicator/Candlestick
        # - Uses the last ~60 samples from price_history.
        # ------------------------------------------------------------------
        def draw_chart(asset: str, chart_kind: str):
            """
            Render the selected chart type for the given asset based on recent price history.

            Behavior:
            - Clears axes and draws Line, Bar, Indicator, or Candlestick chart.
            - For Candlestick, builds OHLC windows from chunks of 4 samples and uses mplfinance.
            - Updates chart title and axes labels, applies tight layout, and refreshes the canvas.
            """
            ax.clear()
            data = price_history.get(asset, [])[-60:]
            if len(data) < 2:
                ax.text(0.5, 0.5, "Not enough data yet...",
                        ha='center', va='center', fontsize=12, color='gray', transform=ax.transAxes)
                ax.set_axis_off()
            else:
                if chart_kind == "Line":
                    ax.plot(data, color="steelblue", linewidth=2)
                elif chart_kind == "Bar":
                    ax.bar(range(len(data)), data, color="orange")
                elif chart_kind == "Indicator":
                    ax.plot(data, color="purple", linestyle="--", marker="o", markersize=4)
                elif chart_kind == "Candlestick":
                    # Build OHLC from chunks of 4 samples
                    ohlc = []
                    chunk = 4
                    for i in range(0, len(data) - chunk + 1, chunk):
                        window = data[i:i+chunk]
                        if len(window) < chunk:
                            continue
                        ohlc.append([i, window[0], max(window), min(window), window[-1]])
                    if len(ohlc) == 0:
                        ax.text(0.5, 0.5, "Not enough data for candlestick...",
                                ha='center', va='center', fontsize=12, color='gray', transform=ax.transAxes)
                        ax.set_axis_off()
                    else:
                        df = pd.DataFrame(ohlc, columns=["Date","Open","High","Low","Close"])
                        df["Date"] = pd.date_range(start=pd.Timestamp.now(), periods=len(df), freq="T")
                        df.set_index("Date", inplace=True)
                        mpf.plot(df, type='candle', ax=ax, style='charles')

                ax.set_title(f"{asset} price chart ({chart_kind})")
                ax.set_ylabel("USD")
                trade_fig.tight_layout()
            trade_canvas.draw()

        # ------------------------------------------------------------------
        # Synchronize Trade tab with current selection and Prices tab color/text
        # ------------------------------------------------------------------
        def sync_trade(event=None):
            """
            Synchronize the Trade tab:
            - Copies text and foreground color from Prices tab to trade label.
            - Redraws chart for selected asset and chart type.
            - Updates wallet display for the selected asset.
            """
            try:
                asset = selected_var.get()
                if trade_price_label.winfo_exists() and asset in price_vars and asset in labels:
                    trade_price_label.config(
                        text=price_vars[asset].get(),
                        fg=labels[asset].cget("fg")
                    )
                draw_chart(asset, chart_type_var.get())
                walet(asset)
            except Exception as e:
                with open("date/erorrs.log","a") as file:
                    file.write(f"{datetime.now()} @{username}/ Error in sync_trade: {e}\n")

        # Bind selection changes to sync
        combo.bind("<<ComboboxSelected>>", sync_trade)
        chart_type_combo.bind("<<ComboboxSelected>>", sync_trade)

        # ------------------------------------------------------------------
        # Periodic sync: refresh trade tab at interval while app is alive
        # ------------------------------------------------------------------
        def periodic_sync():
            """
            Periodically refresh the trade tab:
            - Calls sync_trade and reschedules itself every 2000 ms using root.after.
            - Stores the job ID in 'trade_tab_timer_id' for safe cancellation.
            """
            nonlocal trade_tab_timer_id
            if running and trade_tab.winfo_exists():
                sync_trade()
                trade_tab_timer_id = root.after(2000, periodic_sync)

        # Initial sync and start periodic refresh
        sync_trade()
        periodic_sync()

    # ------------------------------------------------------------------
    # History tab: render a scrollable grid of user transactions
    # Do NOT change label texts or column widths.
    # ------------------------------------------------------------------
    def open_history_tab():
        """
        Build the History tab grid:
        - Creates a scrollable frame with vertical and horizontal scrollbars.
        - Reads the user's history CSV and displays rows in reverse chronological order.
        - Colors rows green for 'buy' and red for 'sell'.
        """
        if not running:
            return
        for widget  in history_tab.winfo_children():
            widget.destroy()

        # Frame + canvas + scrollbars
        frame = tk.Frame(history_tab)
        frame.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(frame, width=400, height=250)
        canvas.grid(row=0, column=0, sticky="nsew")

        scrollbar_y = tk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        scrollbar_y.grid(row=0, column=1, sticky="ns")

        scrollbar_x = tk.Scrollbar(frame, orient="horizontal", command=canvas.xview)
        scrollbar_x.grid(row=1, column=0, sticky="ew")

        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        canvas.configure(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)

        scrollable_frame = tk.Frame(canvas)
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")

        def configure_scrollregion(event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        scrollable_frame.bind("<Configure>", configure_scrollregion)

        file = open(f"date/{username}_history.csv", newline="")
        column=0
        titel = {"crypto_name":18,"type":15,"price":18,"used_mony":19,"crypto_value":19,"time":25}
        column = 0
        for key, width in titel.items():
            tk.Label(
                scrollable_frame,
                text=key,
                borderwidth=2,
                relief="solid",
                font=('Arial', 12),
                width=width,
                height=3
            ).grid(row=0, column=column, padx=5, pady=5)
            column += 1

        row = 1
        reader = csv.DictReader(file)
        trade = list(reader)
        trade.reverse()

        for i in trade:
            column = 0
            for key, width in titel.items():
                if i["type"] == "buy":
                    color = "green"
                else:
                    color = "red"

                tk.Label(
                    scrollable_frame,
                    text=i[key],
                    borderwidth=2,
                    relief="solid",
                    font=('Arial', 12),
                    fg=color,
                    width=width,
                    height=3
                ).grid(row=row, column=column, padx=5, pady=5)

                column += 1
            row += 1
        file.close()

    # ------------------------------------------------------------------
    # User Data tab: render user profile and computed percent
    # Do NOT change display texts or calculations.
    # ------------------------------------------------------------------
    def open_user_tab():
        """
        Build the User Data tab:
        - Filters the user record from 'date/user_date.csv'.
        - Displays username, sign-in date, start money, current money, and percent.
        - Writes the 'percent' back into the CSV for the user record.
        """
        user_file = pd.read_csv("date/user_date.csv")
        filter = user_file[user_file["name"] == Username]
        times =filter["login_days"].iloc[0]
        start_mony =float(filter["start_mony"].iloc[0])
        now_mony =float(filter["now_mony"].iloc[0])
        persent= float(f"{(now_mony - start_mony)/start_mony*100:.1f}")
        tk.Label(user_tab,text="your Username :",font=('Arial', 13, 'bold')).place(x=25,y=25)
        tk.Label(user_tab,text=Username,font=('Arial', 13, 'bold')).place(x=250,y=25)
        tk.Label(user_tab,text="data sign in :",font=('Arial', 13, 'bold')).place(x=25,y=75)
        tk.Label(user_tab,text=times,font=('Arial', 13, 'bold')).place(x=250,y=75)
        tk.Label(user_tab,text="your start mony :",font=('Arial', 13, 'bold')).place(x=25,y=125)
        tk.Label(user_tab,text=start_mony,font=('Arial', 13, 'bold')).place(x=250,y=125)
        tk.Label(user_tab,text="your mony now :",font=('Arial', 13, 'bold')).place(x=25,y=175)
        tk.Label(user_tab,text=now_mony,font=('Arial', 13, 'bold')).place(x=250,y=175)
        tk.Label(user_tab,text="main persent :",font=('Arial', 13, 'bold')).place(x=25,y=225)
        tk.Label(user_tab,text=f"{persent}%",font=('Arial', 13, 'bold')).place(x=250,y=225)
        filter.loc[0, "percent"] = persent
        filter.to_csv("date/user_date.csv", index=False)

    # ------------------------------------------------------------------
    # CLEAN EXIT: stop updates when window closes
    # Do NOT change flow or messages; only comments added.
    # ------------------------------------------------------------------
    def on_close():
        """
        Stop all periodic loops and close Matplotlib resources, then break mainloop and destroy root.

        Behavior:
        - Sets 'running' False and 'ntbok' False to prevent future scheduling and rebuilds.
        - Cancels timers (trade_tab_timer_id, update_prices_timer_id, queue_timer_id).
        - Empties the UI queue to prevent further processing.
        - Destroys the Trade tab canvas widget and closes the Matplotlib figure.
        - Calls 'root.quit()' to break mainloop immediately, then 'root.destroy()'.
        """
        nonlocal running, trade_tab_timer_id, update_prices_timer_id, queue_timer_id, trade_fig, trade_canvas
        global ntbok
        running = False
        ntbok = False  # prevent tab-change handler from rebuilding UI during shutdown

        # Cancel timers safely
        try:
            if trade_tab_timer_id:
                root.after_cancel(trade_tab_timer_id)
                trade_tab_timer_id = None
        except Exception as e:
            with open("date/erorrs.log","a") as file:
                file.write(f"{datetime.now()} @{username}/ Error canceling trade_tab timer: {e}\n")
        try:
            if update_prices_timer_id:
                root.after_cancel(update_prices_timer_id)
                update_prices_timer_id = None
        except Exception as e:
            with open("date/erorrs.log","a") as file:
                file.write(f"{datetime.now()} @{username}/ Error canceling update_prices timer: {e}\n")
        try:
            if queue_timer_id:
                root.after_cancel(queue_timer_id)
                queue_timer_id = None
        except Exception as e:
            with open("date/erorrs.log","a") as file:
                file.write(f"{datetime.now()} @{username}/ Error canceling queue timer: {e}\n")

        # Drain queue to avoid pending UI tasks
        try:
            while not ui_queue.empty():
                ui_queue.get_nowait()
        except:
            pass

        # Explicitly destroy canvas widget and close figure to free backend resources
        try:
            if trade_canvas is not None:
                try:
                    trade_canvas.get_tk_widget().destroy()
                except:
                    pass
                trade_canvas = None
        except Exception as e:
            with open("date/erorrs.log","a") as file:
                file.write(f"{datetime.now()} @{username}/ Error destroying canvas widget: {e}\n")

        try:
            if trade_fig is not None:
                try:
                    plt.close(trade_fig)
                except:
                    pass
                trade_fig = None
        except Exception as e:
            with open("date/erorrs.log","a") as file:
                file.write(f"{datetime.now()} @{username}/ Error closing figure: {e}\n")

        # Break the Tk mainloop immediately and destroy root
        try:
            root.quit()     # ensures mainloop exits immediately
        except:
            pass
        root.destroy()

    # Bind window close to on_close
    root.protocol("WM_DELETE_WINDOW", on_close)

    # ------------------------------------------------------------------
    # Notebook tab change handler
    # - Logs tab clicks and opens relevant tabs when ntbok=True.
    # ------------------------------------------------------------------
    def on_tab_changed(event):
        """
        Handle tab changes; logs the tab title and opens the corresponding tab if allowed by 'ntbok'.

        Behavior:
        - Retrieves selected tab ID and title.
        - Appends a log entry (timestamp, username, tab text) to 'general.log'.
        - If 'Trade'/'History'/'User Data' is selected and 'ntbok' is True, calls the relevant handler.
        """
        if not running:  # guard against rebuild during shutdown
            return
        selected_tab = event.widget.select()  # get selected tab id
        tab_text = event.widget.tab(selected_tab, "text")  # get tab title
        with open("date/general.log","a") as file:
            file.write(f"{datetime.now()} @{username}/ Tab clicked: {tab_text}\n")
        # Only rebuild when invoked by notebook (ntbok=True).
        if tab_text == "Trade" and ntbok:
            open_trade_tab()  # respects default argument (bitcoin) only when coming from notebook
        elif tab_text == "History" and ntbok:
            open_history_tab()
        elif tab_text == "User Data" and ntbok:
            open_user_tab()

    # Bind tab change
    notebook.bind("<<NotebookTabChanged>>", on_tab_changed)

    # ------------------------------------------------------------------
    # Start periodic loops BEFORE mainloop; use only one mainloop
    # ------------------------------------------------------------------
    update_prices()          # start worker-driven fetch loop (schedules itself)
    process_ui_queue()       # start single recurring queue processor

    # Enter Tk event loop
    root.mainloop()


# Entrypoint
if __name__ == "__main__":
    # Do NOT change the username literal or flow here.
    user_panel("amir")