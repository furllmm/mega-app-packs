import tkinter as tk
from tkinter import ttk, simpledialog, messagebox
import json
import os
import sqlite3 # Added for database
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
import base64

# --- Constants ---
APP_NAME = "Mnemonic Phrase Storage"
GEOMETRY = "650x730" # Slightly wider for new entry
DB_FILE = "wallets.db"
SALT_FILE = "salt.bin" # Stores salt for key derivation
PASSWORD_CHECK_FILE = "pwd_check.bin" # Stores a check value to verify password

# --- Global Variables ---
encryption_key = None

# For managing currently loaded/displayed data
current_wallet_id = None
current_wallet_name_displayed = "" # Name of the wallet currently loaded and shown in wallet_name_entry
current_mnemonic_entries_in_wallet = [] # List of dicts: {'entry_id', 'purpose', 'encrypted_mnemonic' (encrypted)}
current_mnemonic_entry_idx = -1      # Index in current_mnemonic_entries_in_wallet for displayed entry

# --- Database Setup ---
def init_db():
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        # Create wallets table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS wallets (
                wallet_id INTEGER PRIMARY KEY AUTOINCREMENT,
                wallet_name TEXT UNIQUE NOT NULL
            )
        ''')
        # Create mnemonic_entries table (renamed from wallets, new structure)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS mnemonic_entries (
                entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
                wallet_id INTEGER NOT NULL,
                purpose TEXT NOT NULL,
                encrypted_mnemonic TEXT NOT NULL,
                FOREIGN KEY (wallet_id) REFERENCES wallets (wallet_id) ON DELETE CASCADE,
                UNIQUE (wallet_id, purpose) 
            )
        ''')
        conn.commit()
        conn.close()
        return True
    except sqlite3.Error as e:
        messagebox.showerror("Database Error", f"Failed to initialize database: {e}")
        return False

# --- Encryption/Decryption ---
def generate_salt():
    return os.urandom(16)

def derive_key(password: str, salt: bytes):
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480000, # NIST recommendation for PBKDF2
        backend=default_backend()
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))

def encrypt_data(data: str, key: bytes):
    f = Fernet(key)
    return f.encrypt(data.encode()).decode()

def decrypt_data(encrypted_data: str, key: bytes):
    f = Fernet(key)
    try:
        return f.decrypt(encrypted_data.encode()).decode()
    except Exception as e:
        print(f"Decryption failed: {e}") # Keep console log for debugging decryption issues
        # Avoid showing detailed crypto errors to user in most cases, unless it's a clear "wrong password" type scenario handled elsewhere.
        return None

def setup_password():
    global encryption_key
    if not os.path.exists(SALT_FILE) or not os.path.exists(PASSWORD_CHECK_FILE):
        # First time setup
        password = simpledialog.askstring("Set Master Password", "Create a new master password:", show='*')
        if not password:
            messagebox.showerror("Error", "Password cannot be empty. Exiting.")
            root.quit()
            return False

        confirm_password = simpledialog.askstring("Confirm Master Password", "Confirm your master password:", show='*')
        if password != confirm_password:
            messagebox.showerror("Error", "Passwords do not match. Exiting.")
            root.quit()
            return False

        salt = generate_salt()
        with open(SALT_FILE, "wb") as sf:
            sf.write(salt)

        encryption_key = derive_key(password, salt)

        # Store a check value
        check_value = "password_correct"
        encrypted_check = encrypt_data(check_value, encryption_key)
        if not encrypted_check: # Handle case where encryption fails (e.g. bad key derivation, though unlikely here)
            messagebox.showerror("Setup Error", "Failed to encrypt password check value. Setup cannot continue.")
            # Clean up potentially created salt file if setup fails critically after its creation
            if os.path.exists(SALT_FILE):
                try:
                    os.remove(SALT_FILE)
                except OSError as e_os:
                    print(f"Error removing salt file during cleanup: {e_os}")
            root.quit()
            return False

        with open(PASSWORD_CHECK_FILE, "w") as pcf:
            pcf.write(encrypted_check)
        messagebox.showinfo("Success", "Master password set and data file initialized.")
        return True
    else:
        # Existing user, ask for password
        with open(SALT_FILE, "rb") as sf:
            salt = sf.read()

        password = simpledialog.askstring("Login", "Enter your master password:", show='*')
        if not password:
            # User cancelled or entered empty password
            root.quit()
            return False

        encryption_key = derive_key(password, salt)

        try:
            with open(PASSWORD_CHECK_FILE, "r") as pcf:
                encrypted_check = pcf.read()
            decrypted_check = decrypt_data(encrypted_check, encryption_key)
            if decrypted_check == "password_correct":
                messagebox.showinfo("Login", "Password correct. Welcome!")
                return True
            else:
                messagebox.showerror("Login Failed", "Incorrect password. Exiting.")
                root.quit()
                return False
        except Exception as e:
            messagebox.showerror("Login Failed", f"Error during login: {e}. Incorrect password or corrupted files. Exiting.")
            root.quit()
            return False

# --- GUI Setup ---
root = tk.Tk()
root.title(APP_NAME)
root.geometry(GEOMETRY)

# --- Wallet Name and Purpose Frame ---
wallet_name_purpose_frame = ttk.Frame(root, padding="10")
wallet_name_purpose_frame.pack(fill=tk.X)

ttk.Label(wallet_name_purpose_frame, text="Wallet Name:").pack(side=tk.LEFT, padx=(0,5))
wallet_name_entry = ttk.Entry(wallet_name_purpose_frame, width=25) # Adjusted width
wallet_name_entry.pack(side=tk.LEFT, padx=(0,10))

load_wallet_button = ttk.Button(wallet_name_purpose_frame, text="Load/New Wallet") # Clarified text
load_wallet_button.pack(side=tk.LEFT, padx=(0,10))

ttk.Label(wallet_name_purpose_frame, text="Purpose/For:").pack(side=tk.LEFT, padx=(0,5))
mnemonic_purpose_entry = ttk.Entry(wallet_name_purpose_frame, width=25) # Adjusted width
mnemonic_purpose_entry.pack(side=tk.LEFT, padx=(0,5), expand=True, fill=tk.X)


# --- Mnemonic Phrases ---
mnemonic_frame = ttk.Frame(root, padding="10")
mnemonic_frame.pack(expand=True, fill=tk.BOTH)

mnemonic_entries_widgets = [] # Renamed from mnemonic_entries to avoid clash with data var

# Create two columns for mnemonic entries
column1_frame = ttk.Frame(mnemonic_frame)
column1_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10)

column2_frame = ttk.Frame(mnemonic_frame)
column2_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=10)

for i in range(24):
    parent_column = column1_frame if i < 12 else column2_frame
    entry_frame = ttk.Frame(parent_column)
    entry_frame.pack(fill=tk.X, pady=2)

    ttk.Label(entry_frame, text=f"{i+1}.", width=3).pack(side=tk.LEFT)
    entry = ttk.Entry(entry_frame, width=20)
    entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
    mnemonic_entries_widgets.append(entry)

# --- Navigation and Actions ---
controls_frame = ttk.Frame(root, padding="10")
controls_frame.pack(fill=tk.X)

prev_button = ttk.Button(controls_frame, text="< Prev Entry")
prev_button.pack(side=tk.LEFT, padx=10)

new_entry_button = ttk.Button(controls_frame, text="New/Clear Entry")
new_entry_button.pack(side=tk.LEFT, padx=5)

save_entry_button = ttk.Button(controls_frame, text="Save Entry")
save_entry_button.pack(side=tk.LEFT, padx=5)

copy_mnemonic_button = ttk.Button(controls_frame, text="Copy Mnemonic")
copy_mnemonic_button.pack(side=tk.LEFT, padx=5)

delete_entry_button = ttk.Button(controls_frame, text="Delete Entry")
delete_entry_button.pack(side=tk.RIGHT, padx=10)

next_button = ttk.Button(controls_frame, text="Next Entry >")
next_button.pack(side=tk.RIGHT, padx=5)

status_bar = ttk.Label(root, text="Status: Ready. Enter wallet name and Load/New or type details.", relief=tk.SUNKEN, anchor=tk.W, padding="2 5")
status_bar.pack(side=tk.BOTTOM, fill=tk.X)


# --- Functions (to be implemented/completed) ---

def handle_paste(event, start_index_in_grid): # start_index_in_grid is the focused entry index (0-23)
    # Check if any mnemonic field already has content - only allow paste to fully empty set
    if any(entry_widget.get().strip() for entry_widget in mnemonic_entries_widgets):
        messagebox.showwarning("Paste Blocked", "Clear all mnemonic words before pasting. Use 'New/Clear Entry' then paste into the first word field.")
        return "break"
    try:
        clipboard_content = root.clipboard_get()
        words = clipboard_content.split()
        
        # Paste only if the focused entry is the first one (index 0)
        if start_index_in_grid != 0:
            messagebox.showwarning("Paste Info", "Please click on the first (1.) word field to paste the entire mnemonic.")
            return "break"

        for i, word in enumerate(words):
            target_index = i # Paste from the beginning
            if target_index < 24:
                mnemonic_entries_widgets[target_index].delete(0, tk.END)
                mnemonic_entries_widgets[target_index].insert(0, word)
            else:
                break 
        if words:
            if len(words) < 24:
                 mnemonic_entries_widgets[len(words)].focus_set()
            else:
                 mnemonic_entries_widgets[23].focus_set()
            return "break" 
    except tk.TclError:
        pass # Clipboard empty or not text
    except Exception as e:
        print(f"Error during paste: {e}")
        messagebox.showerror("Paste Error", f"Could not process pasted text: {e}")


# Bind paste event to mnemonic entries
for idx, entry_widget in enumerate(mnemonic_entries_widgets):
    # We use a lambda with a default argument for idx to capture its current value
    entry_widget.bind("<<Paste>>", lambda e, i=idx: handle_paste(e, i))


def load_group_details():
    global current_wallet_id, current_mnemonic_entries_in_wallet, current_mnemonic_entry_idx, current_wallet_name_displayed
    
    wallet_name = wallet_name_entry.get().strip()
    if not wallet_name:
        messagebox.showwarning("Input Error", "Wallet Name cannot be empty.")
        return

    current_wallet_name_displayed = wallet_name # Set this regardless of DB existence for saving new
    current_mnemonic_entries_in_wallet.clear()
    current_mnemonic_entry_idx = -1
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT wallet_id FROM wallets WHERE wallet_name = ?", (wallet_name,))
    group_row = cursor.fetchone()

    if group_row:
        current_wallet_id = group_row[0]
        cursor.execute("SELECT entry_id, purpose, encrypted_mnemonic FROM mnemonic_entries WHERE wallet_id = ? ORDER BY purpose ASC", (current_wallet_id,))
        entry_rows = cursor.fetchall()
        for row in entry_rows:
            current_mnemonic_entries_in_wallet.append({'entry_id': row[0], 'purpose': row[1], 'encrypted_mnemonic': row[2]})
        
        if current_mnemonic_entries_in_wallet:
            display_mnemonic_entry(0) # Display first entry
            status_bar.config(text=f"Status: Loaded wallet '{wallet_name}' with {len(current_mnemonic_entries_in_wallet)} entries.")
        else:
            clear_fields(clear_wallet_name=False) # Keep wallet name, clear others
            status_bar.config(text=f"Status: Wallet '{wallet_name}' is empty. Ready for new entry.")
    else:
        current_wallet_id = None # Indicate wallet doesn't exist in DB yet
        clear_fields(clear_wallet_name=False) # Keep new wallet name, clear others
        status_bar.config(text=f"Status: New wallet '{wallet_name}'. Ready for first entry.")
    
    conn.close()
    update_navigation_buttons_state()
    mnemonic_purpose_entry.focus_set()


def display_mnemonic_entry(entry_idx_to_display):
    global current_mnemonic_entry_idx, current_mnemonic_entries_in_wallet, current_wallet_name_displayed

    if not current_mnemonic_entries_in_wallet or not (0 <= entry_idx_to_display < len(current_mnemonic_entries_in_wallet)):
        clear_fields(clear_wallet_name=False) # Keep wallet name
        status_bar.config(text=f"Status: No entry to display in wallet '{current_wallet_name_displayed}'. Ready for new entry.")
        current_mnemonic_entry_idx = -1
        update_navigation_buttons_state()
        return

    current_mnemonic_entry_idx = entry_idx_to_display
    entry_data = current_mnemonic_entries_in_wallet[current_mnemonic_entry_idx]

    wallet_name_entry.delete(0, tk.END)
    wallet_name_entry.insert(0, current_wallet_name_displayed) # Ensure wallet name is displayed
    mnemonic_purpose_entry.delete(0, tk.END)
    mnemonic_purpose_entry.insert(0, entry_data['purpose'])

    decrypted_mnemonic = decrypt_data(entry_data['encrypted_mnemonic'], encryption_key)
    clear_fields(clear_wallet_name=False, clear_purpose=False, clear_mnemonics=True) # Clear only mnemonics before filling

    if decrypted_mnemonic:
        words = decrypted_mnemonic.split()
        for i, entry_widget in enumerate(mnemonic_entries_widgets):
            if i < len(words):
                entry_widget.insert(0, words[i])
            else: # Should not happen if data is consistent
                entry_widget.delete(0, tk.END)
    else:
        messagebox.showerror("Decryption Error", f"Could not decrypt mnemonic for purpose '{entry_data['purpose']}'.")
        # Mnemonic fields already cleared

    status_bar.config(text=f"Status: Displaying entry {current_mnemonic_entry_idx + 1} of {len(current_mnemonic_entries_in_wallet)} ('{entry_data['purpose']}') in wallet '{current_wallet_name_displayed}'.")
    update_navigation_buttons_state()

def clear_fields(clear_wallet_name=False, clear_purpose=True, clear_mnemonics=True):
    """Clears specified fields."""
    if clear_wallet_name:
        wallet_name_entry.delete(0, tk.END)
    if clear_purpose:
        mnemonic_purpose_entry.delete(0, tk.END)
    if clear_mnemonics:
        for entry_widget in mnemonic_entries_widgets:
            entry_widget.delete(0, tk.END)
    if clear_purpose and clear_mnemonics: # Common case for new entry
        mnemonic_purpose_entry.focus_set()

def new_mnemonic_entry_action():
    global current_mnemonic_entry_idx
    # Assumes a wallet context is set (current_wallet_name_displayed is populated)
    # If not, user should use "Load/New Wallet" first or just type in the wallet name
    if not wallet_name_entry.get().strip():
        messagebox.showwarning("Wallet Needed", "Please enter or load a Wallet Name first.")
        wallet_name_entry.focus_set()
        return

    clear_fields(clear_wallet_name=False, clear_purpose=True, clear_mnemonics=True)
    current_mnemonic_entry_idx = -1 # Indicates a new, unsaved entry
    status_bar.config(text=f"Status: Ready for new entry in wallet '{wallet_name_entry.get().strip()}'.")
    update_navigation_buttons_state()
    mnemonic_purpose_entry.focus_set()

def save_mnemonic_entry():
    global encryption_key, current_wallet_id, current_wallet_name_displayed, current_mnemonic_entry_idx

    if not encryption_key:
        messagebox.showerror("Error", "Encryption not initialized.")
        return

    wallet_name_from_field = wallet_name_entry.get().strip()
    purpose = mnemonic_purpose_entry.get().strip()

    if not wallet_name_from_field:
        messagebox.showwarning("Input Error", "Wallet Name cannot be empty.")
        wallet_name_entry.focus_set()
        return
    if not purpose:
        messagebox.showwarning("Input Error", "Purpose/For cannot be empty.")
        mnemonic_purpose_entry.focus_set()
        return

    mnemonic_words_from_entries = [entry.get().strip() for entry in mnemonic_entries_widgets]
    mnemonic_phrase_to_save = None
    is_24_words = all(mnemonic_words_from_entries[i] for i in range(24))
    if is_24_words:
        mnemonic_phrase_to_save = " ".join(mnemonic_words_from_entries)
    else:
        first_12_filled = all(mnemonic_words_from_entries[i] for i in range(12))
        last_12_empty = all(not mnemonic_words_from_entries[i] for i in range(12, 24))
        if first_12_filled and last_12_empty:
            mnemonic_phrase_to_save = " ".join(mnemonic_words_from_entries[:12])
        else:
            messagebox.showwarning("Input Error", "Mnemonic must be 12 (first 12 fields, rest empty) or 24 words.")
            return

    encrypted_mnemonic = encrypt_data(mnemonic_phrase_to_save, encryption_key)
    if not encrypted_mnemonic:
        messagebox.showerror("Encryption Error", "Failed to encrypt mnemonic. Entry not saved.")
        return

    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        # Ensure current_wallet_name_displayed is up-to-date with the entry field
        current_wallet_name_displayed = wallet_name_from_field
        
        # Get or create wallet_id
        cursor.execute("SELECT wallet_id FROM wallets WHERE wallet_name = ?", (current_wallet_name_displayed,))
        group_row = cursor.fetchone()
        if group_row:
            current_wallet_id = group_row[0]
        else:
            cursor.execute("INSERT INTO wallets (wallet_name) VALUES (?)", (current_wallet_name_displayed,))
            current_wallet_id = cursor.lastrowid
            status_bar.config(text=f"Status: Created new wallet '{current_wallet_name_displayed}'.")
        
        # Check if purpose already exists for this wallet_id
        cursor.execute("SELECT entry_id FROM mnemonic_entries WHERE wallet_id = ? AND purpose = ?", (current_wallet_id, purpose))
        existing_entry_row = cursor.fetchone()

        if existing_entry_row: # Update existing entry
            entry_id_to_update = existing_entry_row[0]
            if messagebox.askyesno("Confirm Overwrite", f"Entry with purpose '{purpose}' in wallet '{current_wallet_name_displayed}' already exists. Overwrite?"):
                cursor.execute("UPDATE mnemonic_entries SET encrypted_mnemonic = ? WHERE entry_id = ?", (encrypted_mnemonic, entry_id_to_update))
                conn.commit()
                status_bar.config(text=f"Status: Entry '{purpose}' updated in wallet '{current_wallet_name_displayed}'.")
            else:
                status_bar.config(text="Status: Save cancelled by user.")
                conn.close()
                return
        else: # Insert new entry
            cursor.execute("INSERT INTO mnemonic_entries (wallet_id, purpose, encrypted_mnemonic) VALUES (?, ?, ?)",
                           (current_wallet_id, purpose, encrypted_mnemonic))
            conn.commit()
            status_bar.config(text=f"Status: Entry '{purpose}' saved in wallet '{current_wallet_name_displayed}'.")
        
        conn.close()
        # Reload wallet to refresh list and display the potentially new/updated entry correctly
        # Store current purpose to try and re-select it after load
        purpose_to_reselect = purpose
        load_group_details() # This will clear current_mnemonic_entry_idx

        # Attempt to find and display the saved/updated entry
        if current_mnemonic_entries_in_wallet:
            found_idx = -1
            for idx, entry in enumerate(current_mnemonic_entries_in_wallet):
                if entry['purpose'] == purpose_to_reselect:
                    found_idx = idx
                    break
            if found_idx != -1:
                display_mnemonic_entry(found_idx)
            elif current_mnemonic_entries_in_wallet: # Default to first if specific not found (should not happen)
                 display_mnemonic_entry(0)


    except sqlite3.Error as e:
        messagebox.showerror("Database Error", f"Could not save entry: {e}")
        status_bar.config(text="Status: Error saving entry.")
    except Exception as e:
        messagebox.showerror("Save Error", f"An unexpected error occurred: {e}")
        status_bar.config(text="Status: Error saving entry.")
    update_navigation_buttons_state()

def next_mnemonic_entry():
    global current_mnemonic_entry_idx, current_mnemonic_entries_in_wallet
    if current_mnemonic_entries_in_wallet and current_mnemonic_entry_idx < len(current_mnemonic_entries_in_wallet) - 1:
        display_mnemonic_entry(current_mnemonic_entry_idx + 1)
    elif current_mnemonic_entries_in_wallet: # Wrap around
        display_mnemonic_entry(0)

def prev_mnemonic_entry():
    global current_mnemonic_entry_idx, current_mnemonic_entries_in_wallet
    if current_mnemonic_entries_in_wallet and current_mnemonic_entry_idx > 0:
        display_mnemonic_entry(current_mnemonic_entry_idx - 1)
    elif current_mnemonic_entries_in_wallet: # Wrap around
        display_mnemonic_entry(len(current_mnemonic_entries_in_wallet) - 1)

def delete_current_mnemonic_entry():
    global current_mnemonic_entry_idx, current_mnemonic_entries_in_wallet, current_wallet_id

    if current_wallet_id is None or current_mnemonic_entry_idx == -1 or not current_mnemonic_entries_in_wallet:
        messagebox.showinfo("Info", "No entry selected to delete.")
        return

    entry_to_delete = current_mnemonic_entries_in_wallet[current_mnemonic_entry_idx]
    entry_id_db = entry_to_delete['entry_id']
    purpose_deleted = entry_to_delete['purpose']

    if messagebox.askyesno("Confirm Delete", f"Delete entry '{purpose_deleted}' from wallet '{current_wallet_name_displayed}'? This cannot be undone."):
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM mnemonic_entries WHERE entry_id = ?", (entry_id_db,))
            conn.commit()
            # Check if wallet is now empty, if so, optionally delete wallet
            cursor.execute("SELECT COUNT(*) FROM mnemonic_entries WHERE wallet_id = ?", (current_wallet_id,))
            count = cursor.fetchone()[0]
            if count == 0:
                if messagebox.askyesno("Empty Wallet", f"Wallet '{current_wallet_name_displayed}' is now empty. Delete the wallet as well?"):
                    cursor.execute("DELETE FROM wallets WHERE wallet_id = ?", (current_wallet_id,))
                    conn.commit()
                    status_bar.config(text=f"Status: Entry '{purpose_deleted}' and empty wallet '{current_wallet_name_displayed}' deleted.")
                    clear_fields(clear_wallet_name=True, clear_purpose=True, clear_mnemonics=True)
                    wallet_name_entry.focus_set()
                    current_wallet_id = None
                    current_wallet_name_displayed = ""
                    current_mnemonic_entries_in_wallet.clear()
                    current_mnemonic_entry_idx = -1
                else:
                    status_bar.config(text=f"Status: Entry '{purpose_deleted}' deleted. Wallet '{current_wallet_name_displayed}' is now empty.")
            else:
                 status_bar.config(text=f"Status: Entry '{purpose_deleted}' deleted from wallet '{current_wallet_name_displayed}'.")
            conn.close()
            
            if current_wallet_id is not None: # If wallet was not deleted
                load_group_details() # Refresh, will display next/first or clear if wallet became empty but not deleted
            else: # Wallet was deleted
                update_navigation_buttons_state()


        except sqlite3.Error as e:
            messagebox.showerror("Database Error", f"Could not delete entry: {e}")
        except Exception as e:
            messagebox.showerror("Delete Error", f"An unexpected error occurred: {e}")
            load_group_details() # Try to recover state
    update_navigation_buttons_state()


def copy_all_mnemonic():
    global current_mnemonic_entry_idx, current_mnemonic_entries_in_wallet, encryption_key, current_wallet_name_displayed

    if current_mnemonic_entry_idx == -1 or not current_mnemonic_entries_in_wallet:
        messagebox.showinfo("Copy Mnemonic", "No mnemonic entry is currently displayed to copy.")
        return

    entry_data = current_mnemonic_entries_in_wallet[current_mnemonic_entry_idx]
    decrypted_mnemonic = decrypt_data(entry_data['encrypted_mnemonic'], encryption_key)

    if decrypted_mnemonic:
        try:
            root.clipboard_clear()
            root.clipboard_append(decrypted_mnemonic)
            status_bar.config(text=f"Status: Mnemonic for '{entry_data['purpose']}' in '{current_wallet_name_displayed}' copied.")
            messagebox.showinfo("Copied", f"Mnemonic for '{entry_data['purpose']}' copied.")
        except tk.TclError:
            messagebox.showerror("Clipboard Error", "Could not access clipboard.")
        except Exception as e:
            messagebox.showerror("Copy Error", f"An unexpected error occurred: {e}")
    else:
        messagebox.showerror("Decryption Error", "Could not decrypt mnemonic to copy.")

def update_navigation_buttons_state():
    num_entries_in_group = len(current_mnemonic_entries_in_wallet)
    group_name_present = bool(wallet_name_entry.get().strip())

    # Prev/Next buttons
    if num_entries_in_group > 1:
        prev_button.config(state=tk.NORMAL)
        next_button.config(state=tk.NORMAL)
    else:
        prev_button.config(state=tk.DISABLED)
        next_button.config(state=tk.DISABLED)

    # Copy and Delete buttons: require a specific entry to be selected from DB
    if current_mnemonic_entry_idx != -1 and num_entries_in_group > 0 and current_mnemonic_entries_in_wallet[current_mnemonic_entry_idx].get('entry_id') is not None:
        copy_mnemonic_button.config(state=tk.NORMAL)
        delete_entry_button.config(state=tk.NORMAL)
    else:
        copy_mnemonic_button.config(state=tk.DISABLED)
        delete_entry_button.config(state=tk.DISABLED)

    # New/Clear Entry button: enabled if a wallet name is present (either loaded or typed for new)
    new_entry_button.config(state=tk.NORMAL if group_name_present else tk.DISABLED)
    
    # Save Entry button: always enabled, as it can save to new/existing wallet/entry
    save_entry_button.config(state=tk.NORMAL)
    
    # Load Wallet button: always enabled
    load_wallet_button.config(state=tk.NORMAL)


# --- Button Commands ---
load_wallet_button.config(command=load_group_details)
new_entry_button.config(command=new_mnemonic_entry_action)
save_entry_button.config(command=save_mnemonic_entry)
prev_button.config(command=prev_mnemonic_entry)
next_button.config(command=next_mnemonic_entry)
delete_entry_button.config(command=delete_current_mnemonic_entry)
copy_mnemonic_button.config(command=copy_all_mnemonic)


# --- Application Start ---
if __name__ == "__main__":
    if setup_password():
        if not init_db():
            messagebox.showerror("Critical Error", "Failed to initialize database. Application cannot continue.")
            root.quit()
        else:
            # Initial state: No wallet loaded, ready for user input
            clear_fields(clear_wallet_name=True, clear_purpose=True, clear_mnemonics=True)
            status_bar.config(text="Status: Ready. Enter wallet name and Load/New, or type details for a new entry.")
            wallet_name_entry.focus_set()
            update_navigation_buttons_state() # Set initial button states
            root.mainloop()
    else:
        print("Exiting application due to password setup/login failure.")
