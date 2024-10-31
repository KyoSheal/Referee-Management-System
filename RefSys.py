import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
from tkcalendar import Calendar
from datetime import datetime, timedelta
from pystray import Icon, MenuItem as item, Menu
from PIL import Image
import threading
import re
import dateparser

# Initialize or connect to the database
def init_db():
    conn = sqlite3.connect('matches.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS matches
                      (id INTEGER PRIMARY KEY, league TEXT, role TEXT, subject TEXT, content TEXT, date TEXT, start_time TEXT, end_time TEXT, location TEXT, amount REAL)''')
    conn.commit()
    conn.close()

# Update the database structure to add the 'amount' column
def update_db_structure():
    conn = sqlite3.connect('matches.db')
    cursor = conn.cursor()
    try:
        cursor.execute('ALTER TABLE matches ADD COLUMN amount REAL')
        conn.commit()
    except sqlite3.OperationalError:
        pass
    conn.close()

def minimize_to_tray():
    def quit_window(icon, item):
        window.destroy()
        icon.stop()

    def show_window(icon, item):
        window.deiconify()
        icon.stop()

    # Hide the window
    window.withdraw()

    # Create an icon for system tray
    image = Image.open("C:/Users/kyosh/Desktop/Project/RefSys/icon.png")
    menu = Menu(item('Show', show_window), item('Quit', quit_window))
    icon = Icon("Referee Management System", image, menu=menu)

    # Start the icon in a separate thread
    threading.Thread(target=icon.run).start()

# Check for time conflicts before adding a new match
def check_time_conflict(date, start_time, end_time):
    conn = sqlite3.connect('matches.db')
    cursor = conn.cursor()
    cursor.execute("SELECT start_time, end_time FROM matches WHERE date=?", (date,))
    existing_matches = cursor.fetchall()
    conn.close()

    new_start_time = datetime.strptime(start_time, '%H:%M')
    new_end_time = datetime.strptime(end_time, '%H:%M')

    for match in existing_matches:
        existing_start = datetime.strptime(match[0], '%H:%M')
        existing_end = datetime.strptime(match[1], '%H:%M')

        if new_start_time < existing_end and new_end_time > existing_start:
            return True
    return False

# Parse match details from text for the Auto tab
def parse_text_to_match_data(text):
    try:
        name = re.search(r"Name:\s*(.*)", text).group(1)
        role = re.search(r"Role:\s*(.*)", text).group(1)
        division = re.search(r"Division:\s*(.*)", text).group(1)
        schedule = re.search(r"Schedule date/time:\s*(.*)", text).group(1)
        field_name = re.search(r"Field Name:\s*(.*)", text).group(1)
        city = re.search(r"City:\s*(.*)", text).group(1)
        home_team = re.search(r"Home Team:\s*(.*)", text).group(1)
        visiting_team = re.search(r"Visiting Team:\s*(.*)", text).group(1)

        # Convert date and time format
        date_time = dateparser.parse(schedule)
        date = date_time.strftime("%Y-%m-%d")
        start_time = date_time.strftime("%H:%M")
        match_name = f"{home_team} vs {visiting_team}"
        
        if "Assistant Referee" in role:
            role = "AR"

        return {
            "league": division,
            "role": role,
            "match_name": match_name,
            "date": date,
            "start_time": start_time,
            "location": f"{field_name}, {city}"
        }
    except Exception as e:
        messagebox.showerror("Error", f"Failed to parse match data: {e}")
        return None

# Add parsed match data to database
def auto_add_match():
    text = auto_text.get("1.0", "end-1c")
    match_data = parse_text_to_match_data(text)
    if match_data:
        league = match_data["league"]
        role = match_data["role"]
        match_name = match_data["match_name"]
        date = match_data["date"]
        start_time = match_data["start_time"]
        location = match_data["location"]
        end_time = calculate_end_time(start_time)

        # Check for time conflict
        if check_time_conflict(date, start_time, end_time):
            messagebox.showerror("Error", "Time conflict detected with another match!")
            return

        # Insert into database
        conn = sqlite3.connect('matches.db')
        cursor = conn.cursor()
        cursor.execute('INSERT INTO matches (league, role, subject, content, date, start_time, end_time, location, amount) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                       (league, role, match_name, f"{match_name} details", date, start_time, end_time, location, 0))
        conn.commit()
        conn.close()
        messagebox.showinfo("Success", "Match added successfully!")
        mark_dates_with_matches()
        show_matches_for_date()
        update_statistics()

# Calculate match end time
def calculate_end_time(start_time, match_duration=90, break_time=10):
    start_time_obj = datetime.strptime(start_time, '%H:%M')
    total_duration = match_duration + break_time
    end_time_obj = start_time_obj + timedelta(minutes=total_duration)
    return end_time_obj.strftime('%H:%M')

# Delete a match from the database
def delete_match():
    selected_item = match_tree.selection()
    if selected_item:
        match_id = match_tree.item(selected_item, "values")[0]
        conn = sqlite3.connect('matches.db')
        cursor = conn.cursor()
        cursor.execute("DELETE FROM matches WHERE id=?", (match_id,))
        conn.commit()
        conn.close()
        messagebox.showinfo("Success", "Match deleted successfully!")
        mark_dates_with_matches()
        show_matches_for_date()
        update_statistics()
    else:
        messagebox.showwarning("Warning", "Please select a match to delete.")

# Update statistics based on the matches
def update_statistics():
    conn = sqlite3.connect('matches.db')
    cursor = conn.cursor()

    cursor.execute('''SELECT strftime('%Y-%W', date) AS week, SUM(amount) FROM matches GROUP BY week ORDER BY week''')
    weekly_income = cursor.fetchall()

    weekly_tree.delete(*weekly_tree.get_children())
    for week, total_income in weekly_income:
        total_income = total_income if total_income is not None else 0
        weekly_tree.insert('', 'end', values=(week, f'${total_income:.2f}'))

    cursor.execute('''SELECT strftime('%Y-%m', date) AS month, SUM(amount) FROM matches GROUP BY month ORDER BY month''')
    monthly_income = cursor.fetchall()

    monthly_tree.delete(*monthly_tree.get_children())
    for month, total_income in monthly_income:
        total_income = total_income if total_income is not None else 0
        monthly_tree.insert('', 'end', values=(month, f'${total_income:.2f}'))

    conn.close()

# Show matches for the selected date
def show_matches_for_date():
    selected_date = cal.get_date()
    matches = load_matches(selected_date)

    for row in match_tree.get_children():
        match_tree.delete(row)

    if matches:
        for match in matches:
            amount = match[9] if match[9] is not None else 0.00
            match_info = (match[0], match[1], match[2], match[3], match[5], match[6], match[7], match[8], f"${amount:.2f}")
            match_tree.insert('', 'end', values=match_info)
    else:
        match_tree.insert('', 'end', values=("No matches", "", "", "", "", "", "", "", ""))

# Load matches for the selected date
def load_matches(date):
    conn = sqlite3.connect('matches.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM matches WHERE date=?", (date,))
    rows = cursor.fetchall()
    conn.close()
    return rows

# Mark dates with matches in the calendar
def mark_dates_with_matches():
    conn = sqlite3.connect('matches.db')
    cursor = conn.cursor()
    cursor.execute("SELECT date, COUNT(*) FROM matches GROUP BY date")
    dates_with_matches = cursor.fetchall()
    conn.close()

    cal.calevent_remove('match')

    for date_tuple in dates_with_matches:
        date_str = date_tuple[0]
        num_matches = date_tuple[1]
        cal.calevent_create(datetime.strptime(date_str, '%Y-%m-%d'), f'{num_matches} match(es)', 'match')
        cal.tag_config('match', background='red', foreground='white')

# Edit match information window with save functionality
def edit_match_window(match_id):
    conn = sqlite3.connect('matches.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM matches WHERE id=?", (match_id,))
    match = cursor.fetchone()
    conn.close()

    if not match:
        messagebox.showerror("Error", "Match not found!")
        return

    edit_window = tk.Toplevel(window)
    edit_window.title("Edit Match")
    edit_window.geometry("400x400")

    tk.Label(edit_window, text="League:").pack(pady=5)
    league_entry = tk.Entry(edit_window)
    league_entry.insert(0, match[1])
    league_entry.pack(pady=5)

    tk.Label(edit_window, text="Role:").pack(pady=5)
    role_entry = tk.Entry(edit_window)
    role_entry.insert(0, match[2])
    role_entry.pack(pady=5)

    tk.Label(edit_window, text="Match Name:").pack(pady=5)
    subject_entry = tk.Entry(edit_window)
    subject_entry.insert(0, match[3])
    subject_entry.pack(pady=5)

    tk.Label(edit_window, text="Date:").pack(pady=5)
    date_entry = tk.Entry(edit_window)
    date_entry.insert(0, match[5])
    date_entry.pack(pady=5)

    tk.Label(edit_window, text="Start Time:").pack(pady=5)
    start_time_entry = tk.Entry(edit_window)
    start_time_entry.insert(0, match[6])
    start_time_entry.pack(pady=5)

    tk.Label(edit_window, text="Location:").pack(pady=5)
    location_entry = tk.Entry(edit_window)
    location_entry.insert(0, match[8])
    location_entry.pack(pady=5)

    tk.Label(edit_window, text="Amount ($):").pack(pady=5)
    amount_entry = tk.Entry(edit_window)
    amount_entry.insert(0, str(match[9]) if match[9] is not None else "0.00")
    amount_entry.pack(pady=5)

    def save_changes():
        new_league = league_entry.get()
        new_role = role_entry.get()
        new_subject = subject_entry.get()
        new_date = date_entry.get()
        new_start_time = start_time_entry.get()
        new_location = location_entry.get()

        try:
            new_amount = float(amount_entry.get())
        except ValueError:
            messagebox.showerror("Error", "Please enter a valid amount!")
            return

        conn = sqlite3.connect('matches.db')
        cursor = conn.cursor()
        cursor.execute('''UPDATE matches 
                          SET league=?, role=?, subject=?, date=?, start_time=?, location=?, amount=? 
                          WHERE id=?''', 
                       (new_league, new_role, new_subject, new_date, new_start_time, new_location, new_amount, match_id))
        conn.commit()
        conn.close()
        messagebox.showinfo("Success", "Match information updated!")
        edit_window.destroy()
        mark_dates_with_matches()  
        show_matches_for_date()

    save_button = tk.Button(edit_window, text="Save Changes", command=save_changes)
    save_button.pack(pady=10)

    edit_window.bind("<Return>", lambda event: save_changes())

# Handle double-click event to edit match
def on_double_click(event):
    selected_item = match_tree.selection()
    if selected_item:
        match_id = match_tree.item(selected_item, "values")[0]
        edit_match_window(match_id)

# Create main window
window = tk.Tk()
window.title("Referee Management System")
window.geometry("1000x700")

# Create tabs
notebook = ttk.Notebook(window)
calendar_frame = ttk.Frame(notebook)
add_match_frame = ttk.Frame(notebook)
stats_frame = ttk.Frame(notebook)
auto_frame = ttk.Frame(notebook)

notebook.add(calendar_frame, text="Calendar")
notebook.add(add_match_frame, text="Add Match")
notebook.add(stats_frame, text="Statistics")
notebook.add(auto_frame, text="Auto")
notebook.pack(expand=True, fill="both")

# Calendar section
cal = Calendar(calendar_frame, selectmode='day', date_pattern='y-mm-dd', font=("Helvetica", 16), showweeknumbers=False)
cal.pack(pady=20, fill="both", expand=True)

# Match information table
columns = ("ID", "League", "Role", "Match Name", "Date", "Start Time", "End Time", "Location", "Amount")
match_tree = ttk.Treeview(calendar_frame, columns=columns, show="headings", height=10)
for col in columns:
    match_tree.heading(col, text=col)
    match_tree.column(col, width=100)
match_tree.pack(pady=10, padx=10, fill="x")

match_tree.bind("<Double-1>", on_double_click)

show_matches_button = tk.Button(calendar_frame, text="Show Matches", font=("Helvetica", 14), command=show_matches_for_date)
show_matches_button.pack(pady=10)

delete_button = tk.Button(calendar_frame, text="Delete Match", font=("Helvetica", 14), command=lambda: [delete_match(), mark_dates_with_matches()])
delete_button.pack(pady=10)

# Add match section
league_label = tk.Label(add_match_frame, text="League:")
league_label.pack(pady=5)
league_entry = tk.Entry(add_match_frame)
league_entry.pack(pady=5)

role_label = tk.Label(add_match_frame, text="Role:")
role_label.pack(pady=5)
role_var = tk.StringVar()
role_menu = ttk.Combobox(add_match_frame, textvariable=role_var, values=["Referee", "AR"])
role_menu.pack(pady=5)

match_name_label = tk.Label(add_match_frame, text="Match Name:")
match_name_label.pack(pady=5)
match_name_entry = tk.Entry(add_match_frame)
match_name_entry.pack(pady=5)

match_date_label = tk.Label(add_match_frame, text="Match Date (YYYY-MM-DD):")
match_date_label.pack(pady=5)
match_date_entry = tk.Entry(add_match_frame)
match_date_entry.pack(pady=5)

start_time_label = tk.Label(add_match_frame, text="Start Time (HH:MM):")
start_time_label.pack(pady=5)
start_time_entry = tk.Entry(add_match_frame)
start_time_entry.pack(pady=5)

location_label = tk.Label(add_match_frame, text="Location:")
location_label.pack(pady=5)
location_entry = tk.Entry(add_match_frame)
location_entry.pack(pady=5)

amount_label = tk.Label(add_match_frame, text="Amount ($):")
amount_label.pack(pady=5)
amount_entry = tk.Entry(add_match_frame)
amount_entry.pack(pady=5)

add_button = tk.Button(add_match_frame, text="Add Match", command=lambda: [add_new_match(), mark_dates_with_matches(), update_statistics()])
add_button.pack(pady=20)

# Statistics section
ttk.Label(stats_frame, text="Weekly Income", font=("Helvetica", 16)).pack(pady=10)
weekly_tree = ttk.Treeview(stats_frame, columns=("week", "total_income"), show="headings", height=5)
weekly_tree.heading("week", text="Week")
weekly_tree.heading("total_income", text="Total Income ($)")
weekly_tree.pack(pady=10, padx=10, fill="x")

ttk.Label(stats_frame, text="Monthly Income", font=("Helvetica", 16)).pack(pady=10)
monthly_tree = ttk.Treeview(stats_frame, columns=("month", "total_income"), show="headings", height=5)
monthly_tree.heading("month", text="Month")
monthly_tree.heading("total_income", text="Total Income ($)")
monthly_tree.pack(pady=10, padx=10, fill="x")

# Auto tab
auto_label = tk.Label(auto_frame, text="Enter match details:")
auto_label.pack(pady=5)
auto_text = tk.Text(auto_frame, height=15, width=50)
auto_text.pack(pady=5)

parse_button = tk.Button(auto_frame, text="Parse and Add", command=auto_add_match)
parse_button.pack(pady=10)

# Initialize database and start program
init_db()
update_db_structure()
mark_dates_with_matches()
update_statistics()
window.protocol('WM_DELETE_WINDOW', minimize_to_tray)
window.mainloop()
