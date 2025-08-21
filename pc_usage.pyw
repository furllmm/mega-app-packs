#!/usr/bin/python3
import sys
import platform
if platform.system() == 'Windows':
    sys.path.append(r"D:/py/adb")
    try:
        from adb_utils import get_foreground_app, is_adb_connected
    except ImportError:
        pass  # adb_utils not available, ignore on non-Windows

import sqlite3
import os
import psutil
from datetime import datetime, timedelta
from pynput import keyboard, mouse
from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtWidgets import QSystemTrayIcon, QMenu, QAction, QStyle, QInputDialog, QMessageBox, QHBoxLayout, QVBoxLayout, QPushButton, QLabel, QSpinBox, QComboBox
import platform
import time
import ctypes

# OPTIMIZED TIMER SETTINGS
IDLE_THRESHOLD = 120
UPDATE_INTERVAL = 2000  # 2 seconds
REFRESH_INTERVAL = 10000  # Refresh tables every 10 seconds

# Database path - USING YOUR EXISTING DATABASE
if platform.system() == 'Windows':
    DB_PATH = r'./db/usage.db'
else:
    DB_PATH = os.path.expanduser('~/db/usage.db')
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


# Pagination settings
RECORDS_PER_PAGE = 50
PAGE_SIZE_OPTIONS = [25, 50, 100, 200, 500]

# Global counters
key_count = 0
click_counts = {'left': 0, 'right': 0, 'middle': 0}

# Performance optimization
_process_cache = {}
_last_hwnd = None
_last_process_info = (None, None)
_cache_timestamp = 0
_last_api_call_time = 0
_api_call_interval = 3.0
_last_refresh_time = 0

# Predefined application categories
DEFAULT_CATEGORIES = {
    'chrome.exe': 'Web Browsing',
    'firefox.exe': 'Web Browsing',
    'vivaldi.exe': 'Web Browsing',
    'thorium.exe': 'Web Browsing',
    'code.exe': 'Development',
    'notepad++.exe': 'Development',
    'python.exe': 'Development',
    'pythonw.exe': 'Development',
    'winword.exe': 'Office & Productivity',
    'excel.exe': 'Office & Productivity',
    'vlc.exe': 'Media & Entertainment',
    'spotify.exe': 'Media & Entertainment',
    'discord.exe': 'Communication',
    'steam.exe': 'Gaming',
    'explorer.exe': 'System & Utilities',
}

# Input listeners
def on_key_press(key):
    global key_count
    key_count += 1

def on_click(x, y, button, pressed):
    global click_counts
    if pressed:
        name = button.name if hasattr(button, 'name') else str(button)
        if name in click_counts:
            click_counts[name] += 1

keyboard.Listener(on_press=on_key_press, daemon=True).start()
mouse.Listener(on_click=on_click, daemon=True).start()

def get_idle_duration():
    if platform.system() == 'Windows':
        import ctypes
        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [
                ('cbSize', ctypes.c_uint),
                ('dwTime', ctypes.c_uint),
            ]
        lastInputInfo = LASTINPUTINFO()
        lastInputInfo.cbSize = ctypes.sizeof(LASTINPUTINFO)
        if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lastInputInfo)):
            millis = ctypes.windll.kernel32.GetTickCount() - lastInputInfo.dwTime
            return millis / 1000.0
        else:
            return 0
    elif platform.system() == 'Linux':
        try:
            import subprocess
            idle_ms = int(subprocess.check_output(['xprintidle']).decode().strip())
            return idle_ms / 1000.0
        except Exception:
            return 0
    else:
        return 0

def get_foreground_info():
    if platform.system() == 'Windows':
        try:
            import ctypes
            from ctypes import wintypes
            
            global _last_hwnd, _last_process_info, _cache_timestamp, _process_cache
            global _last_api_call_time, _api_call_interval
            
            current_time = time.time()
            
            # Return cached result if within interval
            if current_time - _last_api_call_time < _api_call_interval:
                return _last_process_info
            
            user32 = ctypes.windll.user32
            
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return None, None
            
            if hwnd == _last_hwnd and (current_time - _cache_timestamp) < 10.0:
                return _last_process_info
            
            _last_api_call_time = current_time
            
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            
            proc_name = None
            if pid.value in _process_cache:
                proc_name = _process_cache[pid.value]
            else:
                try:
                    process = psutil.Process(pid.value)
                    proc_name = process.name()
                    _process_cache[pid.value] = proc_name
                    # Keep cache size manageable
                    if len(_process_cache) > 50:
                        keys_to_remove = list(_process_cache.keys())[:10]
                        for key in keys_to_remove:
                            del _process_cache[key]
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    proc_name = None
            
            length = user32.GetWindowTextLengthW(hwnd)
            window_title = None
            if length > 0:
                buffer = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buffer, length + 1)
                window_title = buffer.value
            
            _last_hwnd = hwnd
            _last_process_info = (proc_name, window_title)
            _cache_timestamp = current_time
            
            return proc_name, window_title
        except Exception as e:
            return None, None
    elif platform.system() == 'Linux':
        # Linux implementation using wmctrl and psutil with debug output
        try:
            import subprocess
            print('[DEBUG] Running: xprop -root _NET_ACTIVE_WINDOW')
            win_id_line = subprocess.check_output([
                'xprop', '-root', '_NET_ACTIVE_WINDOW'
            ]).decode()
            print(f'[DEBUG] xprop output: {win_id_line.strip()}')
            if 'window id #' not in win_id_line:
                print('[DEBUG] No window id found in xprop output')
                return None, None
            win_id = win_id_line.strip().split()[-1]
            print(f'[DEBUG] Extracted win_id: {win_id}')
            if win_id == '0x0':
                print('[DEBUG] win_id is 0x0 (no active window)')
                return None, None
            # Get window list with PID
            print('[DEBUG] Running: wmctrl -lp')
            win_list = subprocess.check_output(['wmctrl', '-lp']).decode().splitlines()
            print(f'[DEBUG] wmctrl output lines: {len(win_list)}')
            pid = None
            found_line = None
            for line in win_list:
                parts = line.split()
                if len(parts) >= 4:
                    # Compare both hex and decimal window IDs
                    if parts[0].lower() == win_id.lower() or str(int(parts[0], 16)) == str(int(win_id, 16)):
                        pid = int(parts[2])
                        found_line = line
                        break
            print(f'[DEBUG] Matched wmctrl line: {found_line}')
            if not pid:
                print('[DEBUG] No matching PID found for win_id')
                return None, None
            # Get process name
            try:
                proc = psutil.Process(pid)
                proc_name = proc.name()
                print(f'[DEBUG] Process name: {proc_name}')
            except Exception as e:
                print(f'[DEBUG] psutil.Process error: {e}')
                proc_name = None
            # Get window title
            try:
                print(f'[DEBUG] Running: xprop -id {win_id} WM_NAME')
                title = subprocess.check_output([
                    'xprop', '-id', win_id, 'WM_NAME'
                ]).decode()
                print(f'[DEBUG] xprop WM_NAME output: {title.strip()}')
                if 'WM_NAME(' in title:
                    title = title.split('=', 1)[-1].strip().strip('"')
                else:
                    title = None
            except Exception as e:
                print(f'[DEBUG] xprop WM_NAME error: {e}')
                title = None
            return proc_name, title
        except Exception as e:
            print(f'[DEBUG] get_foreground_info Linux error: {e}')
            return None, None
    else:
        return None, None

def get_network_usage():
    try:
        stats = psutil.net_io_counters()
        return stats.bytes_sent, stats.bytes_recv
    except:
        return 0, 0

def get_disk_usage():
    try:
        stats = psutil.disk_io_counters()
        return stats.write_bytes if stats else 0
    except:
        return 0

def format_bytes(bytes_val):
    if bytes_val is None or bytes_val == 0:
        return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_val < 1024:
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024
    return f"{bytes_val:.1f} TB"

class PaginationWidget(QtWidgets.QWidget):
    page_changed = QtCore.pyqtSignal(int)
    page_size_changed = QtCore.pyqtSignal(int)
    
    def __init__(self):
        super().__init__()
        self.current_page = 1
        self.total_pages = 1
        self.page_size = RECORDS_PER_PAGE
        self.setup_ui()
    
    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Page size selector
        layout.addWidget(QLabel("Sayfa boyutu:"))
        self.page_size_combo = QComboBox()
        self.page_size_combo.addItems([str(size) for size in PAGE_SIZE_OPTIONS])
        self.page_size_combo.setCurrentText(str(self.page_size))
        self.page_size_combo.currentTextChanged.connect(self.on_page_size_changed)
        layout.addWidget(self.page_size_combo)
        
        layout.addStretch()
        
        # Navigation buttons
        self.first_btn = QPushButton("İlk")
        self.first_btn.clicked.connect(lambda: self.go_to_page(1))
        layout.addWidget(self.first_btn)
        
        self.prev_btn = QPushButton("Önceki")
        self.prev_btn.clicked.connect(self.prev_page)
        layout.addWidget(self.prev_btn)
        
        self.page_label = QLabel("Sayfa 1 / 1")
        layout.addWidget(self.page_label)
        
        self.next_btn = QPushButton("Sonraki")
        self.next_btn.clicked.connect(self.next_page)
        layout.addWidget(self.next_btn)
        
        self.last_btn = QPushButton("Son")
        self.last_btn.clicked.connect(lambda: self.go_to_page(self.total_pages))
        layout.addWidget(self.last_btn)
    
    def update_pagination(self, current_page, total_pages):
        self.current_page = current_page
        self.total_pages = max(1, total_pages)
        
        self.page_label.setText(f"Sayfa {self.current_page} / {self.total_pages}")
        
        self.first_btn.setEnabled(self.current_page > 1)
        self.prev_btn.setEnabled(self.current_page > 1)
        self.next_btn.setEnabled(self.current_page < self.total_pages)
        self.last_btn.setEnabled(self.current_page < self.total_pages)
    
    def go_to_page(self, page):
        if 1 <= page <= self.total_pages:
            self.current_page = page
            self.page_changed.emit(page)
    
    def prev_page(self):
        if self.current_page > 1:
            self.go_to_page(self.current_page - 1)
    
    def next_page(self):
        if self.current_page < self.total_pages:
            self.go_to_page(self.current_page + 1)
    
    def on_page_size_changed(self, size_text):
        self.page_size = int(size_text)
        self.page_size_changed.emit(self.page_size)

class UsageTracker(QtCore.QObject):
    session_updated = QtCore.pyqtSignal()
    
    def __init__(self):
        super().__init__()
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self._create_db()
        self.current = None

    def _create_db(self):
        c = self.conn.cursor()

        # Create usage table if it doesn't exist
        c.execute('''CREATE TABLE IF NOT EXISTS usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            app TEXT,
            start TEXT,
            end TEXT,
            duration REAL,
            downloads INTEGER,
            uploads INTEGER,
            key_presses INTEGER,
            disk_writes INTEGER,
            left_clicks INTEGER,
            right_clicks INTEGER,
            middle_clicks INTEGER,
            category TEXT
        )''')

        # Add is_deleted column if missing
        try:
            c.execute("SELECT is_deleted FROM usage LIMIT 1")
        except sqlite3.OperationalError:
            try:
                c.execute("ALTER TABLE usage ADD COLUMN is_deleted INTEGER DEFAULT 0")
            except sqlite3.OperationalError:
                pass

        # Add deleted_date column if missing
        try:
            c.execute("SELECT deleted_date FROM usage LIMIT 1")
        except sqlite3.OperationalError:
            try:
                c.execute("ALTER TABLE usage ADD COLUMN deleted_date TEXT")
            except sqlite3.OperationalError:
                pass

        # Create app_categories table for custom categorization
        c.execute('''CREATE TABLE IF NOT EXISTS app_categories (
            app_name TEXT PRIMARY KEY,
            category TEXT NOT NULL
        )''')
        self.conn.commit()

        # --- MIGRATION: Convert all date fields to ISO format if needed ---
        def convert_to_iso(date_str):
            if not date_str:
                return None
            # If already correct format, return as is
            try:
                datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
                return date_str
            except ValueError:
                pass
            # If ISO with T and microseconds, convert
            try:
                if 'T' in date_str:
                    dt = datetime.strptime(date_str.split('.')[0].replace('T', ' '), '%Y-%m-%d %H:%M:%S')
                    return dt.strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                pass
            # If old format (d/m/Y H:M:S)
            try:
                dt = datetime.strptime(date_str, '%d/%m/%Y %H:%M:%S')
                return dt.strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                pass
            # If ISO with microseconds and space
            try:
                dt = datetime.strptime(date_str.split('.')[0], '%Y-%m-%d %H:%M:%S')
                return dt.strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                pass
            return date_str  # fallback

        # Run migration for all records
        c.execute("SELECT id, start, end, deleted_date FROM usage")
        rows = c.fetchall()
        for row in rows:
            id_, start, end, deleted_date = row
            new_start = convert_to_iso(start)
            new_end = convert_to_iso(end)
            new_deleted = convert_to_iso(deleted_date) if deleted_date else None
            if new_start != start or new_end != end or (deleted_date and new_deleted != deleted_date):
                c.execute("UPDATE usage SET start=?, end=?, deleted_date=? WHERE id=?", (new_start, new_end, new_deleted, id_))
        self.conn.commit()

    def get_app_category(self, app_name):
        if not app_name:
            return "Uncategorized"
        
        # First check custom categories from database
        c = self.conn.cursor()
        c.execute('SELECT category FROM app_categories WHERE app_name = ?', (app_name,))
        result = c.fetchone()
        if result:
            return result[0]
        
        # Then check default categories
        app_lower = app_name.lower()
        for default_app, category in DEFAULT_CATEGORIES.items():
            if default_app.lower() == app_lower:
                return category
        
        return "Uncategorized"
    
    def set_app_category(self, app_name, category):
        """Set custom category for an app"""
        c = self.conn.cursor()
        c.execute('''INSERT OR REPLACE INTO app_categories (app_name, category) 
                     VALUES (?, ?)''', (app_name, category))
        self.conn.commit()
        
        # Update existing records
        c.execute('''UPDATE usage SET category = ? WHERE app = ?''', (category, app_name))
        self.conn.commit()
    
    def get_all_categories(self):
        """Get all unique categories"""
        c = self.conn.cursor()
        c.execute('''SELECT DISTINCT category FROM usage WHERE category IS NOT NULL
                     UNION 
                     SELECT DISTINCT category FROM app_categories
                     ORDER BY category''')
        return [row[0] for row in c.fetchall()]

    def start_session(self, app_label):
        if self.current:
            if self.current['app'] == app_label:
                return
            self.end_session()
        
        now = datetime.now()
        self.current = {
            'app': app_label,
            'start': now,
            'net': get_network_usage(),
            'disk': get_disk_usage(),
            'keys': key_count,
            'clicks': click_counts.copy()
        }

    def end_session(self):
        if not self.current:
            return
        now = datetime.now()
        dur = (now - self.current['start']).total_seconds()
        if dur < 1:
            self.current = None
            return
        net2 = get_network_usage()
        disk2 = get_disk_usage()
        downloads = max(0, net2[1] - self.current['net'][1])
        uploads = max(0, net2[0] - self.current['net'][0])
        writes = max(0, disk2 - self.current['disk'])
        keys = max(0, key_count - self.current['keys'])
        left = max(0, click_counts['left'] - self.current['clicks']['left'])
        right = max(0, click_counts['right'] - self.current['clicks']['right'])
        middle = max(0, click_counts['middle'] - self.current['clicks']['middle'])
        app_category = self.get_app_category(self.current['app'])
        c = self.conn.cursor()
        c.execute('''INSERT INTO usage (app,start,end,duration,downloads,uploads,key_presses,disk_writes,left_clicks,right_clicks,middle_clicks,category,is_deleted,deleted_date)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?,?,0,NULL)''', (
            self.current['app'],
            self.current['start'].strftime('%Y-%m-%d %H:%M:%S'),
            now.strftime('%Y-%m-%d %H:%M:%S'),
            dur, downloads, uploads, keys, writes, left, right, middle, app_category
        ))
        self.conn.commit()
        self.current = None
        self.session_updated.emit()
    
    def get_paginated_records(self, page=1, page_size=RECORDS_PER_PAGE, show_deleted=False, browser_exclude=False):
        """Get paginated records, optionally excluding browsers."""
        c = self.conn.cursor()
        offset = (page - 1) * page_size
        deleted_filter = "is_deleted = 1" if show_deleted else "COALESCE(is_deleted, 0) = 0"
        where = deleted_filter
        if browser_exclude:
            browser_exes = [k.lower() for k, v in DEFAULT_CATEGORIES.items() if v == 'Web Browsing']
            app_exclude_conditions = [f"LOWER(app) NOT LIKE '{exe}%'" for exe in browser_exes]
            where += ' AND ' + ' AND '.join(app_exclude_conditions)
        # Get total count
        count_query = f"SELECT COUNT(*) FROM usage WHERE {where}"
        c.execute(count_query)
        total_records = c.fetchone()[0]
        total_pages = (total_records + page_size - 1) // page_size if total_records > 0 else 1
        # Get records for current page
        query = f'''SELECT id, app, start, end, duration, downloads, uploads, \
                           key_presses, disk_writes, left_clicks, right_clicks, \
                           middle_clicks, category, COALESCE(is_deleted, 0), deleted_date
                    FROM usage WHERE {where}
                    ORDER BY start DESC LIMIT ? OFFSET ?'''
        c.execute(query, (page_size, offset))
        records = c.fetchall()
        return records, total_pages, total_records
    
    def get_paginated_summary(self, page=1, page_size=RECORDS_PER_PAGE, browser_only=None):
        """Get paginated summary data, optionally filtered for browsers or non-browsers. For browsers, group by app and tab title."""
        c = self.conn.cursor()
        offset = (page - 1) * page_size
        browser_exes = [k.lower() for k, v in DEFAULT_CATEGORIES.items() if v == 'Web Browsing']
        where = 'COALESCE(is_deleted, 0) = 0'
        if browser_only is True:
            # For browsers, show each tab as a single row (group by tab only)
            browser_conditions = [f"LOWER(app) LIKE '{exe}%'" for exe in browser_exes]
            where += ' AND (' + ' OR '.join(browser_conditions) + ')'
            # Count unique tab titles
            count_query = f'''SELECT COUNT(DISTINCT (CASE WHEN INSTR(app, ' - ') > 0 THEN TRIM(SUBSTR(app, INSTR(app, ' - ')+3, 1000)) ELSE app END)) FROM usage WHERE {where}'''
            c.execute(count_query)
            total_records = c.fetchone()[0]
            total_pages = (total_records + page_size - 1) // page_size if total_records > 0 else 1
            query = f'''
                SELECT
                    CASE WHEN INSTR(app, ' - ') > 0 THEN TRIM(SUBSTR(app, INSTR(app, ' - ')+3, 1000)) ELSE app END AS tab,
                    category,
                    COUNT(*) as sessions,
                    SUM(duration) as total_duration,
                    SUM(downloads) as total_downloads,
                    SUM(uploads) as total_uploads,
                    SUM(key_presses) as total_keys,
                    SUM(disk_writes) as total_disk,
                    SUM(left_clicks) as total_left,
                    SUM(right_clicks) as total_right,
                    SUM(middle_clicks) as total_middle
                FROM usage
                WHERE {where}
                GROUP BY tab, category
                ORDER BY total_duration DESC
                LIMIT ? OFFSET ?'''
            c.execute(query, [page_size, offset])
            records = c.fetchall()
            return records, total_pages, total_records
        elif browser_only is False:
            # For non-browsers, exclude browser processes
            app_exclude_conditions = [f"LOWER(app) NOT LIKE '{exe}%'" for exe in browser_exes]
            where += ' AND ' + ' AND '.join(app_exclude_conditions)
            count_query = f'''SELECT COUNT(DISTINCT app) FROM usage WHERE {where}'''
            c.execute(count_query)
            total_records = c.fetchone()[0]
            total_pages = (total_records + page_size - 1) // page_size if total_records > 0 else 1
            query = f'''
                SELECT app, category,
                      COUNT(*) as sessions,
                      SUM(duration) as total_duration,
                      SUM(downloads) as total_downloads,
                      SUM(uploads) as total_uploads,
                      SUM(key_presses) as total_keys,
                      SUM(disk_writes) as total_disk,
                      SUM(left_clicks) as total_left,
                      SUM(right_clicks) as total_right,
                      SUM(middle_clicks) as total_middle
               FROM usage WHERE {where}
               GROUP BY app, category
               ORDER BY total_duration DESC
               LIMIT ? OFFSET ?'''
            c.execute(query, [page_size, offset])
            records = c.fetchall()
            return records, total_pages, total_records
        else:
            # All apps summary (not used for browsers tab)
            count_query = f'''SELECT COUNT(DISTINCT app) FROM usage WHERE {where}'''
            c.execute(count_query)
            total_records = c.fetchone()[0]
            total_pages = (total_records + page_size - 1) // page_size if total_records > 0 else 1
            query = f'''
                SELECT app, category,
                      COUNT(*) as sessions,
                      SUM(duration) as total_duration,
                      SUM(downloads) as total_downloads,
                      SUM(uploads) as total_uploads,
                      SUM(key_presses) as total_keys,
                      SUM(disk_writes) as total_disk,
                      SUM(left_clicks) as total_left,
                      SUM(right_clicks) as total_right,
                      SUM(middle_clicks) as total_middle
               FROM usage WHERE {where}
               GROUP BY app, category
               ORDER BY total_duration DESC
               LIMIT ? OFFSET ?'''
            c.execute(query, [page_size, offset])
            records = c.fetchall()
            return records, total_pages, total_records
    
    def soft_delete_records(self, record_ids):
        """Soft delete records by moving them to recycle bin"""
        if not record_ids:
            return
        
        c = self.conn.cursor()
        placeholders = ','.join(['?' for _ in record_ids])
        query = f'''UPDATE usage SET is_deleted = 1, deleted_date = ?
                    WHERE id IN ({placeholders}) AND COALESCE(is_deleted, 0) = 0'''
        
        params = [datetime.now().strftime('%Y-%m-%d %H:%M:%S')] + list(record_ids)
        c.execute(query, params)
        self.conn.commit()
    
    def restore_records(self, record_ids):
        """Restore records from recycle bin"""
        if not record_ids:
            return
        
        c = self.conn.cursor()
        placeholders = ','.join(['?' for _ in record_ids])
        query = f'''UPDATE usage SET is_deleted = 0, deleted_date = NULL
                    WHERE id IN ({placeholders}) AND is_deleted = 1'''
        
        c.execute(query, record_ids)
        self.conn.commit()
    
    def permanently_delete_records(self, record_ids):
        """Permanently delete records"""
        if not record_ids:
            return
        
        c = self.conn.cursor()
        placeholders = ','.join(['?' for _ in record_ids])
        query = f'DELETE FROM usage WHERE id IN ({placeholders})'
        
        c.execute(query, record_ids)
        self.conn.commit()
    
    def empty_recycle_bin(self):
        """Permanently delete all records in recycle bin"""
        c = self.conn.cursor()
        c.execute('DELETE FROM usage WHERE is_deleted = 1')
        self.conn.commit()

class MainWindow(QtWidgets.QWidget):
    def setup_tabs_once(self):
        """Setup all tabs only once, and prevent duplicate tab creation or content mixing."""
        if hasattr(self, '_tabs_initialized') and self._tabs_initialized:
            return
        self._tabs_initialized = True

        # Remove all tabs if any exist (defensive)
        while self.tabs.count() > 0:
            self.tabs.removeTab(0)

        # Detailed tab
        pane1 = QtWidgets.QWidget()
        layout1 = QVBoxLayout(pane1)
        info_layout = QHBoxLayout()
        info_label = QLabel("Del: Geri dönüşüm kutusuna taşı | Çoklu seçim desteklenir")
        info_label.setStyleSheet("color: #666; font-size: 10px; padding: 5px;")
        info_layout.addWidget(info_label)
        info_layout.addStretch()
        self.delete_btn = QPushButton("Seçilenleri Sil")
        self.delete_btn.setStyleSheet("QPushButton { background-color: #ff9999; }")
        self.delete_btn.clicked.connect(self.delete_selected_detailed)
        info_layout.addWidget(self.delete_btn)
        layout1.addLayout(info_layout)
        self.table1 = QtWidgets.QTableWidget()
        self.table1.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table1.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.table1.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        layout1.addWidget(self.table1)
        self.detailed_pagination = PaginationWidget()
        self.detailed_pagination.page_changed.connect(self.on_detailed_page_changed)
        self.detailed_pagination.page_size_changed.connect(self.on_detailed_page_size_changed)
        layout1.addWidget(self.detailed_pagination)
        self.tabs.addTab(pane1, 'Detaylı')

        # Browsers summary tab
        pane_browsers = QtWidgets.QWidget()
        layout_browsers = QVBoxLayout(pane_browsers)
        info_label_browsers = QLabel("Alt+C: Kategorilendirme | Sadece tarayıcılar | Çoklu seçim desteklenir")
        info_label_browsers.setStyleSheet("color: #666; font-size: 10px; padding: 5px;")
        layout_browsers.addWidget(info_label_browsers)
        self.table_browsers = QtWidgets.QTableWidget()
        self.table_browsers.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table_browsers.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.table_browsers.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        layout_browsers.addWidget(self.table_browsers)
        self.browsers_pagination = PaginationWidget()
        self.browsers_pagination.page_changed.connect(self.on_browsers_page_changed)
        self.browsers_pagination.page_size_changed.connect(self.on_browsers_page_size_changed)
        layout_browsers.addWidget(self.browsers_pagination)
        self.tabs.addTab(pane_browsers, 'Tarayıcılar')

        # Applications summary tab
        pane_apps = QtWidgets.QWidget()
        layout_apps = QVBoxLayout(pane_apps)
        info_label_apps = QLabel("Alt+C: Kategorilendirme | Tarayıcılar hariç | Çoklu seçim desteklenir")
        info_label_apps.setStyleSheet("color: #666; font-size: 10px; padding: 5px;")
        layout_apps.addWidget(info_label_apps)
        self.table_apps = QtWidgets.QTableWidget()
        self.table_apps.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table_apps.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.table_apps.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        layout_apps.addWidget(self.table_apps)
        self.apps_pagination = PaginationWidget()
        self.apps_pagination.page_changed.connect(self.on_apps_page_changed)
        self.apps_pagination.page_size_changed.connect(self.on_apps_page_size_changed)
        layout_apps.addWidget(self.apps_pagination)
        self.tabs.addTab(pane_apps, 'Uygulamalar')

        # Category totals tab (should be tab 3)
        pane4 = QtWidgets.QWidget()
        layout4 = QVBoxLayout(pane4)
        info_label = QLabel("Kategoriye göre toplam süre, oturum, tıklama, klavye, internet ve disk kullanımı")
        info_label.setStyleSheet("color: #666; font-size: 10px; padding: 5px;")
        layout4.addWidget(info_label)
        self.table4 = QtWidgets.QTableWidget()
        self.table4.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table4.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.table4.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        layout4.addWidget(self.table4)
        self.tabs.addTab(pane4, 'Kategori Toplam')

        # Recycle bin tab (should be tab 4)
        pane3 = QtWidgets.QWidget()
        layout3 = QVBoxLayout(pane3)
        btn_layout = QHBoxLayout()
        self.restore_btn = QPushButton("Seçilenleri Geri Yükle")
        self.restore_btn.setStyleSheet("QPushButton { background-color: #99ff99; }")
        self.restore_btn.clicked.connect(self.restore_selected)
        btn_layout.addWidget(self.restore_btn)
        self.permanent_delete_btn = QPushButton("Kalıcı Sil")
        self.permanent_delete_btn.setStyleSheet("QPushButton { background-color: #ffcc99; }")
        self.permanent_delete_btn.clicked.connect(self.permanent_delete_selected)
        btn_layout.addWidget(self.permanent_delete_btn)
        btn_layout.addStretch()
        self.empty_bin_btn = QPushButton("Geri Dönüşüm Kutusunu Boşalt")
        self.empty_bin_btn.clicked.connect(self.empty_recycle_bin)
        self.empty_bin_btn.setStyleSheet("QPushButton { background-color: #ff6b6b; color: white; font-weight: bold; }")
        btn_layout.addWidget(self.empty_bin_btn)
        layout3.addLayout(btn_layout)
        self.table3 = QtWidgets.QTableWidget()
        self.table3.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table3.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.table3.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        layout3.addWidget(self.table3)
        self.recycle_pagination = PaginationWidget()
        self.recycle_pagination.page_changed.connect(self.on_recycle_page_changed)
        self.recycle_pagination.page_size_changed.connect(self.on_recycle_page_size_changed)
        layout3.addWidget(self.recycle_pagination)
        self.tabs.addTab(pane3, '🗑️ Geri Dönüşüm Kutusu')

    def __init__(self):
        super().__init__()
        self.setWindowTitle('App Usage Tracker - Enhanced with Recycle Bin & Paging')
        self.resize(1200, 700)
        self.tracker = UsageTracker()
        self.tabs = QtWidgets.QTabWidget()
        self.detailed_page = 1
        self.detailed_page_size = RECORDS_PER_PAGE
        self.browsers_page = 1
        self.browsers_page_size = RECORDS_PER_PAGE
        self.apps_page = 1
        self.apps_page_size = RECORDS_PER_PAGE
        self.recycle_page = 1
        self.recycle_page_size = RECORDS_PER_PAGE
        self.category_totals_page = 1
        self.category_totals_page_size = RECORDS_PER_PAGE
        self.setup_tabs_once()
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.addWidget(self.tabs)
        self.setup_shortcuts()
        self.setup_tray()
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.check_active)
        self.timer.start(UPDATE_INTERVAL)
        self.refresh_timer = QtCore.QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_tables_if_needed)
        self.refresh_timer.start(REFRESH_INTERVAL)
        self.tracker.session_updated.connect(self.mark_refresh_needed)
        self.refresh_needed = False
        self.refresh_all_tables()
    
    def refresh_category_totals_table(self):
        """Refresh category totals table"""
        c = self.tracker.conn.cursor()
        c.execute('''SELECT category,
                        COUNT(*) as oturum,
                        SUM(duration) as toplam_sure,
                        SUM(left_clicks + right_clicks + middle_clicks) as toplam_tik,
                        SUM(key_presses) as toplam_klavye,
                        SUM(downloads) as toplam_download,
                        SUM(uploads) as toplam_upload,
                        SUM(disk_writes) as toplam_disk
                 FROM usage WHERE is_deleted = 0 OR is_deleted IS NULL
                 GROUP BY category
                 ORDER BY toplam_sure DESC''')
        records = c.fetchall()
        headers = ['Kategori', 'Oturum', 'Toplam Süre', 'Toplam Tık', 'Klavye', 'Download', 'Upload', 'Disk']
        self.table4.setRowCount(len(records))
        self.table4.setColumnCount(len(headers))
        self.table4.setHorizontalHeaderLabels(headers)
        for i, row in enumerate(records):
            for j, val in enumerate(row):
                if j == 2:  # toplam_sure
                    hours = int(val // 3600) if val else 0
                    minutes = int((val % 3600) // 60) if val else 0
                    val_str = f"{hours}h {minutes}m"
                elif j in [5, 6, 7]:  # Download, Upload, Disk
                    val_str = format_bytes(val) if val else '0 B'
                else:
                    val_str = str(val) if val else ''
                self.table4.setItem(i, j, QtWidgets.QTableWidgetItem(val_str))
        self.table4.resizeColumnsToContents()
        self.tabs.setTabText(3, f'Kategori Toplam ({len(records)})')

    def setup_shortcuts(self):
        """Setup keyboard shortcuts"""
        categorize_shortcut = QtWidgets.QShortcut(QtGui.QKeySequence("Alt+C"), self)
        categorize_shortcut.activated.connect(self.categorize_selected_apps)
        
        delete_shortcut = QtWidgets.QShortcut(QtGui.QKeySequence("Delete"), self)
        delete_shortcut.activated.connect(self.delete_current_selection)
    
    def setup_tray(self):
        """Setup system tray icon"""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            QMessageBox.critical(None, "System Tray", "System tray is not available on this system.")
            return
        
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(self.style().standardIcon(QStyle.SP_ComputerIcon))
        
        # Create tray menu
        tray_menu = QMenu()
        
        show_action = QAction("Göster", self)
        show_action.triggered.connect(self.show_window)
        tray_menu.addAction(show_action)
        
        hide_action = QAction("Gizle", self)
        hide_action.triggered.connect(self.hide)
        tray_menu.addAction(hide_action)
        
        tray_menu.addSeparator()
        
        quit_action = QAction("Çıkış", self)
        quit_action.triggered.connect(QtWidgets.QApplication.quit)
        tray_menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.tray_icon_activated)
        self.tray_icon.show()
    
    def show_window(self):
        self.show()
        self.raise_()
        self.activateWindow()
    
    def tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_window()
    
    def closeEvent(self, event):
        if self.tray_icon.isVisible():
            self.hide()
            event.ignore()
        else:
            event.accept()
    
    def check_active(self):
        idle = get_idle_duration()
        if idle < IDLE_THRESHOLD:
            app, title = get_foreground_info()
            if app:
                app_label = f"{app}"
                if title and len(title.strip()) > 0:
                    app_label += f" - {title[:50]}"
                self.tracker.start_session(app_label)
            else:
                self.tracker.end_session()
        else:
            self.tracker.end_session()
    
    def mark_refresh_needed(self):
        global _last_refresh_time
        self.refresh_needed = True
        _last_refresh_time = time.time()
    
    def refresh_tables_if_needed(self):
        if self.refresh_needed:
            self.refresh_all_tables()
            self.refresh_needed = False
    
    def refresh_all_tables(self):
        self.refresh_detailed_table()
        self.refresh_browsers_table()
        self.refresh_apps_table()
        self.refresh_recycle_table()
        self.refresh_category_totals_table()
    
    def refresh_browsers_table(self):
        records, total_pages, total_records = self.tracker.get_paginated_summary(
            self.browsers_page, self.browsers_page_size, browser_only=True)
        print("BROWSERS: total_pages:", total_pages, "total_records:", total_records)
        self.browsers_pagination.update_pagination(self.browsers_page, total_pages)
        headers = ['Sekme', 'Kategori', 'Oturum', 'Toplam Süre', 'İndirilen', 'Yüklenen',
                  'Tuş', 'Disk', 'Sol Tık', 'Sağ Tık', 'Orta Tık']
        self.table_browsers.setRowCount(len(records) + 1)
        self.table_browsers.setColumnCount(len(headers))
        self.table_browsers.setHorizontalHeaderLabels(headers)
        # Toplamlar için değişkenler
        total_sessions = total_duration = total_downloads = total_uploads = 0
        total_keys = total_disk = total_left = total_right = total_middle = 0
        for i, row in enumerate(records):
            # row: (tab, category, sessions, total_duration, ...)
            for j, val in enumerate(row):
                if j == 2: total_sessions += val or 0
                if j == 3: total_duration += val or 0
                if j == 4: total_downloads += val or 0
                if j == 5: total_uploads += val or 0
                if j == 6: total_keys += val or 0
                if j == 7: total_disk += val or 0
                if j == 8: total_left += val or 0
                if j == 9: total_right += val or 0
                if j == 10: total_middle += val or 0
                if j == 3:  # Total duration
                    hours = int(val // 3600)
                    minutes = int((val % 3600) // 60)
                    val_str = f"{hours}h {minutes}m"
                elif j in [4, 5, 7]:  # Download, upload, disk columns
                    val_str = format_bytes(val) if val else "0 B"
                else:
                    val_str = str(val) if val else ""
                self.table_browsers.setItem(i, j, QtWidgets.QTableWidgetItem(val_str))
        # Toplam satırı
        total_row = len(records)
        self.table_browsers.setItem(total_row, 0, QtWidgets.QTableWidgetItem("TOPLAM"))
        self.table_browsers.setItem(total_row, 1, QtWidgets.QTableWidgetItem(""))
        self.table_browsers.setItem(total_row, 2, QtWidgets.QTableWidgetItem(""))
        self.table_browsers.setItem(total_row, 3, QtWidgets.QTableWidgetItem(str(total_sessions)))
        hours = int(total_duration // 3600)
        minutes = int((total_duration % 3600) // 60)
        self.table_browsers.setItem(total_row, 4, QtWidgets.QTableWidgetItem(f"{hours}h {minutes}m"))
        self.table_browsers.setItem(total_row, 5, QtWidgets.QTableWidgetItem(format_bytes(total_downloads)))
        self.table_browsers.setItem(total_row, 6, QtWidgets.QTableWidgetItem(format_bytes(total_uploads)))
        self.table_browsers.setItem(total_row, 7, QtWidgets.QTableWidgetItem(str(total_keys)))
        self.table_browsers.setItem(total_row, 8, QtWidgets.QTableWidgetItem(format_bytes(total_disk)))
        self.table_browsers.setItem(total_row, 9, QtWidgets.QTableWidgetItem(str(total_left)))
        self.table_browsers.setItem(total_row, 10, QtWidgets.QTableWidgetItem(str(total_right)))
        self.table_browsers.setItem(total_row, 11, QtWidgets.QTableWidgetItem(str(total_middle)))
        self.table_browsers.resizeColumnsToContents()
        self.tabs.setTabText(1, f'Tarayıcılar ({total_records})')
    
    def refresh_apps_table(self):
        records, total_pages, total_records = self.tracker.get_paginated_summary(
            self.apps_page, self.apps_page_size, browser_only=False)
        self.apps_pagination.update_pagination(self.apps_page, total_pages)
        headers = ['Uygulama', 'Kategori', 'Oturum', 'Toplam Süre', 'İndirilen', 'Yüklenen',
                  'Tuş', 'Disk', 'Sol Tık', 'Sağ Tık', 'Orta Tık']
        self.table_apps.setRowCount(len(records) + 1)
        self.table_apps.setColumnCount(len(headers))
        self.table_apps.setHorizontalHeaderLabels(headers)
        # Toplamlar için değişkenler
        total_sessions = total_duration = total_downloads = total_uploads = 0
        total_keys = total_disk = total_left = total_right = total_middle = 0
        for i, row in enumerate(records):
            for j, val in enumerate(row):
                if j == 2: total_sessions += val or 0
                if j == 3: total_duration += val or 0
                if j == 4: total_downloads += val or 0
                if j == 5: total_uploads += val or 0
                if j == 6: total_keys += val or 0
                if j == 7: total_disk += val or 0
                if j == 8: total_left += val or 0
                if j == 9: total_right += val or 0
                if j == 10: total_middle += val or 0
                if j == 3:  # Total duration
                    hours = int(val // 3600)
                    minutes = int((val % 3600) // 60)
                    val_str = f"{hours}h {minutes}m"
                elif j in [4, 5, 7]:  # Download, upload, disk columns
                    val_str = format_bytes(val) if val else "0 B"
                else:
                    val_str = str(val) if val else ""
                self.table_apps.setItem(i, j, QtWidgets.QTableWidgetItem(val_str))
        # Toplam satırı
        total_row = len(records)
        self.table_apps.setItem(total_row, 0, QtWidgets.QTableWidgetItem("TOPLAM"))
        self.table_apps.setItem(total_row, 1, QtWidgets.QTableWidgetItem(""))
        self.table_apps.setItem(total_row, 2, QtWidgets.QTableWidgetItem(""))
        self.table_apps.setItem(total_row, 3, QtWidgets.QTableWidgetItem(str(total_sessions)))
        hours = int(total_duration // 3600)
        minutes = int((total_duration % 3600) // 60)
        self.table_apps.setItem(total_row, 4, QtWidgets.QTableWidgetItem(f"{hours}h {minutes}m"))
        self.table_apps.setItem(total_row, 5, QtWidgets.QTableWidgetItem(format_bytes(total_downloads)))
        self.table_apps.setItem(total_row, 6, QtWidgets.QTableWidgetItem(format_bytes(total_uploads)))
        self.table_apps.setItem(total_row, 7, QtWidgets.QTableWidgetItem(str(total_keys)))
        self.table_apps.setItem(total_row, 8, QtWidgets.QTableWidgetItem(format_bytes(total_disk)))
        self.table_apps.setItem(total_row, 9, QtWidgets.QTableWidgetItem(str(total_left)))
        self.table_apps.setItem(total_row, 10, QtWidgets.QTableWidgetItem(str(total_right)))
        self.table_apps.setItem(total_row, 11, QtWidgets.QTableWidgetItem(str(total_middle)))
        self.table_apps.resizeColumnsToContents()
        self.tabs.setTabText(2, f'Uygulamalar ({total_records})')
    
    def refresh_detailed_table(self):
        records, total_pages, total_records = self.tracker.get_paginated_records(
            self.detailed_page, self.detailed_page_size, browser_exclude=True)
        self.detailed_pagination.update_pagination(self.detailed_page, total_pages)
        headers = ['#', 'Uygulama', 'Başlama', 'Bitiş', 'Süre (sn)', 'İndirilen', 'Yüklenen',
                  'Tuş', 'Disk', 'Sol Tık', 'Sağ Tık', 'Orta Tık', 'Kategori']
        self.table1.setRowCount(len(records) + 1)
        self.table1.setColumnCount(len(headers))
        self.table1.setHorizontalHeaderLabels(headers)
        # Toplamlar için değişkenler
        total_duration = total_downloads = total_uploads = 0
        total_keys = total_disk = total_left = total_right = total_middle = 0
        for i, row in enumerate(records):
            row_number = total_records - ((self.detailed_page - 1) * self.detailed_page_size + i)
            for j, val in enumerate(row[:13]):  # Only show first 13 columns
                if j == 0:
                    val = row_number  # Show correct row number (newest=1, oldest=total_records)
                elif j == 4:  # Duration column
                    total_duration += row[4] or 0
                    val = f"{val:.1f}" if val else "0.0"
                elif j == 5:  # Download
                    total_downloads += row[5] or 0
                    val = format_bytes(val) if val else "0 B"
                elif j == 6:  # Upload
                    total_uploads += row[6] or 0
                    val = format_bytes(val) if val else "0 B"
                elif j == 7:  # Key
                    total_keys += row[7] or 0
                elif j == 8:  # Disk
                    total_disk += row[8] or 0
                    val = format_bytes(val) if val else "0 B"
                elif j == 9:  # Left
                    total_left += row[9] or 0
                elif j == 10:  # Right
                    total_right += row[10] or 0
                elif j == 11:  # Middle
                    total_middle += row[11] or 0
                self.table1.setItem(i, j, QtWidgets.QTableWidgetItem(str(val) if val else ""))
        # Toplam satırı
        total_row = len(records)
        self.table1.setItem(total_row, 0, QtWidgets.QTableWidgetItem("TOPLAM"))
        for j in range(1, len(headers)):
            if j == 4:
                self.table1.setItem(total_row, j, QtWidgets.QTableWidgetItem(f"{total_duration:.1f}"))
            elif j == 5:
                self.table1.setItem(total_row, j, QtWidgets.QTableWidgetItem(format_bytes(total_downloads)))
            elif j == 6:
                self.table1.setItem(total_row, j, QtWidgets.QTableWidgetItem(format_bytes(total_uploads)))
            elif j == 7:
                self.table1.setItem(total_row, j, QtWidgets.QTableWidgetItem(str(total_keys)))
            elif j == 8:
                self.table1.setItem(total_row, j, QtWidgets.QTableWidgetItem(format_bytes(total_disk)))
            elif j == 9:
                self.table1.setItem(total_row, j, QtWidgets.QTableWidgetItem(str(total_left)))
            elif j == 10:
                self.table1.setItem(total_row, j, QtWidgets.QTableWidgetItem(str(total_right)))
            elif j == 11:
                self.table1.setItem(total_row, j, QtWidgets.QTableWidgetItem(str(total_middle)))
            else:
                self.table1.setItem(total_row, j, QtWidgets.QTableWidgetItem(""))
        self.table1.resizeColumnsToContents()
        self.tabs.setTabText(0, f'Detaylı ({total_records})')
    
    def refresh_recycle_table(self):
        records, total_pages, total_records = self.tracker.get_paginated_records(
            self.recycle_page, self.recycle_page_size, show_deleted=True)
        self.recycle_pagination.update_pagination(self.recycle_page, total_pages)
        headers = ['ID', 'Uygulama', 'Başlama', 'Bitiş', 'Süre (sn)', 'İndirilen', 'Yüklenen',
                  'Tuş', 'Disk', 'Sol Tık', 'Sağ Tık', 'Orta Tık', 'Kategori', 'Silinme Tarihi']
        self.table3.setRowCount(len(records) + 1)
        self.table3.setColumnCount(len(headers))
        self.table3.setHorizontalHeaderLabels(headers)
        # Toplamlar için değişkenler
        total_duration = total_downloads = total_uploads = 0
        total_keys = total_disk = total_left = total_right = total_middle = 0
        for i, row in enumerate(records):
            for j in range(len(headers)):
                if j < 13:  # Regular columns
                    val = row[j]
                    if j == 4:  # Duration column
                        total_duration += row[4] or 0
                        val = f"{val:.1f}" if val else "0.0"
                    elif j == 5:  # Download
                        total_downloads += row[5] or 0
                        val = format_bytes(val) if val else "0 B"
                    elif j == 6:  # Upload
                        total_uploads += row[6] or 0
                        val = format_bytes(val) if val else "0 B"
                    elif j == 7:  # Key
                        total_keys += row[7] or 0
                    elif j == 8:  # Disk
                        total_disk += row[8] or 0
                        val = format_bytes(val) if val else "0 B"
                    elif j == 9:  # Left
                        total_left += row[9] or 0
                    elif j == 10:  # Right
                        total_right += row[10] or 0
                    elif j == 11:  # Middle
                        total_middle += row[11] or 0
                    self.table3.setItem(i, j, QtWidgets.QTableWidgetItem(str(val) if val else ""))
                elif j == 13:  # Deleted date column
                    deleted_date = row[14] if len(row) > 14 else ""
                    self.table3.setItem(i, j, QtWidgets.QTableWidgetItem(str(deleted_date)))
        # Toplam satırı
        total_row = len(records)
        self.table3.setItem(total_row, 0, QtWidgets.QTableWidgetItem("TOPLAM"))
        for j in range(1, len(headers)):
            if j == 4:
                self.table3.setItem(total_row, j, QtWidgets.QTableWidgetItem(f"{total_duration:.1f}"))
            elif j == 5:
                self.table3.setItem(total_row, j, QtWidgets.QTableWidgetItem(format_bytes(total_downloads)))
            elif j == 6:
                self.table3.setItem(total_row, j, QtWidgets.QTableWidgetItem(format_bytes(total_uploads)))
            elif j == 7:
                self.table3.setItem(total_row, j, QtWidgets.QTableWidgetItem(str(total_keys)))
            elif j == 8:
                self.table3.setItem(total_row, j, QtWidgets.QTableWidgetItem(format_bytes(total_disk)))
            elif j == 9:
                self.table3.setItem(total_row, j, QtWidgets.QTableWidgetItem(str(total_left)))
            elif j == 10:
                self.table3.setItem(total_row, j, QtWidgets.QTableWidgetItem(str(total_right)))
            elif j == 11:
                self.table3.setItem(total_row, j, QtWidgets.QTableWidgetItem(str(total_middle)))
            else:
                self.table3.setItem(total_row, j, QtWidgets.QTableWidgetItem(""))
        self.table3.resizeColumnsToContents()
        self.tabs.setTabText(4, f'🗑️ Geri Dönüşüm Kutusu ({total_records})')
    
    def on_detailed_page_changed(self, page):
        self.detailed_page = page
        self.refresh_detailed_table()
    
    def on_detailed_page_size_changed(self, page_size):
        self.detailed_page_size = page_size
        self.detailed_page = 1  # Reset to first page
        self.refresh_detailed_table()
    
    def on_browsers_page_changed(self, page):
        self.browsers_page = page
        self.refresh_browsers_table()
    
    def on_browsers_page_size_changed(self, page_size):
        self.browsers_page_size = page_size
        self.browsers_page = 1
        self.refresh_browsers_table()
    
    def on_apps_page_changed(self, page):
        self.apps_page = page
        self.refresh_apps_table()
    
    def on_apps_page_size_changed(self, page_size):
        self.apps_page_size = page_size
        self.apps_page = 1
        self.refresh_apps_table()
    
    def on_recycle_page_changed(self, page):
        self.recycle_page = page
        self.refresh_recycle_table()
    
    def on_recycle_page_size_changed(self, page_size):
        self.recycle_page_size = page_size
        self.recycle_page = 1  # Reset to first page
        self.refresh_recycle_table()
    
    def delete_current_selection(self):
        """Delete selected records based on current tab"""
        current_tab = self.tabs.currentIndex()
        if current_tab == 0:  # Detailed tab
            self.delete_selected_detailed()
        # Add other tabs if needed
    
    def delete_selected_detailed(self):
        """Delete selected records from detailed table"""
        selected_rows = set()
        for item in self.table1.selectedItems():
            selected_rows.add(item.row())
        
        if not selected_rows:
            QMessageBox.information(self, "Bilgi", "Lütfen silinecek kayıtları seçin.")
            return
        
        reply = QMessageBox.question(self, "Onay", 
                                   f"{len(selected_rows)} kayıt geri dönüşüm kutusuna taşınacak. Devam edilsin mi?",
                                   QMessageBox.Yes | QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            # Get record IDs
            record_ids = []
            for row in sorted(selected_rows):
                id_item = self.table1.item(row, 0)  # ID column
                if id_item:
                    record_ids.append(int(id_item.text()))
            
            self.tracker.soft_delete_records(record_ids)
            self.refresh_all_tables()
            QMessageBox.information(self, "Başarılı", f"{len(record_ids)} kayıt geri dönüşüm kutusuna taşındı.")
    
    def restore_selected(self):
        """Restore selected records from recycle bin"""
        selected_rows = set()
        for item in self.table3.selectedItems():
            selected_rows.add(item.row())
        
        if not selected_rows:
            QMessageBox.information(self, "Bilgi", "Lütfen geri yüklenecek kayıtları seçin.")
            return
        
        # Get record IDs
        record_ids = []
        for row in sorted(selected_rows):
            id_item = self.table3.item(row, 0)  # ID column
            if id_item:
                record_ids.append(int(id_item.text()))
        
        self.tracker.restore_records(record_ids)
        self.refresh_all_tables()
        QMessageBox.information(self, "Başarılı", f"{len(record_ids)} kayıt geri yüklendi.")
    
    def permanent_delete_selected(self):
        """Permanently delete selected records"""
        selected_rows = set()
        for item in self.table3.selectedItems():
            selected_rows.add(item.row())
        
        if not selected_rows:
            QMessageBox.information(self, "Bilgi", "Lütfen kalıcı olarak silinecek kayıtları seçin.")
            return
        
        reply = QMessageBox.question(self, "⚠️ Uyarı", 
                                   f"{len(selected_rows)} kayıt kalıcı olarak silinecek. Bu işlem geri alınamaz!\n\nDevam edilsin mi?",
                                   QMessageBox.Yes | QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            # Get record IDs
            record_ids = []
            for row in sorted(selected_rows):
                id_item = self.table3.item(row, 0)  # ID column
                if id_item:
                    record_ids.append(int(id_item.text()))
            
            self.tracker.permanently_delete_records(record_ids)
            self.refresh_all_tables()
            QMessageBox.information(self, "Başarılı", f"{len(record_ids)} kayıt kalıcı olarak silindi.")
    
    def empty_recycle_bin(self):
        """Empty entire recycle bin"""
        reply = QMessageBox.question(self, "⚠️ Kritik Uyarı", 
                                   "Geri dönüşüm kutusundaki TÜM kayıtlar kalıcı olarak silinecek!\n\nBu işlem geri alınamaz!\n\nDevam edilsin mi?",
                                   QMessageBox.Yes | QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            self.tracker.empty_recycle_bin()
            self.refresh_all_tables()
            QMessageBox.information(self, "Başarılı", "Geri dönüşüm kutusu boşaltıldı.")
    
    def categorize_selected_apps(self):
        """Categorize selected applications (works in browsers and applications summary tabs)"""
        tab_idx = self.tabs.currentIndex()
        if tab_idx not in [1, 2]:  # Only in browsers or applications summary tabs
            return
        if tab_idx == 1:
            table = self.table_browsers
            # For browsers, app name is in column 0, tab title in column 1
            get_app_name = lambda row: table.item(row, 0).text() if table.item(row, 0) else None
        elif tab_idx == 2:
            table = self.table_apps
            # For applications, app name is in column 0
            get_app_name = lambda row: table.item(row, 0).text() if table.item(row, 0) else None
        selected_rows = set()
        for item in table.selectedItems():
            selected_rows.add(item.row())
        if not selected_rows:
            QMessageBox.information(self, "Bilgi", "Lütfen kategorilendirmek istediğiniz uygulamaları seçin.")
            return
        # Get all categories
        categories = self.tracker.get_all_categories()
        categories.append("Yeni Kategori Oluştur...")
        category, ok = QInputDialog.getItem(self, "Kategori Seç", "Kategori seçin:", categories, 0, False)
        if not ok:
            return
        if category == "Yeni Kategori Oluştur...":
            new_category, ok = QInputDialog.getText(self, "Yeni Kategori", "Kategori adı:")
            if not ok or not new_category.strip():
                return
            category = new_category.strip()
        # Get selected app names and update their categories
        updated_apps = []
        for row in sorted(selected_rows):
            app_name = get_app_name(row)
            if app_name:
                self.tracker.set_app_category(app_name, category)
                updated_apps.append(app_name)
        self.refresh_all_tables()
        QMessageBox.information(self, "Başarılı", f"{len(updated_apps)} uygulama '{category}' kategorisine atandı.")

if __name__ == "__main__":
    try:
        app = QtWidgets.QApplication(sys.argv)
        window = MainWindow()
        window.show()
        sys.exit(app.exec_())
    except Exception as e:
        import traceback
        print("Fatal error:", e)
        traceback.print_exc()
        input("Press Enter to exit...")
