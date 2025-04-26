from pathlib import Path
import sys
import sqlite3
from datetime import datetime, timedelta
import re
import dateparser
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QTextEdit, QPushButton, QMessageBox,
    QTabWidget, QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QCalendarWidget, QFormLayout, QToolTip, QAbstractItemView, QCalendarWidget,
    QDoubleSpinBox, QCheckBox, QHBoxLayout, QComboBox, QTimeEdit, QSizePolicy
)
from PySide6.QtGui import QCursor
from qt_material import apply_stylesheet
from PySide6.QtGui import QTextCharFormat, QHelpEvent, QColor, QFont
from PySide6.QtCore import  QRect, QModelIndex, QPoint, QDate, Qt, QLocale
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

# === Referee Payment Rates ===
BCCR_RATES = {
    "BCCSL": {
        "Referee": {
            "U8": 20, "U9": 23, "U10": 25,
            "U11D3": 30, "U12D3": 30,
            "U11": 35, "U12": 35, "U13": 40,
            "U14": 65, "U15": 65, "U16": 65,
            "U17": 75, "U18": 75,
        },
        "AR": {
            "U14": 40, "U15": 40, "U16": 40,
            "U17": 45, "U18": 45,
        }
    },
    "BCSPL": {
        "Referee": {
            "U14": 65, "U15": 65, "U16": 65,
            "U17": 75, "U18": 75,
        },
        "AR": {
            "U14": 40, "U15": 40, "U16": 40,
            "U17": 50, "U18": 50,
        }
    }
}

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
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute('ALTER TABLE matches ADD COLUMN division TEXT')
    except sqlite3.OperationalError:
        pass
    conn.commit()
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
        amount = match.get('amount', 0.0)  # auto amount
        cursor.execute(
            '''INSERT INTO matches (league, role, subject, content, date, start_time, end_time, location, amount, division)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (match['league'], match['role'], match['match_name'], f"{match['match_name']} details",
            match['date'], match['start_time'], match['end_time'], match['location'], match.get('amount', 0.0), match.get('division', ''))
        )
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
    #elif "Game #" in text and "-v-" in text and ("BC Assignments" in text or "Canwest" in text):
    #    return parse_refcenter_format(text)
    return []

def parse_refcenter_format(text):       
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    merged_lines = []
    if len(lines) == 1:
        line = lines[0]
        try:
            #  League name
            league_match = re.search(r"(BC Assignments\s+)?(Canwest Women|BC Soccer)", line)
            league = league_match.group(2).strip() if league_match else "League"

            # match name
            match_match = re.search(r"Game #\d+\s+(.+?)\s+-v-\s+(.+?)\s+(.*?)\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)", line)
            if not match_match:
                raise ValueError("Match pattern not found")
            team1 = match_match.group(1).strip()
            team2 = match_match.group(2).strip()
            location = match_match.group(3).strip()

            # time
            date_match = re.search(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4}\s+at\s+\d{1,2}:\d{2}", line)
            dt_str = date_match.group(0) if date_match else None
            dt = dateparser.parse(dt_str)

            return [{
                "league": league,
                "role": "",
                "match_name": f"{team1} -v- {team2}",
                "date": dt.strftime("%Y-%m-%d"),
                "start_time": dt.strftime("%H:%M"),
                "end_time": (dt + timedelta(minutes=100)).strftime("%H:%M"),
                "location": location
            }]
        except Exception as e:
            print("❌ RefCenter parsing failed:", e)
            return []
    matches = []
    block = []
    for line in lines:
        if "Game #" in line and block:
            matches.append(block)
            block = []
        block.append(line)
    if block:
        matches.append(block)

    parsed = []
    for block in matches:
        try:
            if len(block) < 6:
                raise ValueError("Block too short")

            league = block[1].strip()
            match_name = block[3].strip()
            location = block[4].strip()
            dt = dateparser.parse(block[5].strip())

            parsed.append({
                "league": league,
                "role": "",
                "match_name": match_name,
                "date": dt.strftime("%Y-%m-%d"),
                "start_time": dt.strftime("%H:%M"),
                "end_time": (dt + timedelta(minutes=100)).strftime("%H:%M"),
                "location": location
            })
        except Exception as e:
            print("❌ RefCenter parsing error:", e, block)

    return parsed

def parse_spappz_format(text):
    role = re.search(r"Role:\s*(.*)", text).group(1)
    division = re.search(r"Division:\s*(.*)", text).group(1).strip()
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
    role_clean = "AR" if "Assistant" in role else "Referee"
    # 🏷️ League
    if "Metro Women's Soccer League" in text or "MWSL" in text:
        league = "MWSL"
    elif "Fraser Valley Soccer League" in text or "FVSL" in text:
        league = "FVSL"
    elif "Vancouver Metro Soccer League" in text or "VMSL" in text :
        league = "VMSL"
    else:
        league = "League"
    if any(kw in division for kw in ["Premier", "Imperial Cup", "Prime"]):
        amount = 110 if role_clean == "Referee" else 70
    else:
        amount = 100 if role_clean == "Referee" else 60
    return {
        "league": league,
        "division": division,
        "role": role_clean,
        "match_name": match_name,
        "date": date,
        "start_time": start_time,
        "end_time": end_time,
        "location": f"{field_name}, {city}",
        "amount": amount
    }

def parse_comet_format(text):
    try:
        text = text.replace('\xa0', ' ').replace('\u200b', '').replace('\r\n', '\n')
        print("Text:", text)
        role_match = re.search(r"appointed as (.*?) of the match", text)
        match_teams = re.search(r"of the match (.*?) and the status", text)
        match_date = re.search(r"Match Date:\s*(\d{2}\.\d{2}\.\d{4}) (\d{2}:\d{2})", text)
        stadium = re.search(r"Stadium:\s*(.*?)\s*\(", text)
        city = re.search(r"Stadium:.*\((.*?)\)", text)
        league_match = re.search(r"Competition:\s*(.*)", text)
        amount = 0.0  
        text = text.replace('\xa0', ' ').replace('\u200b', '').replace('\r\n', '\n')

        if not all([role_match, match_teams, match_date, stadium, city, league_match]):
            print("❌ Some parts missing in COMET match.")
            return []

        league_match = re.search(r"Competition:\s*(.*?)(?:\s*Comment:|$)", text)
        league_raw = league_match.group(1).strip()
        known_leagues = ["BCSPL", "BCCSL", "VMSL", "MWSL", "FVSL", "BC Soccer"]
        parts = league_raw.split()
        if len(parts) >= 2:
            candidate_league = " ".join(parts[:2])
            if candidate_league in known_leagues:
                league = candidate_league
                division = " ".join(parts[2:]).strip()
            elif parts[0] in known_leagues:
                league = parts[0]
                division = " ".join(parts[1:]).strip()
            else:
                league = league_raw
                division = ""
        else:
            league = league_raw
            division = ""

        # ✅ role
        role_raw = role_match.group(1).strip().lower()
        if "4th official" in role_raw:
            role = "4th"
        elif "assistant" in role_raw:
            role = "AR"
        elif "referee" in role_raw:
            role = "Referee"
        else:
            role = "Official"

        # ✅ match info 
        teams = match_teams.group(1).strip().split(" - ")
        match_name = f"{teams[0].strip()} vs {teams[1].strip() if len(teams) > 1 else 'TBD'}"

        # ✅ date and time
        date = datetime.strptime(match_date.group(1), "%d.%m.%Y").strftime("%Y-%m-%d")
        start_time = match_date.group(2)
        end_time = (datetime.strptime(start_time, "%H:%M") + timedelta(minutes=100)).strftime("%H:%M")

        # ✅ amount
        if "BC Soccer" in league and "Cup" in division:
            amount = 100 if role == "Referee" else 60
        elif "BCSPL" in league:
            division = league_raw.split()[-1]  # 例如 U16
            amount = infer_match_amount("BCSPL", role, division)

        return [{
            "league": league,
            "division": division,
            "role": role,
            "match_name": match_name,
            "date": date,
            "start_time": start_time,
            "end_time": end_time,
            "location": f"{stadium.group(1).strip()}, {city.group(1).strip()}",
            "amount": amount
        }]

    except Exception as e:
        print("❌ parse_comet_format error:", e)
        return []

def parse_assignr_format(text):
    import re
    matches = []
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    blocks = []
    current_block = []

    for line in lines:
        if re.match(r"(Referee|Assistant Referee(?: \d*)?):", line):
            if current_block:
                blocks.append(current_block)
                current_block = []
        current_block.append(line)
    if current_block:
        blocks.append(current_block)

    for block in blocks:
        try:
            header = block[0]
            desc_line = next((l for l in block if l.startswith("#")), "")
            details = desc_line.replace("#", "").strip()

            print("🧪 Raw details:", details)

            role_match = re.match(r"(Referee|Assistant Referee(?: \d*)?):\s*(.*?)\s*@\s*(.+)", header)
            if not role_match:
                print("❌ Invalid header:", header)
                continue

            role_label, dt_str, location = role_match.groups()
            dt = dateparser.parse(dt_str)
            if not dt:
                print("❌ Invalid datetime:", dt_str)
                continue

            # ⏱️ time
            half_duration = 45
            halftime_break = 10
            duration_match = re.search(r"Two x (\d+)min/(\d+)min HT", details)
            if duration_match:
                half_duration = int(duration_match.group(1))
                halftime_break = int(duration_match.group(2))

            total_minutes = 2 * half_duration + halftime_break
            start_time = dt.strftime("%H:%M")
            end_time = (dt + timedelta(minutes=total_minutes)).strftime("%H:%M")
            date = dt.strftime("%Y-%m-%d")

            role = "AR" if "Assistant" in role_label else "Referee"

            # BCCSL / BCSPL / League
            if "Cup" in details:
                cup_match = re.search(r"([ABC]) Cup", details)
                cup = cup_match.group(1) if cup_match else "Unknown"
                league = "BCCSL"
            else:
                league_match = re.search(r"\b([A-Z]+SPL|BCCSL)\b", details)
                league = league_match.group(1) if league_match else "League"

            div_match = re.search(r"U\s*(\d{2})\s*([A-Z0-9]+)?", details, re.IGNORECASE)
            if div_match:
                age = div_match.group(1)
                level = div_match.group(2) or ''
                level = re.sub(r'\W+', '', level)
                division = f"U{age}{level}"
            else:
                print("🧪 Division match: No match")
                division = "Unknown"

            if "Cup" in details:
                match_name = f"{league} {cup} Cup ({division})"
            else:
                match_name = f"{league} ({division})"
            amount = infer_match_amount(league, role, division)
            matches.append({
                "league": league,
                "division": division,
                "role": role,
                "match_name": match_name,
                "date": date,
                "start_time": start_time,
                "end_time": end_time,
                "location": location.strip(),
                "amount": amount
            })

        except Exception as e:
            print("❌ Assignr parsing failed:", e, block)

    return matches

def infer_match_amount(league, role, division):
    league = league.upper()
    role = role if role in ["Referee", "AR"] else "Referee"
    age_match = re.search(r"U(\d{2})", division.upper())
    if not age_match:
        return 0.0
    age = f"U{age_match.group(1)}"
    if "D3" in division.upper():
        age = age + "D3"

    rates = BCCR_RATES.get(league, {})
    role_rates = rates.get(role, {})
    return float(role_rates.get(age, 0.0))

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
        for label in ["League", "Role", "Match Name", "Date (YYYY-MM-DD)", "Start Time", "End Time", "Location", "Amount"]:
            if "Time" in label and "Date" not in label:  # 区分掉日期字段
                entry = QTimeEdit()
                entry.setDisplayFormat("HH:mm")
            else:
                entry = QLineEdit()
            layout.addRow(QLabel(label), entry)
            self.inputs[label] = entry
        self.add_button = QPushButton("Add Match")
        self.add_button.clicked.connect(self.add_manual)
        layout.addWidget(self.add_button)

    def add_manual(self):
        try:
            data = {}
            for key, widget in self.inputs.items():
                if isinstance(widget, QTimeEdit):
                    data[key] = widget.time().toString("HH:mm")
                else:
                    data[key] = widget.text()
            # ✅ data check
            date_str = data["Date (YYYY-MM-DD)"]
            date = QDate.fromString(date_str, "yyyy-MM-dd")
            if not date.isValid():
                QMessageBox.critical(self, "Error", f"Invalid date format: {date_str}")
                return
            # ✅ conflict check
            if check_time_conflict(data["Date (YYYY-MM-DD)"], data["Start Time"], data["End Time"]):
                QMessageBox.warning(self, "Conflict", "Time conflict detected.")
                return
            # ✅ into database
            conn = sqlite3.connect("matches.db")
            cur = conn.cursor()
            cur.execute('''INSERT INTO matches (league, role, subject, content, date, start_time, end_time, location, amount)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                        (data["League"], data["Role"], data["Match Name"], data["Match Name"] + " details",
                        data["Date (YYYY-MM-DD)"], data["Start Time"], data["End Time"], data["Location"],
                        float(data["Amount"] or 0)))
            conn.commit()
            conn.close()
            QMessageBox.information(self, "Success", "Match added.")
            if hasattr(self, 'calendar_tab'):
                self.calendar_tab.highlight_match_dates()
                self.calendar_tab.refresh_table()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to add match:\n{e}")

class CustomCalendar(QCalendarWidget):
    def __init__(self):
        super().__init__()
        self._last_tooltip_text = ''
        self.marked_dates = {}
        self.setMouseTracking(True)
        self.view = self.findChild(QAbstractItemView, "qt_calendar_calendarview")
        if self.view:
            print("✅ Calendar view found:", self.view)
        else:
            print("❌ Failed to find calendar view")
        if self.view:
            self.view.setMouseTracking(True)
            print("Mouse tracking enabled on calendar view")
    def enterEvent(self, event):
        print("Mouse entered calendar!")
        super().enterEvent(event)
    def mark_dates(self, dates_dict):
        self.marked_dates = dates_dict
        self.updateCells()

    def paintCell(self, painter, rect, date):
        super().paintCell(painter, rect, date)

        date_str = date.toString("yyyy-MM-dd")
        if date_str in self.marked_dates:
            painter.setBrush(QColor("#ff4444"))
            painter.setPen(Qt.NoPen)
            radius = 4
            center_x = rect.center().x()
            center_y = rect.bottom() - radius - 5
            painter.drawEllipse(center_x - radius, center_y - radius, radius * 2, radius * 2)

    def mouseMoveEvent(self, event):
        if not self.view:
            return super().mouseMoveEvent(event)
        try:
            pos_in_calendar = event.position().toPoint()
            global_pos = event.globalPosition().toPoint()
        except AttributeError:
            pos_in_calendar = event.pos()
            global_pos = event.globalPos()
        pos_in_view = self.view.viewport().mapFrom(self, pos_in_calendar)
        index = self.view.indexAt(pos_in_view)
        print("🧪 Hover index:", index.row(), index.column(), index.isValid())
        if index.isValid():
            date = self.dateForCell(index.row(), index.column())
            if date:
                date_str = date.toString("yyyy-MM-dd")
                print("📅 Inferred date:", date_str)
                if date_str in self.marked_dates:
                    matches = self.marked_dates[date_str]
                    tooltip = "\n".join(matches)
                    if getattr(self, '_last_tooltip_text', '') != tooltip:
                        font = QFont("Courier New") 
                        QToolTip.setFont(font)
                        QToolTip.showText(global_pos + QPoint(10, 20), tooltip, self.view)
                        self._last_tooltip_text = tooltip
                    return

                QToolTip.hideText()
                self._last_tooltip_text = ''
                super().mouseMoveEvent(event)

    def dateAt(self, pos: QPoint):
        if not hasattr(self, 'view') or self.view is None:  
            return None

        local_pos = self.mapTo(self.view, pos)
        index = self.view.indexAt(local_pos)
        if index.isValid():
            row = index.row()
            col = index.column()
            date = self.dateForCell(row, col)
            if isinstance(date, QDate):
                return date
        return None

    def dateForCell(self, row, col):
        if row < 1:
            return None 
        first_date = self.monthShownFirstDate()
        days_offset = (row - 1) * 7 + col
        return first_date.addDays(days_offset)

    def monthShownFirstDate(self):
        year = self.yearShown()
        month = self.monthShown()
        first_day_of_month = QDate(year, month, 1)
        day_offset = first_day_of_month.dayOfWeek() % 7  # Sun=7 → 0 offset, Mon=1 → 1 offset
        return first_day_of_month.addDays(-day_offset)

    def calendarHeaderHeight(self):
        return 40  

    def calendarCellHeight(self):
        return (self.height() - self.calendarHeaderHeight()) // 6


class CalendarTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        self.calendar = CustomCalendar()
        self.calendar.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        self.table = QTableWidget(0, 8)  
        self.table.setHorizontalHeaderLabels(["League", "Division", "Role", "Match", "Start", "End", "Location", "Amount"])
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
        self.status_label = QLabel("No matches selected")
        self.status_label.setStyleSheet("font-weight: bold; padding: 4px;")
        layout.addWidget(self.status_label)
        filter_layout = QHBoxLayout()
        self.role_filter = QComboBox()
        self.role_filter.addItem("All Roles")
        self.role_filter.addItem("Referee")
        self.role_filter.addItem("AR")
        self.role_filter.currentTextChanged.connect(self.refresh_table)
        self.league_filter = QComboBox()
        self.league_filter.addItem("All Leagues")
        self.league_filter.currentTextChanged.connect(self.refresh_table)
        filter_layout.addWidget(QLabel("Filter by Role:"))
        filter_layout.addWidget(self.role_filter)
        filter_layout.addWidget(QLabel("Filter by League:"))
        filter_layout.addWidget(self.league_filter)
        layout.addLayout(filter_layout)
        self.setLayout(layout)
        self.calendar.selectionChanged.connect(self.refresh_table)

    def refresh_table(self):
        date = self.calendar.selectedDate().toString("yyyy-MM-dd")
        role_filter = self.role_filter.currentText()
        league_filter = self.league_filter.currentText()
        conn = sqlite3.connect("matches.db")
        cur = conn.cursor()
        query = "SELECT league, division, role, subject, start_time, end_time, location, amount FROM matches WHERE date=?"
        params = [date]

        if role_filter != "All Roles":
            query += " AND role=?"
            params.append(role_filter)

        if league_filter != "All Leagues":
            query += " AND league=?"
            params.append(league_filter)

        cur.execute(query, params)
        rows = cur.fetchall()
        conn.close()
        self.table.setRowCount(0)
        for row in rows:
            row_pos = self.table.rowCount()
            self.table.insertRow(row_pos)
            for i, val in enumerate(row):
                if i == 7:
                    val = f"${val:.2f}"
                self.table.setItem(row_pos, i, QTableWidgetItem(str(val)))
        self.table.resizeColumnsToContents()
        self.status_label.setText(f"{len(rows)} match(es) on {date}")
        self.update_league_filter(date)
    
    def update_league_filter(self, date):
        conn = sqlite3.connect("matches.db")
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT league FROM matches WHERE date=?", (date,))
        leagues = sorted(set(row[0] for row in cur.fetchall()))
        conn.close()

        current = self.league_filter.currentText()
        self.league_filter.blockSignals(True)
        self.league_filter.clear()
        self.league_filter.addItem("All Leagues")
        for league in leagues:
            self.league_filter.addItem(league)
        self.league_filter.setCurrentText(current)
        self.league_filter.blockSignals(False)

    def highlight_match_dates(self):
        conn = sqlite3.connect("matches.db")
        cur = conn.cursor()
        cur.execute("SELECT date, league, role, division FROM matches")
        rows = cur.fetchall()
        conn.close()

        match_dict = {}
        for date_str, league, role, division in rows:
            division_display = division if division and division.lower() != "none" else ""
            line = f"{role:<8} | {league:<12} | {division_display}"
            match_dict.setdefault(date_str, []).append(line)
        self.calendar.mark_dates(match_dict)

    def delete_selected(self):
        selected = self.table.currentRow()
        if selected == -1:
            QMessageBox.warning(self, "No selection", "Select a match to delete.")
            return
        match = self.table.item(selected, 3).text()  # ✅ Match now at column 3
        date = self.calendar.selectedDate().toString("yyyy-MM-dd")
        conn = sqlite3.connect("matches.db")
        cur = conn.cursor()
        cur.execute("DELETE FROM matches WHERE subject=? AND date=?", (match, date))
        conn.commit()
        conn.close()
        self.refresh_table()
        self.highlight_match_dates()
    
    def edit_match_dialog(self, row, column):
        match_name = self.table.item(row, 3).text()
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
        dialog.setFixedSize(400, 500)
        dialog.show()
    
    
class StatisticsTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        # 📆 Monthly Income 表格 + 图表（缩窄表格、左对齐）
        self.monthly = QTableWidget()
        self.monthly.setFixedHeight(200)
        self.monthly.setMaximumWidth(350)
        self.monthly_chart = FigureCanvas(Figure(figsize=(5.5, 3.2)))
        monthly_layout = QHBoxLayout()
        monthly_layout.setSpacing(20)
        monthly_layout.setAlignment(Qt.AlignLeft)
        monthly_layout.addWidget(self.monthly)
        monthly_layout.addWidget(self.monthly_chart)
        layout.addWidget(QLabel("📆 Monthly Income"))
        layout.addLayout(monthly_layout)

        # 📌 年份选择 + 摘要
        self.year_selector = QComboBox()
        self.year_selector.currentTextChanged.connect(self.refresh)
        self.summary_label = QLabel()
        layout.addWidget(QLabel("📌 Select Year:"))
        layout.addWidget(self.year_selector)
        layout.addWidget(self.summary_label)

        # 💰 League 表格 + 图表（缩窄表格、左对齐）
        self.league_table = QTableWidget()
        self.league_table.setMinimumHeight(120)
        self.league_table.setMaximumWidth(350)
        self.league_chart = FigureCanvas(Figure(figsize=(5.5, 3.2)))
        league_layout = QHBoxLayout()
        league_layout.setSpacing(20)
        league_layout.setAlignment(Qt.AlignLeft)
        league_layout.addWidget(self.league_table)
        league_layout.addWidget(self.league_chart)
        layout.addWidget(self.bold_label("💰 By League"))
        layout.addLayout(league_layout)

        # 🎭 Role 表格 + 饼图（缩窄表格、左对齐、图表加高）
        self.role_table = QTableWidget()
        self.role_table.setMaximumWidth(350)
        #self.role_table.setMinimumHeight(120)
        self.role_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.role_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)  # ✅ 添加
        self.role_table.setMaximumHeight(1000)  # ✅ 添加

        self.role_chart = FigureCanvas(Figure(figsize=(5, 5)))
        self.role_chart.setMinimumHeight(400)
        self.role_chart.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        role_container = QWidget()
        role_layout = QHBoxLayout(role_container)
        role_layout.setContentsMargins(0, 0, 0, 0)
        role_layout.setSpacing(20)
        role_layout.addWidget(self.role_table)
        role_layout.addWidget(self.role_chart)

        role_container.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

        layout.addWidget(self.bold_label("🎭 By Role"))
        layout.addWidget(role_container)

        self.refresh()

    def auto_resize_table_height(self, table, row_height=30, max_height=300):
        rows = table.rowCount()
        height = min(row_height * (rows + 10), max_height)
        table.setFixedHeight(height)

    def bold_label(self, text):
        lbl = QLabel()
        lbl.setTextFormat(Qt.RichText)
        lbl.setText(f"<b>{text}</b>")
        return lbl

    def load_years(self):
        conn = sqlite3.connect("matches.db")
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT strftime('%Y', date) FROM matches")
        years = sorted(set(row[0] for row in cur.fetchall() if row[0]))
        conn.close()

        self.year_selector.blockSignals(True)
        self.year_selector.clear()
        self.year_selector.addItem("All")  # 默认值
        self.year_selector.addItems(years)
        self.year_selector.blockSignals(False)

    def get_year_filter(self):
        year = self.year_selector.currentText()
        if year == "All":
            return "", []
        else:
            return " AND strftime('%Y', date)=?", [year]
    

    def load_summary(self):
        year_filter, params = self.get_year_filter()
        conn = sqlite3.connect("matches.db")
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*), SUM(amount) FROM matches WHERE 1=1 {year_filter}", params)
        row = cur.fetchone()
        count = row[0] or 0
        total = row[1] or 0.0
        avg = (total / count) if count else 0.0
        self.summary_label.setText(f"📊 Total Matches: <b>{count}</b> | Total: <b>${total:.2f}</b> | Avg: <b>${avg:.2f}</b>")
        conn.close()
    
    def auto_resize_table_height(self, table, row_height=32, max_height=1000):
        rows = table.rowCount()
        height = min(row_height * rows + table.horizontalHeader().height() + 4, max_height)
        print(f"🪄 Final resize: {rows} rows -> height={height}")
        table.setFixedHeight(height)
            
    def load_league_stats(self):
        year_filter, params = self.get_year_filter()
        conn = sqlite3.connect("matches.db")
        cur = conn.cursor()
        cur.execute(f"SELECT league, SUM(amount) FROM matches WHERE 1=1 {year_filter} GROUP BY league", params)
        rows = cur.fetchall()
        conn.close()
        self.league_table.setColumnCount(2)
        self.league_table.setHorizontalHeaderLabels(["League", "Total"])
        self.league_table.setRowCount(0)
        self.auto_resize_table_height(self.league_table)
        for row in rows:
            self.league_table.insertRow(self.league_table.rowCount())
            self.league_table.setItem(self.league_table.rowCount() - 1, 0, QTableWidgetItem(row[0]))
            self.league_table.setItem(self.league_table.rowCount() - 1, 1, QTableWidgetItem(f"${row[1]:.2f}"))
        self.league_table.resizeColumnsToContents()
        self.auto_resize_table_height(self.league_table, row_height=32, max_height=1000)

    def load_role_stats(self):
        year_filter, params = self.get_year_filter()
        conn = sqlite3.connect("matches.db")
        cur = conn.cursor()
        cur.execute(f"SELECT role, SUM(amount) FROM matches WHERE 1=1 {year_filter} GROUP BY role", params)
        rows = cur.fetchall()
        conn.close()

        self.role_table.setColumnCount(2)
        self.role_table.setHorizontalHeaderLabels(["Role", "Total"])
        self.role_table.setRowCount(0)

        for role, total in rows:
            row_pos = self.role_table.rowCount()
            self.role_table.insertRow(row_pos)
            self.role_table.setItem(row_pos, 0, QTableWidgetItem(role or ""))
            self.role_table.setItem(row_pos, 1, QTableWidgetItem(f"${total:.2f}" if total is not None else "$0.00"))
        
        self.role_table.resizeColumnsToContents()
        self.auto_resize_table_height(self.role_table, row_height=32, max_height=1000)

    def plot_role_chart(self):
        self.role_chart.figure.clear()
        ax = self.role_chart.figure.add_subplot(111)
        year_filter, params = self.get_year_filter()
        conn = sqlite3.connect("matches.db")
        cur = conn.cursor()
        cur.execute(f"SELECT role, SUM(amount) FROM matches WHERE 1=1 {year_filter} GROUP BY role", params)
        data = [(r, a) for r, a in cur.fetchall() if r and a]
        conn.close()

        if not data:
            return

        roles = [r for r, _ in data]
        totals = [a for _, a in data]

        wedges, texts, autotexts = ax.pie(
            totals,
            labels=None,  # 不直接在图上画 label，避免重叠
            autopct='%1.1f%%',
            startangle=90,
            textprops={'fontsize': 8}
        )

        ax.set_title("Income by Role", pad=10, fontsize=10)

        # ✅ 设置图例在右侧、字体小、水平分布
        ax.legend(
            wedges,
            [r if len(r) < 10 else r[:8] + "…" for r in roles],
            loc="lower center",
            bbox_to_anchor=(0.5, -0.15),  # 适当微调
            ncol=len(roles),
            fontsize=9,
            title="Role"
        )
        self.role_chart.setMinimumHeight(300)
        self.role_chart.draw()

    def load_data(self):
        conn = sqlite3.connect("matches.db")
        cur = conn.cursor()

        self.monthly.setColumnCount(2)
        self.monthly.setHorizontalHeaderLabels(["Month", "Total"])
        self.auto_resize_table_height(self.league_table)
        self.auto_resize_table_height(self.role_table)
        cur.execute("SELECT strftime('%Y-%m', date), SUM(amount) FROM matches GROUP BY 1")
        rows = cur.fetchall()
        self.monthly.setRowCount(0)
        for row in rows:
            self.monthly.insertRow(self.monthly.rowCount())
            self.monthly.setItem(self.monthly.rowCount() - 1, 0, QTableWidgetItem(row[0]))
            self.monthly.setItem(self.monthly.rowCount() - 1, 1, QTableWidgetItem(f"${row[1] or 0:.2f}"))
        conn.close()

    def plot_monthly_chart(self):
        self.monthly_chart.figure.clear()
        ax = self.monthly_chart.figure.add_subplot(111)

        year_filter, params = self.get_year_filter()
        conn = sqlite3.connect("matches.db")
        cur = conn.cursor()
        cur.execute(f"SELECT strftime('%Y-%m', date), SUM(amount) FROM matches WHERE 1=1 {year_filter} GROUP BY 1", params)
        data = cur.fetchall()
        conn.close()

        data = [(m, t) for m, t in data if m and t is not None]
        months = [row[0] for row in data]
        totals = [row[1] for row in data]

        ax.bar(months, totals, color='cornflowerblue', width=0.6)
        ax.set_title("Monthly Income", fontsize=10)
        ax.set_xlabel("Month", fontsize=9)
        ax.set_ylabel("Total ($)", fontsize=9)
        ax.tick_params(axis='x', labelsize=8, rotation=45)
        ax.tick_params(axis='y', labelsize=8)
        ax.margins(x=0.1)

        self.monthly_chart.draw()

    def plot_league_chart(self):
        self.league_chart.figure.clear()
        ax = self.league_chart.figure.add_subplot(111)
        year_filter, params = self.get_year_filter()
        conn = sqlite3.connect("matches.db")
        cur = conn.cursor()
        cur.execute(f"SELECT league, SUM(amount) FROM matches WHERE 1=1 {year_filter} GROUP BY league", params)
        data = cur.fetchall()
        conn.close()

        data = [(l, t) for l, t in data if l and t is not None]
        data = sorted(data, key=lambda x: x[1], reverse=True)[:7]

        leagues = [l if len(l) <= 14 else l[:12] + "…" for l, _ in data]
        totals = [t for _, t in data]
        ax.barh(leagues, totals, color='lightskyblue')
        ax.set_title("Top Leagues by Income", fontsize=10)
        ax.set_xlabel("Total ($)", fontsize=9)
        ax.set_ylabel("League", fontsize=9)
        ax.tick_params(axis='x', labelsize=8)
        ax.tick_params(axis='y', labelsize=8)
        ax.invert_yaxis()  # 从高到低显示

        self.league_chart.figure.subplots_adjust(left=0.2, right=0.95, top=0.85, bottom=0.2)
        self.league_chart.draw()


    def refresh(self):
        self.load_years()
        self.load_data()
        self.load_summary()
        self.load_league_stats()
        self.load_role_stats()
        self.plot_monthly_chart()
        self.plot_league_chart()
        self.plot_role_chart()

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
        self.theme_switch.setChecked(False)  # default color
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
        tabs.addTab(self.auto_tab, "🧠 Auto")
        tabs.addTab(self.calendar_tab, "📅 Calendar")
        tabs.addTab(self.add_tab, "➕ Add Match")
        tabs.addTab(self.stats_tab, "📊 Statistics")
        layout.addWidget(tabs)
        self.calendar_tab.highlight_match_dates()
        self.calendar_tab.refresh_table()
        self.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 6px 12px;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                transition: all 0.3s ease;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #397d3c;
            }
        """)
        self.setStyleSheet(self.styleSheet() + """
            QLineEdit, QComboBox, QTableWidget {
                border: 1px solid #ccc;
                border-radius: 6px;
                padding: 6px;
                background-color: #f7f7f7;
            }

            QLineEdit:hover, QComboBox:hover {
                background-color: #ffffff;
            }

            QHeaderView::section {
                background-color: #e0e0e0;
                padding: 4px;
                border: 1px solid #ccc;
                font-weight: bold;
            }

            QTableWidget::item:hover {
                background-color: #eaf4ea;
            }
        """)
    
    def toggle_theme(self):
        if self.theme_switch.isChecked():
            apply_stylesheet(app, theme='dark_teal.xml')
            self.set_dark_table_style()
        else:
            apply_stylesheet(app, theme='light_blue.xml')
            self.set_light_table_style()
    
    def set_dark_table_style(self):
        self.setStyleSheet(self.styleSheet() + """
        QTableWidget {
            background-color: #2b2b2b;
            color: #eeeeee;
            gridline-color: #444;
        }
        QHeaderView::section {
            background-color: #3c3c3c;
            color: white;
            border: 1px solid #555;
        }
        QTableWidget::item:selected {
            background-color: #555;
        }
        QLineEdit, QComboBox, QTimeEdit {
            background-color: #2b2b2b;
            color: #eeeeee;
            border: 1px solid #555;
            border-radius: 6px;
            padding: 6px;
        }
        QLineEdit:hover, QComboBox:hover, QTimeEdit:hover {
            background-color: #3c3c3c;
        }
    """)

    def set_light_table_style(self):
        self.setStyleSheet(self.styleSheet() + """
            QTableWidget {
                background-color: #f7f7f7;
                color: black;
                gridline-color: #ccc;
            }
            QHeaderView::section {
                background-color: #e0e0e0;
                color: black;
            }
            QTableWidget::item:selected {
                background-color: #d0f0d0;
            }
        """)

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