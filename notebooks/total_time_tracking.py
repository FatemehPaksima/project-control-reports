"""
Total Time Tracking Report
===========================
Extracts employee attendance data from a monthly Excel report and
produces a clean, formatted Excel workbook with:

    - Full name
    - Employee code
    - Date
    - Total attendance (HH:MM)
    - Status (حضور / مرخصی ساعتی / مرخصی روزانه) as a dropdown list
"""

import pandas as pd
from openpyxl import Workbook
from openpyxl.worksheet.datavalidation import DataValidation


# ============================================================
# Configuration
# ============================================================
INPUT_FILE = "./data/raw/attendance_report.xlsx"
OUTPUT_FILE = "./output/Total_time_tracking/timetracking_output.xlsx"


# ============================================================
# Helpers
# ============================================================
def time_difference(entry_time: str, exit_time: str):
    """Compute the time difference between two HH:MM strings."""
    time_format = "%H:%M"
    try:
        t_entry = pd.to_datetime(entry_time, format=time_format, errors="raise")
        t_exit = pd.to_datetime(exit_time, format=time_format, errors="raise")
        difference = t_entry - t_exit
        total_minutes = difference.total_seconds() // 60
        hours = total_minutes // 60
        minutes = total_minutes % 60
        return f"{int(hours):02}:{int(minutes):02}"
    except Exception:
        return None


def extract_data(df: pd.DataFrame) -> list[dict]:
    """Walk the report and pull out attendance rows."""
    data = []
    current_full_name = None
    current_employee_code = None

    for i in range(len(df)):
        # Detect employee name
        if pd.notna(df.iloc[i, 3]) and isinstance(df.iloc[i, 3], str):
            if "نام و نام خانوادگی:" in df.iloc[i, 3]:
                current_full_name = df.iloc[i, 3].split(":")[1].strip()
            elif "کد پرسنلی:" in df.iloc[i, 3]:
                current_employee_code = df.iloc[i, 3].split(":")[1].strip()

        if not (current_full_name and current_employee_code):
            continue

        first_col = df.iloc[i, 0]
        unnamed_11 = df.iloc[i, 11] if len(df.columns) > 11 else None
        total_presence = df.iloc[i]["کل حضور"] if "کل حضور" in df.columns else None

        if total_presence and first_col in ["حضور", "مرخصی استحقاقی"]:
            status = (
                "حضور"
                if first_col == "حضور"
                else ("مرخصی روزانه" if total_presence == "08:45" else "مرخصی ساعتی")
            )
            data.append({
                "نام و نام خانوادگی": current_full_name,
                "کد پرسنلی": current_employee_code,
                "Unnamed: 11": unnamed_11,
                "کل حضور": total_presence,
                "وضعیت": status,
            })

    return data


def save_to_excel(data: list[dict], output_path: str) -> None:
    """Write the extracted data to a nicely formatted Excel file."""
    result_df = pd.DataFrame(data)
    result_df.rename(columns={"Unnamed: 11": "روز و تاریخ"}, inplace=True)

    # Forward-fill date column
    result_df["روز و تاریخ"] = result_df["روز و تاریخ"].ffill()

    # Drop duplicates
    result_df.drop_duplicates(inplace=True)

    # Build workbook
    wb = Workbook()
    ws = wb.active

    # Header row
    for c_idx, column in enumerate(result_df.columns, start=1):
        ws.cell(row=1, column=c_idx, value=column)

    # Data rows
    for r_idx, row in enumerate(result_df.itertuples(index=False, name=None), start=2):
        for c_idx, value in enumerate(row, start=1):
            ws.cell(row=r_idx, column=c_idx, value=value)

    # Dropdown for the "وضعیت" column
    dv = DataValidation(
        type="list",
        formula1='"حضور,مرخصی ساعتی,مرخصی روزانه"',
        showDropDown=True,
    )
    ws.add_data_validation(dv)
    status_col = result_df.columns.get_loc("وضعیت") + 1
    for row in range(2, len(result_df) + 2):
        dv.add(ws.cell(row=row, column=status_col))

    # Save
    import os
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    wb.save(output_path)


# ============================================================
# Main
# ============================================================
def main(input_file: str, output_file: str) -> None:
    df = pd.read_excel(input_file)

    # Calculate total attendance from entry (col 1) and exit (col 2)
    df["کل حضور"] = df.apply(
        lambda row: time_difference(row.iloc[1], row.iloc[2]), axis=1
    )

    extracted = extract_data(df)
    save_to_excel(extracted, output_file)
    print("✅ Data extraction and saving has been completed.")


if __name__ == "__main__":
    main(INPUT_FILE, OUTPUT_FILE)