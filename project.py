from tkinter import *
import csv
from datetime import datetime
import csv
from user_panel import *
import os
from user_panel import *
# addres
folder_path = os.path.join(os.path.dirname(__file__), "date")
if not os.path.exists(folder_path):
    os.makedirs(folder_path)

# ============================================================
# Application entry point
# ============================================================
def main():
    """
    Main entry point of the application.
    Initializes and shows the login window.
    """
    general_log()

# ============================================================
# Login window
# ============================================================
def general_log():
    """
    Create and manage the login window.
    - Collects username and password.
    - Validates credentials against 'date/user_date.csv'.
    - On success: logs the event and opens the user panel.
    - On failure: shows a visible error label within the window.
    """
    global login_program
    login_program = Tk()

    # Window configuration
    login_program.title("Log In")
    login_program.geometry("320x240")

    # StringVar holders for user input (reactive storage for Tk widgets)
    username_var = StringVar()
    password_var = StringVar()

    # ------------------------------------------------------------
    # Internal: validate and proceed to user panel
    # ------------------------------------------------------------
    def check_log():
        """
        Validate credentials:
        - Reads 'date/user_date.csv' with DictReader.
        - Filters rows where both 'name' and 'password' match the input.
        - On success: destroy login window, append to 'general.log', and open user panel.
        - On failure: display an in-window error label.
        """
        username = username_var.get()
        password = password_var.get()

        # Read user records from CSV
        with open(os.path.join(folder_path, 'user_date.csv'), 'r') as csvfile:
            csv_reader = csv.DictReader(csvfile)
            user_data = [
                row for row in csv_reader
                if row["name"] == username and row["password"] == password
            ]

        if len(user_data) < 1:
            # Show an error label (placed within current window)
            error_label = Label(
                login_program,
                text='Username/Password is incorrect. Try again.',
                font=('calibre', 10, 'bold'),
                bg="red"
            )
            error_label.place(x=25, y=170)
        else:
            # Success: close login window, log the event, open user panel
            login_program.destroy()
            with open(os.path.join(folder_path, "general.log"), "a") as file:
                file.write(f"{datetime.now()} \\{username}\\ logged in successfully\n")
            user_panel(username)

    # ------------------------------------------------------------
    # UI: labels, entries, and actions
    # ------------------------------------------------------------
    # Username
    user_label = Label(login_program, text='Username', font=('calibre', 10, 'bold'))
    user_label.place(x=33, y=15)

    user_entry = Entry(login_program, bd=5, textvariable=username_var, font=('calibre', 10, 'normal'))
    user_entry.place(x=103, y=15)

    # Password
    pass_label = Label(login_program, text="Password", font=('calibre', 10, 'bold'))
    pass_label.place(x=33, y=50)

    pass_entry = Entry(login_program, bd=5, textvariable=password_var, font=('calibre', 10, 'normal'))
    pass_entry.place(x=103, y=50)

    # Login action
    log_button = Button(
        login_program,
        text="Log In",
        fg="blue",
        command=check_log,
        font=('calibre', 11, 'normal')
    )
    log_button.place(x=38, y=100)

    # Sign-up guidance and action
    sign_label = Label(login_program, text="Don't have an account:", font=('calibre', 9, 'normal'))
    sign_label.place(x=94, y=105)

    sign_button = Button(
        login_program,
        text="Sign Up",
        fg="red",
        command=sign_up,
        font=('calibre', 11, 'normal')
    )
    sign_button.place(x=200, y=100)

    # Event loop for the login window
    login_program.mainloop()

# ============================================================
# Sign-up window
# ============================================================
def sign_up():
    """
    Create and manage the sign-up window.
    Responsibilities:
    - Collect username, password, and starting money.
    - Validate inputs (format, uniqueness, strength).
    - Persist new user in 'date/user_date.csv'.
    - Initialize wallet in 'date/wallets.csv' and user history 'date/{username}_history.csv'.
    - Log events to 'date/general.log'.
    - Show success window and return to main login.
    """
    # Close the login window if present
    login_program.destroy()

    # Create a new sign-up window
    sign_program = Tk()
    sign_program.title("Sign Up")
    sign_program.geometry("300x200")

    # Reactive variables for user input
    username_var = StringVar()
    password_var = StringVar()
    start_money_var = StringVar()

    # ------------------------------------------------------------
    # Validation: username, password, starting money
    # ------------------------------------------------------------
    def check_password(username: str, password: str, money: int | str) -> int:
        """
        Validate provided credentials and starting money with the following rules:

        Username:
        - Must be at least 3 characters.
        - Must not be purely digits.
        - Must be unique in 'date/user_date.csv'.
        - Must be non-empty.

        Password:
        - Must include at least one special character among '@#$'.
        - Must include both uppercase and lowercase letters.
        - Must include numbers (i.e., not purely alphabetic).
        - Must be at least 7 characters.

        Starting money:
        - Must be an integer string, or in the format '<integer>$'.
        - Must be non-empty.

        Returns:
            True if all validations pass; otherwise False.
        """
        with open(os.path.join(folder_path, 'user_date.csv'), 'r') as csvfile:
            csv_reader = csv.DictReader(csvfile)

            # Username validation
            if any(row["name"] == username for row in csv_reader) or username == "" or username.isdigit() or len(username) < 3:
                error_text = "Username is already used, invalid, or too short (minimum 3 characters)."

            # Password validation
            elif not any(i in password for i in "@#$") or len(password) < 7 or \
                 password.lower() == password or password.upper() == password or password.isalpha():
                error_text = "Password must contain numbers, special characters (@#$), uppercase & lowercase letters, and be at least 7 characters long."

            # Starting money validation
            elif not (money.isdigit() or money.replace("$", "").isdigit()) or not money:
                error_text = "Starting money must be an integer or formatted as 'integer$'."

            else:
                return True

            # Log error to general log for auditing
            with open(os.path.join(folder_path, "general.log"), "a") as file:
                file.write(f"{datetime.now()} \\no username\\ Error: {error_text}\n")

            # Show a minimal message window with computed size based on label
            error_window = Tk()
            error_window.title("Message")
            error_label = Label(error_window, text=error_text, font=('calibre', 10, 'bold'))
            error_label.place(height=45)

            # Dynamically fit the window to the label requirements
            error_label.update_idletasks()
            width = error_label.winfo_reqwidth()
            height = error_label.winfo_reqheight()
            error_window.geometry(f"{width + 10}x{height + 20}")

            return False

    # ------------------------------------------------------------
    # Finalize sign-up: persist user and initialize files
    # ------------------------------------------------------------
    def check_sign():
        """
        Execute the sign-up workflow:
        - Validate input via `check_password`.
        - Append the user to 'date/user_date.csv'.
        - Log the successful sign-up to 'date/general.log'.
        - Initialize the user's wallet in 'date/wallets.csv' using `crypto_list`.
        - Create the user's history file 'date/{username}_history.csv' with header.
        - Display success window and redirect to `main`.
        """
        username = username_var.get()
        password = password_var.get()
        money = start_money_var.get()

        valid = check_password(username, password, money)
        if valid:
            # Persist user record
            with open(os.path.join(folder_path, 'user_date.csv'), 'a', newline='') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=[
                    "name", "password", "start_mony", "now_mony",
                    "profit_percent", "login_days", "level"
                ])
                writer.writerow({
                    "name": username,
                    "password": password,
                    "start_mony": money,
                    "now_mony": money,
                    "profit_percent": 0,
                    "login_days": datetime.now(),
                    "level": "normal"
                })

            # Audit trail: successful sign-up
            with open(os.path.join(folder_path, "general.log"), "a") as file:
                file.write(f"{datetime.now()} \\{username}\\ successfully signed up\n")

            # Initialize wallets: ensure one row per user with zero balances for all cryptos
            with open(os.path.join(folder_path, "wallets.csv"), "a", newline='') as wallets_file:
                wallet_data = {"name": username}
                for crypto in crypto_list:
                    if crypto == username:
                        # Preserve 'name' field as username
                        wallet_data["name"] = username
                    else:
                        # Initialize crypto balances to zero
                        wallet_data[crypto] = 0
                writer = csv.DictWriter(wallets_file, fieldnames=["name"] + crypto_list)
                writer.writerow(wallet_data)

            # Initialize per-user history with a standard header
            with open(os.path.join(folder_path, f"{username}_history.csv"), "a", newline='') as history_file:
                user_wallet = csv.DictWriter(history_file, fieldnames=[
                    "name", "time", "crypto_name", "type", "price", "used_mony", "crypto_value"
                ])
                user_wallet.writeheader()

            # --------------------------------------------------------
            # Success message and return flow
            # --------------------------------------------------------
            def success_window():
                """
                Close the success message window and re-enter the application at `main()`.
                """
                success_win.destroy()
                main()

            # Build a minimal success dialog
            success_win = Tk()
            success_win.title("Message")
            success_win.geometry("180x100")

            success_label = Label(success_win, text="Successfully signed up", font=('calibre', 10, 'bold'))
            success_label.place(x=5, y=15)

            success_button = Button(
                success_win,
                text="OK",
                fg="blue",
                command=success_window,
                font=('calibre', 11, 'normal')
            )
            success_button.place(x=50, y=50)

            # Close the sign-up form after success to avoid duplicate windows
            sign_program.destroy()

    # ------------------------------------------------------------
    # UI: sign-up form elements
    # ------------------------------------------------------------
    # Username
    user_label = Label(sign_program, text='Username', font=('calibre', 10, 'bold'))
    user_label.place(x=33, y=15)

    user_entry = Entry(sign_program, bd=5, textvariable=username_var, font=('calibre', 10, 'normal'))
    user_entry.place(x=103, y=15)

    # Password
    pass_label = Label(sign_program, text="Password", font=('calibre', 10, 'bold'))
    pass_label.place(x=33, y=50)

    pass_entry = Entry(sign_program, bd=5, textvariable=password_var, font=('calibre', 10, 'normal'))
    pass_entry.place(x=103, y=50)

    # Starting money
    money_label = Label(sign_program, text="Start Money", font=('calibre', 10, 'bold'))
    money_label.place(x=25, y=85)

    money_entry = Entry(sign_program, bd=5, textvariable=start_money_var, font=('calibre', 9, 'normal'))
    money_entry.place(x=110, y=85)

    # Sign-up action
    sign_button = Button(
        sign_program,
        text="Sign Up",
        fg="blue",
        command=check_sign,
        font=('calibre', 11, 'normal')
    )
    sign_button.place(x=108, y=135)

    # Event loop for the sign-up window
    sign_program.mainloop()

# ============================================================
# Bootstrap
# ============================================================
if __name__ == "__main__":
    """
    When executed as a script:
    - Start the application by calling `main()`.
    - This enters the login window flow.
    """
    main()

