# Referee-Management-System
Referee Management System
This application is a referee management system that allows referees to manage their match schedules, track earnings, and record match details. The system includes a calendar interface, a match-adding feature, and income statistics for weekly and monthly earnings.

Features
Calendar View: View match schedules with highlighted match dates.
Add Match: Add new matches, including league, role, date, start time, location, and payment.
Match Management: Double-click to edit match details and delete matches.
Income Statistics: View weekly and monthly income based on match earnings.
How to Run
Install Python 3.x and the required libraries:

bash
Copy code
pip install tkcalendar sqlite3
Run the Python script:
python -m PyInstaller --onefile --hidden-import=plyer 111.py

bash
Copy code
python referee_management.py
Functions
init_db(): Initializes the SQLite database.
update_db_structure(): Updates the database to include any missing fields.
add_new_match(): Adds a new match to the database.
delete_match(): Deletes a selected match.
update_statistics(): Updates weekly and monthly earnings statistics.
show_matches_for_date(): Displays matches for a selected date in the calendar.
edit_match_window(): Opens a window to edit match information.
mark_dates_with_matches(): Marks match dates in the calendar.
Requirements
Python 3.x
Tkinter
SQLite3
tkcalendar library for calendar functionality
