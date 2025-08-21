import tkinter as tk
from tkinter import ttk, simpledialog, messagebox, filedialog, font
import sqlite3
import csv
import os
from datetime import datetime

DB_FILE = '.\\db\\counters.db'

class DBManager:
    def __init__(self, db_file):
        # Ensure directory exists
        os.makedirs(os.path.dirname(db_file), exist_ok=True)
        self.conn = sqlite3.connect(db_file)
        self._create_tables()

    def _create_tables(self):
        c = self.conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS groups (
                id INTEGER PRIMARY KEY,
                name TEXT UNIQUE
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS counters (
                id INTEGER PRIMARY KEY,
                name TEXT,
                group_id INTEGER,
                amount INTEGER DEFAULT 0,
                last_hour TEXT,
                last_day TEXT,
                last_week TEXT,
                last_month TEXT,
                last_year TEXT,
                count_in_current_hour INTEGER DEFAULT 0,
                count_in_current_day INTEGER DEFAULT 0,
                count_in_current_week INTEGER DEFAULT 0,
                count_in_current_month INTEGER DEFAULT 0,
                count_in_current_year INTEGER DEFAULT 0,
                FOREIGN KEY(group_id) REFERENCES groups(id)
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY,
                counter_id INTEGER,
                interval_type TEXT,
                period TEXT,
                count INTEGER,
                FOREIGN KEY(counter_id) REFERENCES counters(id)
            )
        ''')
        self.conn.commit()

    def add_group(self, name):
        c = self.conn.cursor()
        c.execute("INSERT OR IGNORE INTO groups (name) VALUES (?)", (name,))
        self.conn.commit()

    def get_groups(self):
        c = self.conn.cursor()
        c.execute("SELECT id, name FROM groups")
        return c.fetchall()

    def add_counter(self, name, group_id, initial_amount=0):
        c = self.conn.cursor()
        now = datetime.now()
        periods = self._get_periods(now)
        c.execute(
            "INSERT INTO counters (name, group_id, amount, last_hour, last_day, last_week, last_month, last_year, count_in_current_hour, count_in_current_day, count_in_current_week, count_in_current_month, count_in_current_year) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (name, group_id, initial_amount, periods['hourly'], periods['daily'], periods['weekly'], periods['monthly'], periods['yearly'], 0,0,0,0,0)
        )
        self.conn.commit()

    def counter_exists(self, name, group_id):
        c = self.conn.cursor()
        c.execute("SELECT 1 FROM counters WHERE name = ? AND group_id = ?", (name, group_id))
        return c.fetchone() is not None

    def get_counters(self, group_id=None):
        c = self.conn.cursor()
        if group_id:
            c.execute("SELECT id, name, amount FROM counters WHERE group_id = ?", (group_id,))
        else:
            c.execute("SELECT id, name, amount FROM counters")
        return c.fetchall()

    def update_counter(self, counter_id, change):
        c = self.conn.cursor()
        # Update total amount
        c.execute("UPDATE counters SET amount = amount + ? WHERE id = ?", (change, counter_id))

        now = datetime.now()
        current_periods_strings_map = self._get_periods(now)

        # Fetch the counter's current state for all periods and current counts
        c.execute(
            "SELECT last_hour, last_day, last_week, last_month, last_year, "
            "count_in_current_hour, count_in_current_day, count_in_current_week, "
            "count_in_current_month, count_in_current_year "
            "FROM counters WHERE id = ?",
            (counter_id,)
        )
        row = c.fetchone()
        if not row:
            print(f"Warning: No counter found with id {counter_id} when trying to update periods.")
            self.conn.commit()
            return

        db_last_periods = row[0:5]
        db_counts_in_current_periods = list(row[5:10])

        interval_mappings = [
            ('hourly',  'hour',  0, 0),
            ('daily',   'day',   1, 1),
            ('weekly',  'week',  2, 2),
            ('monthly', 'month', 3, 3),
            ('yearly',  'year',  4, 4)
        ]

        for interval_key, db_col_suffix, period_idx, count_idx in interval_mappings:
            last_recorded_period_str = db_last_periods[period_idx]
            current_calculated_period_str = current_periods_strings_map[interval_key]
            count_for_this_interval_type = db_counts_in_current_periods[count_idx]

            if current_calculated_period_str != last_recorded_period_str:
                if last_recorded_period_str is not None and count_for_this_interval_type > 0:
                    c.execute(
                        "INSERT INTO history (counter_id, interval_type, period, count) VALUES (?,?,?,?)",
                        (counter_id, interval_key, last_recorded_period_str, count_for_this_interval_type)
                    )
                
                sql_update_last_period_column = f"last_{db_col_suffix}"
                c.execute(
                    f"UPDATE counters SET {sql_update_last_period_column}=? WHERE id=?",
                    (current_calculated_period_str, counter_id)
                )
                
                new_count_for_new_period = change
                sql_update_current_count_column = f"count_in_current_{db_col_suffix}"
                c.execute(
                    f"UPDATE counters SET {sql_update_current_count_column}=? WHERE id=?",
                    (new_count_for_new_period, counter_id)
                )
            else:
                updated_count_for_ongoing_period = count_for_this_interval_type + change
                sql_update_current_count_column = f"count_in_current_{db_col_suffix}"
                c.execute(
                    f"UPDATE counters SET {sql_update_current_count_column}=? WHERE id=?",
                    (updated_count_for_ongoing_period, counter_id)
                )
        
        self.conn.commit()

    def _get_periods(self, dt):
        return {
            'hourly': dt.strftime('%H %d/%m/%Y'),
            'daily': dt.strftime('%d/%m/%Y'),
            'weekly': dt.strftime('%V/%Y'),
            'monthly': dt.strftime('%m/%Y'),
            'yearly': dt.strftime('%Y')
        }

    def get_history(self):
        c = self.conn.cursor()
        c.execute(
            "SELECT h.id, c.name, h.interval_type, h.period, h.count "
            "FROM history h JOIN counters c ON h.counter_id = c.id ORDER BY h.id DESC"
        )
        return c.fetchall()

    def add_imported_counter_with_history(self, name, group_id, timestamps: list[datetime]):
        if not timestamps:
            return None

        c = self.conn.cursor()
        latest_ts = max(timestamps) if timestamps else datetime.now()
        periods_for_latest = self._get_periods(latest_ts)

        aggregated_period_counts = {
            'hourly': {}, 'daily': {}, 'weekly': {}, 'monthly': {}, 'yearly': {}
        }

        for ts in timestamps:
            ts_all_periods = self._get_periods(ts)
            for interval_key in aggregated_period_counts.keys():
                period_str = ts_all_periods[interval_key]
                aggregated_period_counts[interval_key][period_str] = \
                    aggregated_period_counts[interval_key].get(period_str, 0) + 1
        
        current_hourly_count = aggregated_period_counts['hourly'].get(periods_for_latest['hourly'], 0)
        current_daily_count = aggregated_period_counts['daily'].get(periods_for_latest['daily'], 0)
        current_weekly_count = aggregated_period_counts['weekly'].get(periods_for_latest['weekly'], 0)
        current_monthly_count = aggregated_period_counts['monthly'].get(periods_for_latest['monthly'], 0)
        current_yearly_count = aggregated_period_counts['yearly'].get(periods_for_latest['yearly'], 0)

        c.execute(
            "INSERT INTO counters (name, group_id, amount, last_hour, last_day, last_week, last_month, last_year, count_in_current_hour, count_in_current_day, count_in_current_week, count_in_current_month, count_in_current_year) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (name, group_id, len(timestamps),
             periods_for_latest['hourly'], periods_for_latest['daily'],
             periods_for_latest['weekly'], periods_for_latest['monthly'],
             periods_for_latest['yearly'],
             current_hourly_count, current_daily_count, current_weekly_count,
             current_monthly_count, current_yearly_count)
        )
        counter_id = c.lastrowid

        for interval_type, periods_map in aggregated_period_counts.items():
            for period_str, count_in_period in periods_map.items():
                if count_in_period > 0: 
                    c.execute(
                        "INSERT INTO history (counter_id, interval_type, period, count) VALUES (?,?,?,?)",
                        (counter_id, interval_type, period_str, count_in_period)
                    )
        
        self.conn.commit()
        return counter_id

    def get_counter_id_by_name_group(self, name, group_id):
        c = self.conn.cursor()
        c.execute("SELECT id FROM counters WHERE name = ? AND group_id = ?", (name, group_id))
        result = c.fetchone()
        return result[0] if result else None

    def delete_counter_completely(self, counter_id):
        c = self.conn.cursor()
        c.execute("DELETE FROM history WHERE counter_id = ?", (counter_id,))
        c.execute("DELETE FROM counters WHERE id = ?", (counter_id,))
        self.conn.commit()

    def export_to_csv(self, filename):
        """Export all data to CSV"""
        c = self.conn.cursor()
        c.execute("""
            SELECT g.name as group_name, c.name as counter_name, c.amount,
                   h.interval_type, h.period, h.count
            FROM groups g
            JOIN counters c ON g.id = c.group_id
            LEFT JOIN history h ON c.id = h.counter_id
            ORDER BY g.name, c.name, h.id
        """)
        
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['Group', 'Counter', 'Total Count', 'Interval Type', 'Period', 'Period Count'])
            writer.writerows(c.fetchall())

class CustomDialog(tk.Toplevel):
    """Base class for custom dialogs"""
    def __init__(self, parent, title, width=400, height=300):
        super().__init__(parent)
        self.title(title)
        self.geometry(f"{width}x{height}")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        
        # Center the dialog
        self.geometry(f"+{parent.winfo_rootx() + 50}+{parent.winfo_rooty() + 50}")
        
        self.result = None
        self.create_widgets()
        
    def create_widgets(self):
        """Override in subclasses"""
        pass

class FormatDialog(CustomDialog):
    def __init__(self, parent, title, formats):
        self.formats = formats
        super().__init__(parent, title, 450, 250)

    def create_widgets(self):
        # Main frame
        main_frame = ttk.Frame(self, padding="20")
        main_frame.pack(fill='both', expand=True)
        
        # Title
        title_label = ttk.Label(main_frame, text="Select timestamp format:", 
                               font=('Segoe UI', 10, 'bold'))
        title_label.pack(anchor='w', pady=(0, 15))
        
        # Format selection
        self.format_var = tk.StringVar()
        if self.formats:
            self.format_var.set(self.formats[0])
        
        for fmt in self.formats:
            rb = ttk.Radiobutton(main_frame, text=fmt, variable=self.format_var, value=fmt)
            rb.pack(anchor='w', pady=2, padx=20)
        
        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill='x', pady=(20, 0))
        
        ttk.Button(button_frame, text="Cancel", command=self.destroy).pack(side='right', padx=(5, 0))
        ttk.Button(button_frame, text="OK", command=self.ok_clicked).pack(side='right')
    
    def ok_clicked(self):
        self.result = self.format_var.get()
        self.destroy()

class InputDialog(CustomDialog):
    def __init__(self, parent, title, prompt, multiline=False):
        self.prompt = prompt
        self.multiline = multiline
        height = 200 if not multiline else 350
        super().__init__(parent, title, 400, height)

    def create_widgets(self):
        main_frame = ttk.Frame(self, padding="20")
        main_frame.pack(fill='both', expand=True)
        
        # Prompt
        ttk.Label(main_frame, text=self.prompt, font=('Segoe UI', 10)).pack(anchor='w', pady=(0, 10))
        
        # Input
        if self.multiline:
            self.text_widget = tk.Text(main_frame, height=8, width=40, font=('Segoe UI', 9))
            scrollbar = ttk.Scrollbar(main_frame, orient='vertical', command=self.text_widget.yview)
            self.text_widget.configure(yscrollcommand=scrollbar.set)
            
            text_frame = ttk.Frame(main_frame)
            text_frame.pack(fill='both', expand=True, pady=(0, 15))
            
            self.text_widget.pack(side='left', fill='both', expand=True)
            scrollbar.pack(side='right', fill='y')
        else:
            self.entry = ttk.Entry(main_frame, font=('Segoe UI', 10))
            self.entry.pack(fill='x', pady=(0, 15))
            self.entry.focus()
        
        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill='x')
        
        ttk.Button(button_frame, text="Cancel", command=self.destroy).pack(side='right', padx=(5, 0))
        ttk.Button(button_frame, text="OK", command=self.ok_clicked).pack(side='right')
        
        # Bind Enter key
        if not self.multiline:
            self.entry.bind('<Return>', lambda e: self.ok_clicked())
    
    def ok_clicked(self):
        if self.multiline:
            self.result = self.text_widget.get('1.0', 'end-1c')
        else:
            self.result = self.entry.get()
        self.destroy()

class TallyApp(tk.Tk):
    def __init__(self, db):
        super().__init__()
        self.title("Professional Tally Counter")
        self.geometry("1000x700")
        self.minsize(800, 600)
        self.db = db
        self.selected_group = None
        
        # Configure style
        self.setup_styles()
        
        # Create menu bar
        self.create_menu()
        
        # Create main interface
        self.create_widgets()
        
        # Create status bar
        self.create_status_bar()
        
        # Load initial data
        self.load_groups()
        
        # Bind keyboard shortcuts
        self.bind_shortcuts()

    def setup_styles(self):
        """Configure modern styling"""
        style = ttk.Style()
        
        # Configure colors
        self.colors = {
            'primary': '#2E86AB',
            'secondary': '#A23B72',
            'success': '#F18F01',
            'background': '#F8F9FA',
            'surface': '#FFFFFF',
            'text': '#212529',
            'text_secondary': '#6C757D'
        }
        
        # Configure treeview
        style.configure("Custom.Treeview", 
                       background=self.colors['surface'],
                       foreground=self.colors['text'],
                       rowheight=30,
                       fieldbackground=self.colors['surface'])
        
        style.configure("Custom.Treeview.Heading",
                       background=self.colors['primary'],
                       foreground='white',
                       font=('Segoe UI', 10, 'bold'))
        
        # Configure buttons
        style.configure("Action.TButton",
                       font=('Segoe UI', 9, 'bold'))

    def create_menu(self):
        """Create professional menu bar"""
        menubar = tk.Menu(self)
        self.config(menu=menubar)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="New Group", command=self.new_group, accelerator="Ctrl+G")
        file_menu.add_command(label="New Counter", command=self.new_counter, accelerator="Ctrl+N")
        file_menu.add_separator()
        file_menu.add_command(label="Import CSV...", command=self.import_counters, accelerator="Ctrl+I")
        file_menu.add_command(label="Export CSV...", command=self.export_data, accelerator="Ctrl+E")
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.quit, accelerator="Ctrl+Q")
        
        # Edit menu
        edit_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Edit", menu=edit_menu)
        edit_menu.add_command(label="Quick Add Counters", command=self.quick_add_counters, accelerator="Ctrl+Shift+N")
        edit_menu.add_separator()
        edit_menu.add_command(label="Delete Counter", command=self.delete_counter, accelerator="Delete")
        
        # View menu
        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="View", menu=view_menu)
        view_menu.add_command(label="Refresh", command=self.refresh_data, accelerator="F5")
        
        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=self.show_about)

    def create_widgets(self):
        """Create the main interface"""
        # Main container with padding
        main_container = ttk.Frame(self, padding="10")
        main_container.pack(fill='both', expand=True)
        
        # Header section
        self.create_header(main_container)
        
        # Content area with paned window
        content_paned = ttk.PanedWindow(main_container, orient='vertical')
        content_paned.pack(fill='both', expand=True, pady=(10, 0))
        
        # Counters section
        counters_frame = self.create_counters_section(content_paned)
        assert counters_frame is not None, "create_counters_section returned None!"
        content_paned.add(counters_frame, weight=3)
        
        # History section
        history_frame = self.create_history_section(content_paned)
        assert history_frame is not None, "create_history_section returned None!"
        content_paned.add(history_frame, weight=2)

    def create_header(self, parent):
        """Create header with toolbar and group selection"""
        header_frame = ttk.Frame(parent)
        header_frame.pack(fill='x', pady=(0, 10))
        
        # Title
        title_label = ttk.Label(header_frame, text="Tally Counter", 
                               font=('Segoe UI', 16, 'bold'),
                               foreground=self.colors['primary'])
        title_label.pack(side='left')
        
        # Toolbar
        toolbar_frame = ttk.Frame(header_frame)
        toolbar_frame.pack(side='right')
        
        # Group selection
        ttk.Label(toolbar_frame, text="Group:", font=('Segoe UI', 10)).pack(side='left', padx=(0, 5))
        self.group_cb = ttk.Combobox(toolbar_frame, state='readonly', width=15, font=('Segoe UI', 9))
        self.group_cb.pack(side='left', padx=(0, 15))
        self.group_cb.bind('<<ComboboxSelected>>', lambda e: self.load_counters())
        
        # Action buttons
        ttk.Button(toolbar_frame, text="➕ New Group", command=self.new_group,
                  style="Action.TButton").pack(side='left', padx=2)
        ttk.Button(toolbar_frame, text="📊 New Counter", command=self.new_counter,
                  style="Action.TButton").pack(side='left', padx=2)
        ttk.Button(toolbar_frame, text="⚡ Quick Add", command=self.quick_add_counters,
                  style="Action.TButton").pack(side='left', padx=2)
        ttk.Button(toolbar_frame, text="📁 Import", command=self.import_counters,
                  style="Action.TButton").pack(side='left', padx=2)

    def create_counters_section(self, parent):
        """Create counters display section"""
        # Main frame
        counters_frame = ttk.LabelFrame(parent, text="Counters", padding="10")
        
        # Search frame
        search_frame = ttk.Frame(counters_frame)
        search_frame.pack(fill='x', pady=(0, 10))
        
        ttk.Label(search_frame, text="Search:", font=('Segoe UI', 9)).pack(side='left')
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=20)
        self.search_entry.pack(side='left', padx=(5, 10))
        self.search_var.trace('w', self.filter_counters)
        
        ttk.Button(search_frame, text="🗑️ Delete Selected", 
                  command=self.delete_counter).pack(side='right')
        
        # Treeview container
        tree_container = ttk.Frame(counters_frame)
        tree_container.pack(fill='both', expand=True)
        
        # Counters treeview
        columns = ('name', 'amount', 'actions')
        self.tree = ttk.Treeview(tree_container, columns=columns, show='headings', 
                                style="Custom.Treeview", height=12)
        
        # Configure columns
        self.tree.heading('name', text='Counter Name')
        self.tree.heading('amount', text='Count')
        self.tree.heading('actions', text='Actions')
        
        self.tree.column('name', width=300, anchor='w')
        self.tree.column('amount', width=100, anchor='e')  # sağa hizala
        self.tree.column('actions', width=150, anchor='center')
        
        # Scrollbars
        v_scrollbar = ttk.Scrollbar(tree_container, orient='vertical', command=self.tree.yview)
        h_scrollbar = ttk.Scrollbar(tree_container, orient='horizontal', command=self.tree.xview)
        self.tree.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        
        # Pack treeview and scrollbars
        self.tree.grid(row=0, column=0, sticky='nsew')
        v_scrollbar.grid(row=0, column=1, sticky='ns')
        h_scrollbar.grid(row=1, column=0, sticky='ew')
        
        tree_container.grid_rowconfigure(0, weight=1)
        tree_container.grid_columnconfigure(0, weight=1)
        
        # Bind events
        self.tree.bind('<Button-1>', self.on_counter_single_click)
        self.tree.bind('<Button-3>', self.show_context_menu)
        
        # Action buttons frame
        action_frame = ttk.Frame(counters_frame)
        action_frame.pack(fill='x', pady=(10, 0))
        
        self.increment_btn = ttk.Button(action_frame, text="➕ Increment (+1)", 
                                       command=lambda: self.update_selected_counter(1),
                                       style="Action.TButton")
        self.increment_btn.pack(side='left', padx=(0, 5))
        
        self.decrement_btn = ttk.Button(action_frame, text="➖ Decrement (-1)", 
                                       command=lambda: self.update_selected_counter(-1),
                                       style="Action.TButton")
        self.decrement_btn.pack(side='left', padx=(0, 5))
        
        self.custom_btn = ttk.Button(action_frame, text="✏️ Custom Amount", 
                                    command=self.custom_update,
                                    style="Action.TButton")
        self.custom_btn.pack(side='left')
        
        return counters_frame
    
    def create_history_section(self, parent):
        """Create history display section"""
        history_frame = ttk.LabelFrame(parent, text="History", padding="10")
        hist_controls = ttk.Frame(history_frame)
        hist_controls.pack(fill='x', pady=(0, 10))
        ttk.Label(hist_controls, text="Filter by interval:", font=('Segoe UI', 9)).pack(side='left')
        self.interval_filter = ttk.Combobox(hist_controls, values=['All', 'hourly', 'daily', 'weekly', 'monthly', 'yearly'],
                                            state='readonly', width=10)
        self.interval_filter.set('All')
        self.interval_filter.pack(side='left', padx=(5, 10))
        self.interval_filter.bind('<<ComboboxSelected>>', lambda e: self.load_history())
        ttk.Button(hist_controls, text="🗑️ Clear History", command=self.clear_history).pack(side='right')
        hist_container = ttk.Frame(history_frame)
        hist_container.pack(fill='both', expand=True)
        hist_columns = ('id', 'counter', 'interval', 'period', 'count')
        self.history = ttk.Treeview(hist_container, columns=hist_columns, show='headings', style="Custom.Treeview", height=8)
        self.history.heading('id', text='ID')
        self.history.heading('counter', text='Counter')
        self.history.heading('interval', text='Interval')
        self.history.heading('period', text='Period')
        self.history.heading('count', text='Count')
        self.history.column('id', width=50, anchor='center')
        self.history.column('counter', width=200, anchor='w')
        self.history.column('interval', width=100, anchor='center')
        self.history.column('period', width=120, anchor='center')
        self.history.column('count', width=80, anchor='center')
        hist_v_scrollbar = ttk.Scrollbar(hist_container, orient='vertical', command=self.history.yview)
        hist_h_scrollbar = ttk.Scrollbar(hist_container, orient='horizontal', command=self.history.xview)
        self.history.configure(yscrollcommand=hist_v_scrollbar.set, xscrollcommand=hist_h_scrollbar.set)
        self.history.grid(row=0, column=0, sticky='nsew')
        hist_v_scrollbar.grid(row=0, column=1, sticky='ns')
        hist_h_scrollbar.grid(row=1, column=0, sticky='ew')
        hist_container.grid_rowconfigure(0, weight=1)
        hist_container.grid_columnconfigure(0, weight=1)
        return history_frame

    def digital_number_str(self, number_str):
        # 7-segment ASCII fontu, 8'in izleriyle
        digits = {
            '0': [' _ ', '| |', '|_|'],
            '1': ['   ', '  |', '  |'],
            '2': [' _ ', ' _|', '|_ '],
            '3': [' _ ', ' _|', ' _|'],
            '4': ['   ', '|_|', '  |'],
            '5': [' _ ', '|_ ', ' _|'],
            '6': [' _ ', '|_ ', '|_|'],
            '7': [' _ ', '  |', '  |'],
            '8': [' _ ', '|_|', '|_|'],
            '9': [' _ ', '|_|', ' _|'],
            ',': ['   ', '   ', '   '],
            ' ': ['   ', '   ', '   '],
        }
        # Her rakamı 7 segment olarak yaz, 3 satırı birleştirip tek satırda göster
        lines = ['', '', '']
        for ch in number_str.rjust(6):
            seg = digits.get(ch, ['   ', '   ', '   '])
            for i in range(3):
                lines[i] += seg[i]
        return '\n'.join(lines)

    def create_status_bar(self):
        """Create status bar"""
        self.status_bar = ttk.Frame(self)
        self.status_bar.pack(fill='x', side='bottom')
        
        self.status_label = ttk.Label(self.status_bar, text="Ready", 
                                     font=('Segoe UI', 8),
                                     foreground=self.colors['text_secondary'])
        self.status_label.pack(side='left', padx=5, pady=2)
        
        # Add current time
        self.time_label = ttk.Label(self.status_bar, text="", 
                                   font=('Segoe UI', 8),
                                   foreground=self.colors['text_secondary'])
        self.time_label.pack(side='right', padx=5, pady=2)
        self.update_time()

    def bind_shortcuts(self):
        """Bind keyboard shortcuts"""
        self.bind('<Control-g>', lambda e: self.new_group())
        self.bind('<Control-n>', lambda e: self.new_counter())
        self.bind('<Control-i>', lambda e: self.import_counters())
        self.bind('<Control-e>', lambda e: self.export_data())
        self.bind('<Control-q>', lambda e: self.quit())
        self.bind('<Control-Shift-N>', lambda e: self.quick_add_counters())
        self.bind('<Delete>', lambda e: self.delete_counter())
        self.bind('<F5>', lambda e: self.refresh_data())

    def update_time(self):
        """Update time in status bar"""
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.time_label.config(text=current_time)
        self.after(1000, self.update_time)

    def set_status(self, message, duration=3000):
        """Set status message"""
        self.status_label.config(text=message)
        if duration > 0:
            self.after(duration, lambda: self.status_label.config(text="Ready"))

    def on_counter_single_click(self, event):
        """Handle single click on counter actions column (+ or -)"""
        region = self.tree.identify('region', event.x, event.y)
        if region != 'cell':
            return
        col = self.tree.identify_column(event.x)
        if col != '#3':  # 'actions' column is the 3rd column
            return
        row = self.tree.identify_row(event.y)
        if not row or row in ('sep', 'total'):
            return
        # Get the bounding box of the cell
        bbox = self.tree.bbox(row, col)
        if not bbox:
            return
        x_offset = event.x - bbox[0]
        # The actions cell contains '➕ ➖', so split the cell roughly in half
        cell_width = bbox[2]
        if x_offset < cell_width // 2:
            # Left side (+)
            self.db.update_counter(row, 1)
            self.load_counters()
            self.set_status("Counter incremented by 1")
        else:
            # Right side (-)
            self.db.update_counter(row, -1)
            self.load_counters()
            self.set_status("Counter decremented by 1")

    def show_context_menu(self, event):
        """Show context menu for counters"""
        selection = self.tree.selection()
        if selection and selection[0] not in ('sep', 'total'):
            context_menu = tk.Menu(self, tearoff=0)
            context_menu.add_command(label="Increment (+1)", command=lambda: self.update_selected_counter(1))
            context_menu.add_command(label="Decrement (-1)", command=lambda: self.update_selected_counter(-1))
            context_menu.add_command(label="Custom Amount", command=self.custom_update)
            context_menu.add_separator()
            context_menu.add_command(label="Delete Counter", command=self.delete_counter)
            
            try:
                context_menu.tk_popup(event.x_root, event.y_root)
            finally:
                context_menu.grab_release()

    def update_selected_counter(self, change):
        """Update selected counter by specified amount"""
        selection = self.tree.selection()
        if selection and selection[0] not in ('sep', 'total'):
            counter_id = selection[0]
            self.db.update_counter(counter_id, change)
            self.load_counters()
            action = "incremented" if change > 0 else "decremented"
            self.set_status(f"Counter {action} by {abs(change)}")

    def custom_update(self):
        """Update counter by custom amount"""
        selection = self.tree.selection()
        if not selection or selection[0] in ('sep', 'total'):
            messagebox.showwarning("Warning", "Please select a counter first")
            return
        
        dialog = InputDialog(self, "Custom Update", "Enter amount to add/subtract:")
        self.wait_window(dialog)
        
        if dialog.result:
            try:
                amount = int(dialog.result)
                counter_id = selection[0]
                self.db.update_counter(counter_id, amount)
                self.load_counters()
                action = "increased" if amount > 0 else "decreased"
                self.set_status(f"Counter {action} by {abs(amount)}")
            except ValueError:
                messagebox.showerror("Error", "Please enter a valid number")

    def filter_counters(self, *args):
        """Filter counters based on search text"""
        self.load_counters()

    def new_group(self):
        """Create new group"""
        dialog = InputDialog(self, "New Group", "Enter group name:")
        self.wait_window(dialog)
        
        if dialog.result and dialog.result.strip():
            self.db.add_group(dialog.result.strip())
            self.load_groups()
            self.set_status(f"Group '{dialog.result.strip()}' created")

    def new_counter(self):
        """Create new counter"""
        if not self.selected_group:
            messagebox.showwarning("Warning", "Please select a group first")
            return
        
        dialog = InputDialog(self, "New Counter", "Enter counter name:")
        self.wait_window(dialog)
        
        if dialog.result and dialog.result.strip():
            name = dialog.result.strip()
            if self.db.counter_exists(name, self.selected_group):
                messagebox.showwarning("Warning", f"Counter '{name}' already exists in this group")
                return
            
            self.db.add_counter(name, self.selected_group)
            self.load_counters()
            self.set_status(f"Counter '{name}' created")

    def quick_add_counters(self):
        """Quick add multiple counters"""
        if not self.selected_group:
            messagebox.showwarning("Warning", "Please select a group first")
            return
        
        dialog = InputDialog(self, "Quick Add Counters", 
                           "Enter counter names (one per line):", multiline=True)
        self.wait_window(dialog)
        
        if not dialog.result:
            return
        
        names = [name.strip() for name in dialog.result.split('\n') if name.strip()]
        added = 0
        skipped = 0
        
        for name in names:
            if self.db.counter_exists(name, self.selected_group):
                skipped += 1
                continue
            
            self.db.add_counter(name, self.selected_group)
            added += 1
        
        if added > 0:
            self.load_counters()
        
        self.set_status(f"Added {added} counters, skipped {skipped}")
        messagebox.showinfo("Quick Add Results", f"Added {added} counters. Skipped {skipped} (already exist).")

    def delete_counter(self):
        """Delete selected counter"""
        selection = self.tree.selection()
        if not selection or selection[0] in ('sep', 'total'):
            messagebox.showwarning("Warning", "Please select a counter to delete")
            return
        
        counter_name = self.tree.item(selection[0])['values'][0]
        if messagebox.askyesno("Confirm Delete", 
                              f"Are you sure you want to delete counter '{counter_name}'?\n\nThis will also delete all its history."):
            self.db.delete_counter_completely(selection[0])
            self.load_counters()
            self.set_status(f"Counter '{counter_name}' deleted")

    def export_data(self):
        """Export data to CSV, bettercounter CSV veya countn.com TXT formatında"""
        from tkinter.simpledialog import askstring
        format_choice = tk.simpledialog.askstring("Export Format", "Format seçin: bettercounter, countn, csv", initialvalue="csv")
        if not format_choice:
            return
        format_choice = format_choice.strip().lower()
        if format_choice not in ("csv", "bettercounter", "countn"):
            messagebox.showerror("Error", "Geçersiz format seçimi!")
            return
        if format_choice == "csv":
            filename = filedialog.asksaveasfilename(
                title="Export Data",
                defaultextension=".csv",
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
            )
            if filename:
                try:
                    self.db.export_to_csv(filename)
                    self.set_status("Data exported successfully")
                    messagebox.showinfo("Export Complete", f"Data exported to {filename}")
                except Exception as e:
                    messagebox.showerror("Export Error", f"Error exporting data: {str(e)}")
        elif format_choice == "bettercounter":
            filename = filedialog.asksaveasfilename(
                title="Export BetterCounter CSV",
                defaultextension=".csv",
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
            )
            if filename:
                try:
                    self.export_bettercounter_csv(filename)
                    self.set_status("BetterCounter CSV exported successfully")
                    messagebox.showinfo("Export Complete", f"Exported to {filename}")
                except Exception as e:
                    messagebox.showerror("Export Error", f"Error exporting: {str(e)}")
        elif format_choice == "countn":
            filename = filedialog.asksaveasfilename(
                title="Export CountN TXT",
                defaultextension=".txt",
                filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
            )
            if filename:
                try:
                    self.export_countn_txt(filename)
                    self.set_status("CountN TXT exported successfully")
                    messagebox.showinfo("Export Complete", f"Exported to {filename}")
                except Exception as e:
                    messagebox.showerror("Export Error", f"Error exporting: {str(e)}")

    def export_bettercounter_csv(self, filename):
        """Export counters as bettercounter CSV format: name,epoch1,epoch2,..."""
        c = self.db.conn.cursor()
        c.execute("SELECT id, name FROM counters WHERE group_id = ?", (self.selected_group,))
        counters = c.fetchall()
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            for cid, name in counters:
                c2 = self.db.conn.cursor()
                c2.execute("SELECT h.period, h.count FROM history h WHERE h.counter_id = ? ORDER BY h.id", (cid,))
                timestamps = []
                for period, count in c2.fetchall():
                    try:
                        dt = datetime.strptime(period, '%d/%m/%Y')
                        epoch = int(dt.timestamp() * 1000)
                        timestamps.extend([epoch] * count)
                    except Exception:
                        continue
                writer.writerow([name] + timestamps)

    def export_countn_txt(self, filename):
        """Export counters as countn.com TXT format"""
        c = self.db.conn.cursor()
        c.execute("SELECT id, name FROM counters WHERE group_id = ?", (self.selected_group,))
        counters = c.fetchall()
        with open(filename, 'w', encoding='utf-8') as f:
            for cid, name in counters:
                f.write("Session : Default\n\n")
                f.write(f"Counter : {name}\n\n")
                c2 = self.db.conn.cursor()
                c2.execute("SELECT h.period, h.count FROM history h WHERE h.counter_id = ? ORDER BY h.id", (cid,))
                idx = 1
                for period, count in c2.fetchall():
                    try:
                        dt = datetime.strptime(period, '%d/%m/%Y')
                        for _ in range(count):
                            f.write(f"{idx} - {dt.strftime('%d.%m.%Y %H:%M:%S')}\n")
                            idx += 1
                    except Exception:
                        continue
                f.write("\n++++++++++\n\n")

    def clear_history(self):
        """Clear all history"""
        if messagebox.askyesno("Confirm Clear", "Are you sure you want to clear all history?"):
            c = self.db.conn.cursor()
            c.execute("DELETE FROM history")
            self.db.conn.commit()
            self.load_history()
            self.set_status("History cleared")

    def refresh_data(self):
        """Refresh all data"""
        self.load_groups()
        self.load_counters()
        self.load_history()
        self.set_status("Data refreshed")

    def show_about(self):
        """Show about dialog"""
        messagebox.showinfo("About", 
                           "Professional Tally Counter v2.0\n\n"
                           "A modern, feature-rich tally counter application\n"
                           "with professional UI and advanced functionality.\n\n"
                           "Features:\n"
                           "• Multiple counter groups\n"
                           "• Historical tracking\n"
                           "• CSV import/export\n"
                           "• Search and filtering\n"
                           "• Keyboard shortcuts")

    def import_counters(self):
        """Import counters from CSV, bettercounter CSV veya countn.com TXT"""
        if not self.selected_group:
            messagebox.showwarning("Warning", "Please select a group first")
            return
        file_path = filedialog.askopenfilename(
            title="Select file",
            filetypes=[("All files", "*.*"), ("CSV files", "*.csv"), ("Text files", "*.txt")]
        )
        if not file_path:
            return
        try:
            if file_path.lower().endswith('.csv'):
                with open(file_path, 'r', newline='', encoding='utf-8') as csvfile:
                    reader = csv.reader(csvfile)
                    first_row = next(reader, None)
                    if not first_row:
                        messagebox.showerror("Error", "CSV file is empty")
                        return
                    # bettercounter: sayaç adı, epoch1, epoch2, ...
                    if len(first_row) > 2 and all(x.isdigit() for x in first_row[1:]):
                        # bettercounter formatı
                        self.import_bettercounter_csv(file_path)
                        self.set_status("Imported bettercounter CSV")
                        self.load_counters()
                        return
                    # Diğer CSV formatları için eski mantık
                    csvfile.seek(0)
                    self.import_legacy_csv(file_path)
                    self.set_status("Imported legacy CSV")
                    self.load_counters()
            elif file_path.lower().endswith('.txt'):
                with open(file_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                if any("Session :" in l for l in lines) and any("Counter :" in l for l in lines):
                    self.import_countn_txt(lines)
                    self.set_status("Imported countn.com TXT")
                    self.load_counters()
                else:
                    messagebox.showerror("Error", "Unknown TXT format")
        except Exception as e:
            messagebox.showerror("Error", f"Error importing: {str(e)}")

    def import_bettercounter_csv(self, file_path):
        import csv
        with open(file_path, 'r', newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            for row in reader:
                if not row or not row[0].strip():
                    continue
                name = row[0].strip()
                timestamps = []
                for ts in row[1:]:
                    try:
                        ts = int(ts)
                        dt = datetime.fromtimestamp(ts / 1000)
                        timestamps.append(dt)
                    except Exception:
                        continue
                if timestamps:
                    self.db.add_imported_counter_with_history(name, self.selected_group, timestamps)

    def import_legacy_csv(self, file_path):
        # Buraya eski CSV import mantığı eklenebilir (isteğe bağlı)
        pass

    def import_countn_txt(self, lines):
        # countn.com TXT formatı: Session : Default, Counter : Name, altına n - dd.mm.yyyy hh:mm:ss
        group_name = None
        name = None
        timestamps = []
        for line in lines:
            line = line.strip()
            if line.startswith("Session :"):
                group_name = line.split(":", 1)[1].strip()
                # Grup yoksa oluştur
                if group_name:
                    groups = self.db.get_groups()
                    group_id = None
                    for gid, gname in groups:
                        if gname == group_name:
                            group_id = gid
                            break
                    if group_id is None:
                        self.db.add_group(group_name)
                        groups = self.db.get_groups()
                        for gid, gname in groups:
                            if gname == group_name:
                                group_id = gid
                                break
                    self.selected_group = group_id
            elif line.startswith("Counter :"):
                if name and timestamps:
                    self._merge_or_add_counter(name, self.selected_group, timestamps)
                name = line.split(":", 1)[1].strip()
                timestamps = []
            elif line and '-' in line and any(ch.isdigit() for ch in line):
                try:
                    parts = line.split('-', 1)
                    n_str = parts[0].strip()
                    dt_str = parts[1].strip()
                    dt = datetime.strptime(dt_str, '%d.%m.%Y %H:%M:%S')
                    timestamps.append(dt)
                except Exception:
                    continue
        if name and timestamps:
            self._merge_or_add_counter(name, self.selected_group, timestamps)

    def _merge_or_add_counter(self, name, group_id, timestamps):
        # Eğer sayaç varsa, mevcut timestamp'larla birleştir (periyotlara göre)
        if self.db.counter_exists(name, group_id):
            # Mevcut sayaç id'sini bul
            counter_id = self.db.get_counter_id_by_name_group(name, group_id)
            # Mevcut sayaç için eski timestamp'ları bulmak için bir yol yoksa, doğrudan yeni timestamp'ları ekle
            # Tüm timestamp'ları birleştirip, add_imported_counter_with_history ile güncelle
            # Önce mevcut sayaç adını ve group_id'yi sil, sonra birleştirip yeniden ekle
            c = self.db.conn.cursor()
            c.execute("SELECT amount FROM counters WHERE id = ?", (counter_id,))
            row = c.fetchone()
            current_amount = row[0] if row else 0
            # Mevcut history'den eski timestamp'ları çekmek yerine, sadece yeni timestamp'ları ekle (çakışma riskini azaltmak için)
            # Alternatif: Sadece yeni timestamp'ları ekle
            for dt in timestamps:
                self.db.update_counter(counter_id, 1)
        else:
            self.db.add_imported_counter_with_history(name, group_id, timestamps)

    def _parse_timestamp(self, ts_string):
        """Parse timestamp from string"""
        try:
            try:
                ts_float = float(ts_string)
                return datetime.fromtimestamp(ts_float)
            except ValueError:
                pass
            
            formats = [
                '%Y-%m-%d %H:%M:%S',
                '%Y-%m-%d',
                '%m/%d/%Y %H:%M:%S',
                '%m/%d/%Y',
                '%d/%m/%Y %H:%M:%S',
                '%d/%m/%Y',
            ]
            
            for fmt in formats:
                try:
                    return datetime.strptime(ts_string, fmt)
                except ValueError:
                    continue
            
            return None
        except Exception:
            return None

    def load_groups(self):
        """Load groups into combobox"""
        groups = self.db.get_groups()
        self.group_cb['values'] = [g[1] for g in groups]
        if groups:
            self.group_cb.current(0)
            self.selected_group = groups[0][0]
            self.load_counters()

    def load_counters(self):
        """Load counters for selected group"""
        groups = self.db.get_groups()
        sel = self.group_cb.get()
        gid = next((g[0] for g in groups if g[1] == sel), None)
        self.selected_group = gid
        
        # Clear existing items
        for row in self.tree.get_children():
            self.tree.delete(row)
        if not gid:
            return
        counters = self.db.get_counters(gid)
        search_term = self.search_var.get().lower()
        total_count = 0
        displayed_count = 0
        for cid, name, amt in counters:
            if not search_term or search_term in name.lower():
                self.tree.insert('', 'end', iid=cid, values=(name, str(amt), "➕ ➖"))
                displayed_count += 1
            total_count += amt
        if counters:
            self.tree.insert('', 'end', iid='sep', values=('─' * 30, '─' * 10, ''))
            self.tree.insert('', 'end', iid='total', values=(f"TOTAL ({len(counters)} counters)", str(total_count), ''))
            self.tree.item('total', tags=('total',))
            self.tree.tag_configure('total', font=('Segoe UI', 10, 'bold'), 
                                   background=self.colors['primary'], foreground='white')
            self.tree.tag_configure('sep', foreground=self.colors['text_secondary'])
        self.tree.tag_configure('oddrow', background='#F8F9FA')
        self.tree.tag_configure('evenrow', background='#FFFFFF')
        for i, item in enumerate(self.tree.get_children()):
            if item not in ('sep', 'total'):
                tag = 'oddrow' if i % 2 else 'evenrow'
                self.tree.item(item, tags=(tag,))
        # Tooltip for digital number
        if not hasattr(self, 'amount_tooltip'):
            self.amount_tooltip = ToolTip(self.tree)
        def on_motion(event):
            region = self.tree.identify('region', event.x, event.y)
            col = self.tree.identify_column(event.x)
            row = self.tree.identify_row(event.y)
            if region == 'cell' and col == '#2' and row and row not in ('sep', 'total'):
                amt = self.tree.item(row)['values'][1]
                digital = self.digital_number_str(str(amt))
                x = self.tree.winfo_rootx() + event.x + 20
                y = self.tree.winfo_rooty() + event.y + 10
                self.amount_tooltip.showtip(digital, x, y)
            else:
                self.amount_tooltip.hidetip()
        self.tree.bind('<Motion>', on_motion)
        self.tree.bind('<Leave>', lambda e: self.amount_tooltip.hidetip())
        self.load_history()

    def load_history(self):
        """Load history data"""
        for row in self.history.get_children():
            self.history.delete(row)
        
        interval_filter = self.interval_filter.get()
        
        for log in self.db.get_history():
            if interval_filter == 'All' or log[2] == interval_filter:
                self.history.insert('', 'end', values=log)
        
        # Configure alternating row colors for history
        for i, item in enumerate(self.history.get_children()):
            tag = 'oddrow' if i % 2 else 'evenrow'
            self.history.item(item, tags=(tag,))

class ToolTip:
    """Simple tooltip for widgets"""
    def __init__(self, widget):
        self.widget = widget
        self.tipwindow = None

    def showtip(self, text, x, y):
        if self.tipwindow or not text:
            return
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(tw, text=text, justify='left',
                         background="#ffffe0", relief='solid', borderwidth=1,
                         font=("Consolas", 10))
        label.pack(ipadx=1)

    def hidetip(self):
        tw = self.tipwindow
        self.tipwindow = None
        if tw:
            tw.destroy()

if __name__ == '__main__':
    # Create database directory if it doesn't exist
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    
    db = DBManager(DB_FILE)
    app = TallyApp(db)
    app.mainloop()
