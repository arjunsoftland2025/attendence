import frappe
from frappe.utils import add_days, get_datetime, today, getdate, add_months, formatdate
from datetime import timedelta

@frappe.whitelist()
def get_date():
   today = frappe.utils.today()
   return today

@frappe.whitelist(allow_guest=True)
def get_user_details(email=None):
    if not email:
        return {"error": "Email parameter is required."}
    try:
        user = frappe.get_doc("Employee", {"user_id": email})
        
        return {
            "full_name": user.employee,
            "email": user.user_id
        }
    except frappe.DoesNotExistError:
        return {"error": "User not found."}
    except Exception as e:
        return {"error": str(e)}

@frappe.whitelist(allow_guest=True)
def get_attendance(employee_name, date):
    start_datetime = get_datetime(date + " 00:00:00")
    end_datetime = get_datetime(date + " 23:59:59")

    # Query Employee Checkin table
    query = """
        SELECT `employee`, `log_type`, `time`
        FROM `tabEmployee Checkin`
        WHERE `employee` = %s
        AND `time` BETWEEN %s AND %s
        ORDER BY `time` ASC
    """
    attendance_records = frappe.db.sql(query, (employee_name, start_datetime, end_datetime), as_dict=True)

    # Get multi-level reportees
    report_hierarchy = get_all_reportees(employee_name)

    sessions = []
    total_working_seconds = 0
    current_session = {}

    for record in attendance_records:
        log_type = record["log_type"]
        log_time = record["time"]

        if log_type == "IN":
            if "in_time" in current_session and "out_time" not in current_session:
                sessions.append({
                    f"session {len(sessions) + 1}": {
                        "employee_name": employee_name,
                        "date": str(current_session["in_time"].date()),
                        "in_time": current_session["in_time"].strftime("%H:%M:%S"),
                        "out_time": "",
                        "working_hours": "0:00:00"
                    }
                })

            current_session = {"in_time": log_time}

        elif log_type == "OUT":
            if "in_time" not in current_session:
                sessions.append({
                    f"session {len(sessions) + 1}": {
                        "employee_name": employee_name,
                        "date": str(log_time.date()),
                        "in_time": "",
                        "out_time": log_time.strftime("%H:%M:%S"),
                        "working_hours": "0:00:00"
                    }
                })
            else:
                in_time = current_session["in_time"]
                out_time = log_time
                working_seconds = (out_time - in_time).total_seconds()
                total_working_seconds += working_seconds

                working_hours = f"{int(working_seconds // 3600)}:{str(int((working_seconds % 3600) // 60)).zfill(2)}:{str(int(working_seconds % 60)).zfill(2)}"

                sessions.append({
                    f"session {len(sessions) + 1}": {
                        "employee_name": employee_name,
                        "date": str(in_time.date()),
                        "in_time": in_time.strftime("%H:%M:%S"),
                        "out_time": out_time.strftime("%H:%M:%S"),
                        "working_hours": working_hours
                    }
                })
                current_session = {}  

    if "in_time" in current_session:
        sessions.append({
            f"session {len(sessions) + 1}": {
                "employee_name": employee_name,
                "date": str(current_session["in_time"].date()),
                "in_time": current_session["in_time"].strftime("%H:%M:%S"),
                "out_time": "",
                "working_hours": "0:00:00"
            }
        })

   
    # Convert total working seconds to hours:minutes:seconds format
    total_hours = int(total_working_seconds // 3600)
    total_minutes = int((total_working_seconds % 3600) // 60)
    total_seconds = int(total_working_seconds % 60)
    
    total_working_hours = f"{total_hours}:{str(total_minutes).zfill(2)}:{str(total_seconds).zfill(2)}"

    # Construct the final response JSON with labeled session records and total working hours in 'hours:minutes' format
    response = {
        "attendance_sessions": sessions,  # Nested session data with labeled sessions
        "working_hours": total_working_hours, # Total working hours for the day
        "report_names": report_hierarchy # Multi-level reportees
    }

    return response

# ✅ **Recursive Function to Get Multi-Level Reportees**
def get_all_reportees(employee_name, level=1):
    reportees = frappe.db.sql("""
        SELECT `employee`
        FROM `tabEmployee`
        WHERE `old_parent` = %s
    """, (employee_name,), as_dict=True)

    all_reportees = []
    for reportee in reportees:
        reportee_data = {
            "employee": reportee["employee"],
            "level": level,  # Track depth level
            "subordinates": get_all_reportees(reportee["employee"], level + 1)  # Recursion
        }
        all_reportees.append(reportee_data)

    return all_reportees

@frappe.whitelist(allow_guest=True)
def get_weekly_average(employee_name, current_date):
    # Convert string date to datetime object
    current_date = getdate(current_date)

    # Check if today is Sunday; if yes, return 0
    if current_date.weekday() == 6:  # Sunday (0=Monday, 6=Sunday)
        return {"error": "Sunday is ignored for weekly average calculation."}

    total_seconds = 0
    valid_days = 0  # Track number of valid weekdays (Mon-Sat)

    # Iterate over days from Monday to (Current Day - 1)
    for days_ago in range(1, current_date.weekday() + 1):  
        past_date = add_days(current_date, -days_ago)  # Get past date

        # Query Employee Checkin table for working hours
        query = """
            SELECT `time` FROM `tabEmployee Checkin`
            WHERE `employee` = %s
            AND DATE(`time`) = %s
        """
        checkin_records = frappe.db.sql(query, (employee_name, past_date), as_dict=True)

        # Fetch attendance data for the day
        attendance = get_attendance(employee_name, str(past_date))
        if attendance.get("error"):  
            continue  # Skip if no attendance data

        working_hours = attendance["working_hours"]
        hours, minutes, seconds = map(int, working_hours.split(":"))
        daily_seconds = (hours * 3600) + (minutes * 60) + seconds

        total_seconds += daily_seconds
        valid_days += 1

    # If no valid days found, return 0
    if valid_days == 0:
        return {"error": "No working days found for weekly average calculation."}

    # Calculate the average in seconds
    avg_seconds = total_seconds // valid_days  
    avg_hours = avg_seconds // 3600
    avg_minutes = (avg_seconds % 3600) // 60
    avg_seconds_remaining = avg_seconds % 60

    # Format output
    avg_hh_mm_ss = f"{avg_hours}:{str(avg_minutes).zfill(2)}:{str(avg_seconds_remaining).zfill(2)}"
    avg_hh_mm = f"{avg_hours}.{str(avg_minutes).zfill(2)}"

    return {
        "weekly_avg_hh_mm_ss": avg_hh_mm_ss,  
        "weekly_avg_hh_mm": avg_hh_mm,  
        "days_considered": valid_days
    }

@frappe.whitelist(allow_guest=True)
def get_monthly_average(employee_name, current_date):
    current_date = getdate(current_date)  # Convert string date to datetime object
    
    # Get the first and last date of the previous month
    first_day_of_prev_month = add_months(current_date.replace(day=1), -1)
    first_day_of_current_month = current_date.replace(day=1)
    # last_day_of_prev_month = first_day_of_current_month - timedelta(days=1)
    # print(f"last_day_of_prev_month: {last_day_of_prev_month}")
    
    total_seconds = 0
    valid_days = 0  # Track number of valid working days
    
    # Fetch all valid dates with check-in data
    query = """
        SELECT DISTINCT DATE(`time`) as work_date
        FROM `tabEmployee Checkin`
        WHERE `employee` = %s
        AND `time` BETWEEN %s AND %s
    """
    valid_dates = frappe.db.sql(query, (employee_name, first_day_of_prev_month, first_day_of_current_month), as_dict=True)
    # print(f"Length of valid_dates: {len(valid_dates)}")

    for record in valid_dates:
        work_date = record["work_date"]
        
        # Fetch attendance data for the date
        attendance = get_attendance(employee_name, str(work_date))
        if attendance.get("error"):  
            print(f"Skipping {work_date} due to error: {attendance.get('error')}")
            continue  # Skip if no attendance data
        
        working_hours = attendance["working_hours"]
        hours, minutes, seconds = map(int, working_hours.split(":"))
        daily_seconds = (hours * 3600) + (minutes * 60) + seconds

        total_seconds += daily_seconds
        valid_days += 1

    # print("Valid dates from SQL:", valid_dates)
    # print("\n")
    # print("Processed dates in API:", valid_days)
    # If no valid days found, return an error
    if valid_days == 0:
        return {"error": "No working days found for monthly average calculation."}

    # Calculate the average in seconds
    avg_seconds = total_seconds // valid_days  
    avg_hours = avg_seconds // 3600
    avg_minutes = (avg_seconds % 3600) // 60
    avg_seconds_remaining = avg_seconds % 60

    # Format output
    avg_hh_mm_ss = f"{avg_hours}:{str(avg_minutes).zfill(2)}:{str(avg_seconds_remaining).zfill(2)}"
    avg_hh_mm = f"{avg_hours}.{str(avg_minutes).zfill(2)}"

    

    return {
        "monthly_avg_hh_mm_ss": avg_hh_mm_ss,
        "monthly_avg_hh_mm": avg_hh_mm,
        "days_considered": valid_days,
        "month": formatdate(first_day_of_prev_month, "MMMM YYYY")  # Format as "March 2024"
    }
