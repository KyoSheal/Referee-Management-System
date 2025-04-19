from pathlib import Path
import sys
import sqlite3
from datetime import datetime, timedelta
import re
import dateparser
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QTextEdit, QPushButton, QMessageBox,
    QTabWidget, QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QCalendarWidget, QFormLayout
)
from qt_material import apply_stylesheet
from PySide6.QtGui import QTextCharFormat, QColor
from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QDoubleSpinBox
from PySide6.QtCore import QLocale
from PySide6.QtWidgets import QCheckBox, QHBoxLayout
from PySide6.QtCore import Qt
# ---------- Database ----------
def init_db():
    conn = sqlite3.connect('matches.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS matches
                      (id INTEGER PRIMARY KEY, league TEXT, role TEXT, subject TEXT, content TEXT,
                      date TEXT, start_time TEXT, end_time TEXT, location TEXT, amount REAL)''')
    conn.commit()
    conn.close()

def update_db_structure():
    conn = sqlite3.connect('matches.db')
    cursor = conn.cursor()
    try:
        cursor.execute('ALTER TABLE matches ADD COLUMN amount REAL')
        conn.commit()
    except sqlite3.OperationalError:
        pass
    conn.close()

def check_time_conflict(date, start_time, end_time):
    conn = sqlite3.connect('matches.db')
    cursor = conn.cursor()
    cursor.execute("SELECT start_time, end_time FROM matches WHERE date=?", (date,))
    existing_matches = cursor.fetchall()
    conn.close()

    new_start = datetime.strptime(start_time, '%H:%M')
    new_end = datetime.strptime(end_time, '%H:%M')

    for existing_start_str, existing_end_str in existing_matches:
        existing_start = datetime.strptime(existing_start_str, '%H:%M')
        existing_end = datetime.strptime(existing_end_str, '%H:%M')
        if new_start < existing_end and new_end > existing_start:
            return True
    return False

def add_matches_to_db(matches):
    conn = sqlite3.connect("matches.db")
    cursor = conn.cursor()
    for match in matches:
        cursor.execute(
            '''INSERT INTO matches (league, role, subject, content, date, start_time, end_time, location, amount)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (match['league'], match['role'], match['match_name'], f"{match['match_name']} details",
             match['date'], match['start_time'], match['end_time'], match['location'], 0))
    conn.commit()
    conn.close()

# ---------- Parsers ----------
def parse_text_to_match_data(text):
    if "Schedule date/time" in text:
        return [parse_spappz_format(text)]
    elif "appointed as" in text and "Match Date" in text:
        return parse_comet_format(text) 
    elif "Referee:" in text or "Assistant Referee" in text:
        return parse_assignr_format(text)
    return []

def parse_spappz_format(text):
    role = re.search(r"Role:\s*(.*)", text).group(1)
    division = re.search(r"Division:\s*(.*)", text).group(1)
    schedule = re.search(r"Schedule date/time:\s*(.*)", text).group(1)
    field_name = re.search(r"Field Name:\s*(.*)", text).group(1)
    city = re.search(r"City:\s*(.*)", text).group(1)
    home_team = re.search(r"Home Team:\s*(.*)", text).group(1)
    visiting_team = re.search(r"Visiting Team:\s*(.*)", text).group(1)

    dt = dateparser.parse(schedule)
    date = dt.strftime("%Y-%m-%d")
    start_time = dt.strftime("%H:%M")
    end_time = (dt + timedelta(minutes=100)).strftime("%H:%M")
    match_name = f"{home_team} vs {visiting_team}"
    role = "AR" if "Assistant" in role else "Referee"
    return {
        "league": division, "role": role, "match_name": match_name,
        "date": date, "start_time": start_time, "end_time": end_time,
        "location": f"{field_name}, {city}"
    }   

def parse_comet_format(text):
    try:
        text = text.replace('\xa0', ' ').replace('\u200b', '').replace('\r\n', '\n')

        role_match = re.search(r"appointed as (.*?) of the match", text)
        match_teams = re.search(r"of the match (.*?) and the status", text)
        match_date = re.search(r"Match Date:\s*(\d{2}\.\d{2}\.\d{4}) (\d{2}:\d{2})", text)
        stadium = re.search(r"Stadium:\s*(.*?)\s*\(", text)
        city = re.search(r"Stadium:.*\((.*?)\)", text)
        league = re.search(r"Competition:\s*(.*)", text)

        if not all([role_match, match_teams, match_date, stadium, city, league]):
            return []  

        role_raw = role_match.group(1).strip().lower()
        if "4th official" in role_raw:
            role = "4th"
        elif "assistant" in role_raw:
            role = "AR"
        elif "referee" in role_raw:
            role = "Referee"
        else:
            role = "Official"

        teams = match_teams.group(1).strip().split(" - ")
        match_name = f"{teams[0].strip()} vs {teams[1].strip() if len(teams) > 1 else 'TBD'}"
        date = datetime.strptime(match_date.group(1), "%d.%m.%Y").strftime("%Y-%m-%d")
        start_time = match_date.group(2)
        end_time = (datetime.strptime(start_time, "%H:%M") + timedelta(minutes=100)).strftime("%H:%M")
        location = f"{stadium.group(1).strip()}, {city.group(1).strip()}"

        return [{
            "league": league.group(1).strip(),
            "role": role,
            "match_name": match_name,
            "date": date,
            "start_time": start_time,
            "end_time": end_time,
            "location": location
        }]
    except Exception as e:
        print("❌ parse_comet_format error:", e)
        return []

def parse_assignr_format(text):
    matches = []
    try:
        role_lines =  re.findall(r"(Referee|Assistant Referee(?: \s*\d*)?):\s*(.*?)\s*@\s*(.+)", text)
        desc_lines = re.findall(r"#(.*)", text)
        for i, (role_label, dt_str, location) in enumerate(role_lines):
            if i >= len(desc_lines):
                continue

            details = desc_lines[i]
            dt = dateparser.parse(dt_str)
            if not dt:
                continue
            print(f"✔ Extracted location: '{location}'")
            half_duration = 45
            halftime_break = 10
            duration_match = re.search(r"Two x (\d+)min/(\d+)min HT", details)
            if duration_match:
                half_duration = int(duration_match.group(1))
                halftime_break = int(duration_match.group(2))

            total_minutes = 2 * half_duration + halftime_break
            date = dt.strftime("%Y-%m-%d")
            start_time = dt.strftime("%H:%M")
            end_time = (dt + timedelta(minutes=total_minutes)).strftime("%H:%M")

            role = "AR" if "Assistant" in role_label else "Referee"

            league_match = re.search(r"U\d{2}(?:\s*[A-Z0-9]*)", details)
            league = f"BCCSL {league_match.group(0).replace(' ', '').upper()}" if league_match else "BCCSL Unknown"
            match_name = f"{role_label} @ {league}"
            matches.append({
                "league": league,
                "role": role,
                "match_name": match_name,
                "date": date,
                "start_time": start_time,
                "end_time": end_time,
                "location": location.strip() if location else ""
            })

    except Exception as e:
        print(f"❌ Assignr parsing failed: {e}")
    return matches

# ---------- Tabs ----------
class AutoTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        self.text_input = QTextEdit()
        self.button = QPushButton("Parse and Add")
        self.button.clicked.connect(self.parse_and_add)
        layout.addWidget(QLabel("Paste match text:"))
        layout.addWidget(self.text_input)
        layout.addWidget(self.button)

    def parse_and_add(self):
        text = self.text_input.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Warning", "No text provided.")
            return

        text = text.replace('\xa0', ' ')
        text = text.replace('\u200b', '')
        text = text.replace('\r\n', '\n')

        matches = parse_text_to_match_data(text)
        if not matches:
            QMessageBox.critical(self, "Error", "Failed to parse match info.")
            return

        added = 0
        for match in matches:
            if check_time_conflict(match['date'], match['start_time'], match['end_time']):
                QMessageBox.warning(self, "Conflict", f"Time conflict for {match['match_name']}")
                continue
            add_matches_to_db([match])
            added += 1

        QMessageBox.information(self, "Success", f"Added {added} match(es).")
        self.text_input.clear()
        if hasattr(self, 'calendar_tab'):
            self.calendar_tab.highlight_match_dates()
            self.calendar_tab.refresh_table()

class AddMatchTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QFormLayout(self)
        self.inputs = {}
        for label in ["League", "Role", "Match Name", "Date (YYYY-MM-DD)", "Start Time (HH:MM)", "End Time", "Location", "Amount"]:
            entry = QLineEdit()
            layout.addRow(QLabel(label), entry)
            self.inputs[label] = entry
        self.add_button = QPushButton("Add Match")
        self.add_button.clicked.connect(self.add_manual)
        layout.addWidget(self.add_button)

    def add_manual(self):
        data = {k: f.text() for k, f in self.inputs.items()}
        if check_time_conflict(data["Date (YYYY-MM-DD)"], data["Start Time (HH:MM)"], data["End Time"]):
            QMessageBox.warning(self, "Conflict", "Time conflict detected.")
            return
        conn = sqlite3.connect("matches.db")
        cur = conn.cursor()
        cur.execute('''INSERT INTO matches (league, role, subject, content, date, start_time, end_time, location, amount)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    (data["League"], data["Role"], data["Match Name"], data["Match Name"] + " details",
                    data["Date (YYYY-MM-DD)"], data["Start Time (HH:MM)"], data["End Time"], data["Location"], float(data["Amount"] or 0)))
        conn.commit()
        conn.close()
        QMessageBox.information(self, "Success", "Match added.")

        if hasattr(self, 'calendar_tab'):
            self.calendar_tab.highlight_match_dates()
            self.calendar_tab.refresh_table()
            self.highlight_match_dates()

class CustomCalendar(QCalendarWidget):
    def __init__(self):
        super().__init__()
        self.marked_dates = set()

    def mark_dates(self, dates):
        self.marked_dates = set(dates)
        self.updateCells()

    def paintCell(self, painter, rect, date):
        super().paintCell(painter, rect, date)

        if date.toString("yyyy-MM-dd") in self.marked_dates:
            painter.setBrush(QColor("#ff4444"))  # Red
            painter.setPen(Qt.NoPen)
            radius = 4
            center_x = rect.center().x()
            center_y = rect.bottom() - radius - 5
            painter.drawEllipse(center_x - radius, center_y - radius, radius * 2, radius * 2)


class CalendarTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        self.calendar = CustomCalendar()
        self.calendar.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        self.table = QTableWidget(0, 7)  
        self.table.setHorizontalHeaderLabels(["League", "Role", "Match", "Start", "End", "Location", "Amount"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive) 
        header.setStretchLastSection(True)
        self.table.cellDoubleClicked.connect(self.edit_match_dialog)
        layout.addWidget(self.calendar)
        layout.addWidget(self.table)
        self.calendar.setLocale(QLocale(QLocale.English))
        self.delete_button = QPushButton("Delete Selected Match")
        self.delete_button.clicked.connect(self.delete_selected)
        layout.addWidget(self.delete_button)
        self.setLayout(layout)
        self.calendar.selectionChanged.connect(self.refresh_table)

    def refresh_table(self):
        date = self.calendar.selectedDate().toString("yyyy-MM-dd")
        conn = sqlite3.connect("matches.db")
        cur = conn.cursor()
        cur.execute("SELECT league, role, subject, start_time, end_time, location, amount FROM matches WHERE date=?", (date,))
        rows = cur.fetchall()
        self.table.setRowCount(0)
        for row in rows:
            row_pos = self.table.rowCount()
            self.table.insertRow(row_pos)
            for i, val in enumerate(row):
                if i == 6:
                    val = f"${val:.2f}" 
                self.table.setItem(row_pos, i, QTableWidgetItem(str(val)))
        self.table.resizeColumnsToContents()
        conn.close()

    def highlight_match_dates(self):
        conn = sqlite3.connect("matches.db")
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT date FROM matches")
        dates = cur.fetchall()
        conn.close()
        date_keys = [date_str for (date_str,) in dates]
        self.calendar.mark_dates(date_keys)


    def delete_selected(self):
        selected = self.table.currentRow()
        if selected == -1:
            QMessageBox.warning(self, "No selection", "Select a match to delete.")
            return
        match = self.table.item(selected, 2).text()  # subject
        date = self.calendar.selectedDate().toString("yyyy-MM-dd")
        conn = sqlite3.connect("matches.db")
        cur = conn.cursor()
        cur.execute("DELETE FROM matches WHERE subject=? AND date=?", (match, date))
        conn.commit()
        conn.close()
        self.refresh_table()
        self.highlight_match_dates()
    
    def edit_match_dialog(self, row, column):
        match_name = self.table.item(row, 2).text()
        date = self.calendar.selectedDate().toString("yyyy-MM-dd")
        conn = sqlite3.connect("matches.db")
        cur = conn.cursor()
        cur.execute("SELECT * FROM matches WHERE subject=? AND date=?", (match_name, date))
        match = cur.fetchone()
        conn.close()
        if not match:
            QMessageBox.warning(self, "Error", "Match not found.")
            return
        dialog = QWidget()
        dialog.setWindowTitle("Edit Match")
        layout = QFormLayout(dialog)
        fields = {}
        labels = ["League", "Role", "Subject", "Date", "Start Time", "End Time", "Location", "Amount"]
        font = QFont("Segoe UI", 10)

        def create_entry(text, placeholder):
            entry = QLineEdit(text)
            entry.setPlaceholderText(placeholder)
            entry.setFont(font)
            return entry

        fields["League"] = create_entry(match[1], "e.g. BCSL U16M")
        fields["Role"] = create_entry(match[2], "Referee / AR")
        fields["Subject"] = create_entry(match[3], "Match title")
        fields["Date"] = create_entry(match[5], "YYYY-MM-DD")
        fields["Start Time"] = create_entry(match[6], "HH:MM")
        fields["End Time"] = create_entry(match[7], "HH:MM")
        fields["Location"] = create_entry(match[8], "Location name")
        fields["Amount"] = QLineEdit(str(match[9] if match[9] is not None else "0.00"))


        amount_spin = QDoubleSpinBox()
        amount_spin.setRange(0, 1000)
        amount_spin.setDecimals(2)
        amount_spin.setValue(float(match[9] if match[9] is not None else 0))
        amount_spin.setFont(font)
        fields["Amount"] = amount_spin

        for label, widget in fields.items():
            layout.addRow(QLabel(label), widget)
        

        def save_changes():
            data = {k: (v.value() if isinstance(v, QDoubleSpinBox) else v.text()) for k, v in fields.items()}
            try:
                data["Amount"] = float(data["Amount"])
            except ValueError:
                QMessageBox.warning(dialog, "Error", "Amount must be a number.")
                return
            conn = sqlite3.connect("matches.db")
            cur = conn.cursor()
            cur.execute('''UPDATE matches SET league=?, role=?, subject=?, date=?, start_time=?,
                        end_time=?, location=?, amount=? WHERE id=?''',
                        (data["League"], data["Role"], data["Subject"], data["Date"],
                        data["Start Time"], data["End Time"], data["Location"], data["Amount"], match[0]))
            conn.commit()
            conn.close()
            self.refresh_table()
            self.highlight_match_dates()
            if hasattr(self, 'stats_tab'):
                self.stats_tab.refresh()
            dialog.close()

        save_btn = QPushButton("Save")
        save_btn.clicked.connect(save_changes)
        layout.addWidget(save_btn)

        dialog.setLayout(layout)
        dialog.setFixedSize(400, 400)
        dialog.show()
    
    

class StatisticsTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        self.weekly = QTableWidget()
        self.monthly = QTableWidget()
        layout.addWidget(QLabel("Weekly Income"))
        layout.addWidget(self.weekly)
        layout.addWidget(QLabel("Monthly Income"))
        layout.addWidget(self.monthly)
        self.setLayout(layout)
        self.load_data()

    def load_data(self):
        conn = sqlite3.connect("matches.db")
        cur = conn.cursor()

        self.weekly.setColumnCount(2)
        self.weekly.setHorizontalHeaderLabels(["Week", "Total"])
        cur.execute("SELECT strftime('%Y-%W', date), SUM(amount) FROM matches GROUP BY 1")
        rows = cur.fetchall()
        self.weekly.setRowCount(0)
        for row in rows:
            self.weekly.insertRow(self.weekly.rowCount())
            self.weekly.setItem(self.weekly.rowCount() - 1, 0, QTableWidgetItem(row[0]))
            self.weekly.setItem(self.weekly.rowCount() - 1, 1, QTableWidgetItem(f"${row[1] or 0:.2f}"))

        self.monthly.setColumnCount(2)
        self.monthly.setHorizontalHeaderLabels(["Month", "Total"])
        cur.execute("SELECT strftime('%Y-%m', date), SUM(amount) FROM matches GROUP BY 1")
        rows = cur.fetchall()
        self.monthly.setRowCount(0)
        for row in rows:
            self.monthly.insertRow(self.monthly.rowCount())
            self.monthly.setItem(self.monthly.rowCount() - 1, 0, QTableWidgetItem(row[0]))
            self.monthly.setItem(self.monthly.rowCount() - 1, 1, QTableWidgetItem(f"${row[1] or 0:.2f}"))
        conn.close()

    def refresh(self):
        self.load_data()

# ---------- App ----------
class RefereeApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Referee Management System")
        self.resize(1000, 700)
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        self.auto_tab = AutoTab()
        self.calendar_tab = CalendarTab()
        self.add_tab = AddMatchTab()
        self.stats_tab = StatisticsTab()
        self.auto_tab.calendar_tab = self.calendar_tab
        self.add_tab.calendar_tab = self.calendar_tab
        self.calendar_tab.stats_tab = self.stats_tab
        self.theme_switch = QCheckBox("🌞 Light / Dark 🌚")
        self.theme_switch.setChecked(False)  # 默认浅色
        self.theme_switch.setCursor(Qt.PointingHandCursor)
        self.theme_switch.stateChanged.connect(self.toggle_theme)
        self.theme_switch.setStyleSheet("""
            QCheckBox {
                spacing: 10px;
            }
            QCheckBox::indicator {
                width: 50px;
                height: 25px;
                border-radius: 12px;
                background-color: #999;
                position: relative;
            }
            QCheckBox::indicator:checked {
                background-color: #00cc66;
            }
            QCheckBox::indicator::checked {
                background-color: #00cc66;
            }
        """)
        top_layout = QHBoxLayout()
        top_layout.addStretch()
        top_layout.addWidget(self.theme_switch)
        layout.addLayout(top_layout)
        tabs.addTab(self.auto_tab, "Auto")
        tabs.addTab(self.calendar_tab, "Calendar")
        tabs.addTab(self.add_tab, "Add Match")
        tabs.addTab(self.stats_tab, "Statistics")
        layout.addWidget(tabs)
        self.calendar_tab.highlight_match_dates()
        self.calendar_tab.refresh_table()
    
    def toggle_theme(self):
        if self.theme_switch.isChecked():
            apply_stylesheet(app, theme='dark_teal.xml')
        else:
            apply_stylesheet(app, theme='light_blue.xml')

if __name__ == "__main__":
    init_db()
    update_db_structure()
    app = QApplication(sys.argv)
    font = QFont("Segoe UI", 17)
    font.setBold(True)
    font.setStyleStrategy(QFont.PreferAntialias)
    app.setFont(font)
    apply_stylesheet(app, theme='light_blue.xml')
    window = RefereeApp()
    window.show()
    sys.exit(app.exec())