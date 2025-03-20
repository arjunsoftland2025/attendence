import frappe
from frappe import _
from frappe.utils import get_datetime
from datetime import datetime, timedelta

@frappe.whitelist()
def get_date():
   today = frappe.utils.today()
   return today


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

    report_query = """
        SELECT `employee`
        FROM `tabEmployee`
        WHERE `old_parent` = %s
    """
    report_records = frappe.db.sql(report_query, (employee_name), as_dict=True)
    print(report_records)

    sessions = []  # List to hold session data
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

    total_hours = int(total_working_seconds // 3600)
    total_minutes = int((total_working_seconds % 3600) // 60)
    total_working_hours = f"{total_hours}:{str(total_minutes).zfill(2)}"

    response = {
        "attendance_sessions": sessions,
        "working_hours": total_working_hours,
        "report_names" : report_records
    }

    return response
