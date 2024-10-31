README

# Referee Management System

Referee Management System (RefSys) is a tool designed for amateur and semi-professional referees to manage their match assignments efficiently. The system allows referees to add, edit, delete, and view match details, track earnings, and parse text-based assignments automatically to minimize manual data entry.

## Features

1. **Match Management**:
   - Add, edit, and delete match assignments manually.
   - Store details like league, role, match name, date, time, location, and amount.
   - Detect scheduling conflicts to prevent overlapping matches.

2. **Statistics Tracking**:
   - Calculate weekly and monthly income based on match assignments.
   - Display income statistics in a user-friendly interface.

3. **Automated Text Parsing**:
   - Automatically extract match details from text-based assignment formats.
   - Supports two different text formats, commonly used in assignment sheets.
   - Parses details such as league, role, match name, date, start time, and location.
   - Converts roles to consistent names (e.g., "Assistant Referee #1" or "Assistant Referee #2" to "AR").
   - Generates match names in the format `<Home Team> vs <Visiting Team>` automatically.

4. **System Tray Minimization**:
   - Minimize the application to the system tray for easier background running.
   
## Installation

### Requirements

- Python 3.8 or later
- Required Python packages:
  - `tkinter` for the graphical interface
  - `sqlite3` for database management
  - `dateparser` for parsing date strings from text
  - `pystray` for system tray functionality
  - `Pillow` for image handling (for tray icon)
  - `tkcalendar` for date picking

### Installation Steps
   
- python -m PyInstaller --onefile --windowed RefSys.py
- run the exe file \RefSys\dist\RefSys.exe


Interface Overview
1. Calendar:

-  Displays matches on their scheduled dates.
-  Shows a red mark on dates with scheduled matches.
-  Double-click a match in the list to edit it.

2. Add Match:

-  Manually add a new match with all details.
-  Detects conflicts if the match overlaps with existing entries.

3. Statistics:

-  Shows weekly and monthly income based on saved matches.
-  Useful for tracking earnings over time.

4. Auto Parsing:

-  Paste text-based assignments into the text box under the "Auto" tab.
-  Click "Parse and Add Match" to automatically extract match details and add them to the calendar.

-  Supports two specific formats:
	Format 1: Brief format with date, time, and team info.
	Format 2: Detailed format with name, role, teams, and location.
	Example of Supported Input Formats for Auto Parsing


		Format 1

		Referee: Sat Nov 2 10:15 AM PDT @ BBY CENTRAL SS Turf
		# BCCSL 15154, U16 D3, BOYS, Two x 40min/5min HT; CR full reports AssignR & SPAPPZ. AR scores in AssignR by Sun night., BCCSL DIV 3 NEON GREEN (Map)
		Assistant Referee 2: Sat Nov 2 2:15 PM PDT @ BLWSC Turf #4
		# BCSPL - 20241102-05, U15 PL, BOYS, Two x 40min/10min HT; UNLIM SUBS 5 INSTANCES/HALF Re-entry permitted. CR COMET/All AssignR, BCSPL 2024 Phase2
		
		Format 2
		
		Name: Junyue Zhang
		Role: Assistant Referee #1
		Division: O45 Premier
		Schedule date/time: Sunday, October 27, 2024 - 11:00:00 AM
		Field Name: Hillcrest SE Grass - VAN
		City: Vancouver
		Home Team: Westside FC M-B Originals
		Visiting Team: FC Romania M-B

# Common Operations
-  Add Match: Use the "Add Match" tab to enter match details manually.
-  Edit Match: Double-click a match in the list to open an edit window. Update details and click "Save Changes."
-  Delete Match: Select a match and click the "Delete Match" button.
-  View Statistics: Access the "Statistics" tab to see weekly and monthly income.
-  Auto Parse: Paste formatted text in the "Auto" tab and click "Parse and Add Match."

# System Tray Icon
-  The application minimizes to the system tray when closed. To restore the window:
-  Right-click the tray icon and select "Show."
-  To fully quit, right-click and choose "Quit."