"""
Weekly Report Generator
========================
Combines a weekly Jira export with the planning spreadsheet, and produces
two reports:
    1. Task tracking vs. planned time
    2. Team productivity breakdown by task category
"""

import re
import os

import pandas as pd


# ============================================================
# Configuration
# ============================================================
DATA_DIR = "./data/raw/"
RESULTS_DIR = "./output/Weekly/"
JIRA_FILE_NAME = "week.csv"
PLANNED_FILE_NAME = "planning.xlsx"
EXCEL_OUTPUT_NAME = "weekly_output.xlsx"
PROD_REPORT_NAME = "aggregated_jira_report.csv"

REGEX_PATTERN = r"S21W1-(\d{1,2})"


# ============================================================
# Helpers
# ============================================================
def extract_summary_format(text: str, pattern: str):
    match = re.search(pattern, text)
    return match.group(0) if match else None


def extract_numeric_summary(summary: str, pattern: str):
    match = re.search(pattern, summary)
    return int(match.group(1)) if match else None


def unexpected_task_recognition(text: str) -> int:
    return int("unexpected" in text.lower())


def meeting_task_recognition(text: str) -> int:
    return int("meeting" in text.lower())


def planned_task_recognition(text: str, pattern: str = r"S\d+W[12]-(\d+)") -> int:
    return int(1) if re.search(pattern, text) else 0


# ============================================================
# DataFrame prep
# ============================================================
def process_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df["Summary"] = df["Summary"].fillna("").astype(str).str.upper()
    df["Description"] = df["Description"].fillna("").astype(str)
    df["Combined_Text"] = df["Summary"] + " " + df["Description"]
    df["Extracted_Summary"] = df["Combined_Text"].apply(
        lambda x: extract_summary_format(x, REGEX_PATTERN)
    )
    df.dropna(subset=["Extracted_Summary"], inplace=True)
    df["In Progress"] = pd.to_numeric(df["In Progress"], errors="coerce")
    return df


def merge_excel_sheets_to_dataframe(path: str) -> pd.DataFrame:
    """Merge all sheets of a planning Excel into a single DataFrame."""
    excel_file = pd.ExcelFile(path)
    frames = []
    for sheet in excel_file.sheet_names:
        sheet_df = excel_file.parse(sheet)
        selected = sheet_df[["کد", "عنوان تسک", "زمان تخمینی"]]
        selected.columns = ["Summary", "taskName", "OriginalTime"]
        frames.append(selected)

    combined = pd.concat(frames, ignore_index=True).dropna()
    combined["OriginalTime"] = (
        combined["OriginalTime"].str.replace("hr", "").astype(float) * 60
    )
    return combined


# ============================================================
# Report 1 — Task tracking vs planned time
# ============================================================
def weekly_task_tracking_report(input_csv: str, plan_df: pd.DataFrame, out_path: str) -> None:
    df = pd.read_csv(input_csv)
    df = process_dataframe(df)

    grouped = df.groupby(["Extracted_Summary", "Assignee"], as_index=False).agg(
        {"In Progress": "sum"}
    )

    plan_df["Summary"] = plan_df["Summary"].fillna("").astype(str).str.upper()
    merged = pd.merge(grouped, plan_df,
                      left_on="Extracted_Summary", right_on="Summary", how="inner")

    if {"Task Name", "In Progress"}.issubset(merged.columns):
        merged["In Progress"], merged["taskName"] = merged["taskName"], merged["In Progress"]

    merged["Numeric_Summary"] = merged["Extracted_Summary"].apply(
        lambda x: extract_numeric_summary(x, REGEX_PATTERN)
    )
    merged.sort_values(by="Numeric_Summary", inplace=True)
    merged.drop(columns="Numeric_Summary", inplace=True)

    final_cols = ["Extracted_Summary", "Assignee", "taskName", "In Progress", "OriginalTime"]
    merged = merged[final_cols]

    merged["Progress_Per_Time"] = (
        merged["In Progress"] / merged["OriginalTime"] * 100
    ).round()

    save_to_excel(merged, out_path)


def save_to_excel(df: pd.DataFrame, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
        df.to_excel(writer, sheet_name="Sheet1", index=False)
        workbook = writer.book
        worksheet = writer.sheets["Sheet1"]
        percent_col = df.columns.get_loc("Progress_Per_Time")

        fmt_red = workbook.add_format({"bg_color": "#FFCCCC"})
        fmt_green = workbook.add_format({"bg_color": "#CCFFCC"})
        fmt_yellow = workbook.add_format({"bg_color": "#FFFFCC"})

        rng = (1, percent_col, len(df), percent_col)
        worksheet.conditional_format(*rng, {"type": "cell", "criteria": ">", "value": 100, "format": fmt_red})
        worksheet.conditional_format(*rng, {"type": "cell", "criteria": "<", "value": 100, "format": fmt_green})
        worksheet.conditional_format(*rng, {"type": "cell", "criteria": "=", "value": 100, "format": fmt_yellow})


# ============================================================
# Report 2 — Team productivity breakdown
# ============================================================
def weekly_task_time_report(input_csv: str, in_progress_column: str = "Time Spent") -> pd.DataFrame:
    df = pd.read_csv(input_csv, delimiter=",")
    df[in_progress_column] = pd.to_numeric(df[in_progress_column], errors="coerce")

    df["Summary"] = df["Summary"].fillna("").astype(str).str.upper()
    df["Description"] = df["Description"].fillna("").astype(str)
    df["Labels"] = df["Labels"].fillna("").astype(str)

    df["Combined_Text"] = df["Summary"] + " " + df["Description"] + " " + df["Labels"]

    df["unexpected_flag"] = df["Combined_Text"].apply(unexpected_task_recognition)
    df["meeting_flag"] = df["Combined_Text"].apply(meeting_task_recognition)
    df["planned_flag"] = df["Combined_Text"].apply(
        planned_task_recognition, pattern=r"S\d+W[12]-(\d+)"
    )
    df["unexpected_unplanned_tasks_flag"] = (
        df[["unexpected_flag", "meeting_flag", "planned_flag"]] == 0
    ).all(axis=1).astype(int)

    df[in_progress_column] = df[in_progress_column].fillna(0)

    df["unexpected_time"] = df["unexpected_flag"] * df[in_progress_column]
    df["meeting_time"] = df["meeting_flag"] * df[in_progress_column]
    df["planned_time"] = df["planned_flag"] * df[in_progress_column]
    df["unexpected_unplanned_tasks_time"] = (
        df["unexpected_unplanned_tasks_flag"] * df[in_progress_column]
    )
    return df


def weekly_team_productivity_report(df: pd.DataFrame) -> pd.DataFrame:
    time_cols = [
        "Time Spent", "unexpected_time", "meeting_time",
        "planned_time", "unexpected_unplanned_tasks_time",
    ]
    for col in time_cols:
        df[col] = df[col] / 60  # seconds → minutes

    agg = df.groupby("Assignee").agg(
        total_time_spent=("Time Spent", "sum"),
        total_unexpected_time=("unexpected_time", "sum"),
        total_meeting_time=("meeting_time", "sum"),
        total_planned_time=("planned_time", "sum"),
        total_unexpected_unplanned_tasks_time=("unexpected_unplanned_tasks_time", "sum"),
        count_unexpected_tasks=("unexpected_flag", "sum"),
        count_meetings=("meeting_flag", "sum"),
        count_planned_tasks=("planned_flag", "sum"),
        count_unexpected_unplanned_tasks=("unexpected_unplanned_tasks_flag", "sum"),
    ).reset_index()

    agg["percent_unexpected_time"] = (agg["total_unexpected_time"] / agg["total_time_spent"] * 100).round(1)
    agg["percent_meeting_time"] = (agg["total_meeting_time"] / agg["total_time_spent"] * 100).round(1)
    agg["percent_planned_time"] = (agg["total_planned_time"] / agg["total_time_spent"] * 100).round(1)
    agg["percent_unexpected_unplanned_tasks_time"] = (
        agg["total_unexpected_unplanned_tasks_time"] / agg["total_time_spent"] * 100
    ).round(1)

    agg.rename(columns={
        "total_time_spent": "Total Time Spent",
        "total_unexpected_time": "Total time of Unexpected Tasks",
        "total_meeting_time": "Total time of Meeting tasks",
        "total_planned_time": "Total time of Planned tasks",
        "total_unexpected_unplanned_tasks_time": "Total time of Remained tasks",
        "count_unexpected_tasks": "Count of Unexpected task",
        "count_meetings": "Count of Meetings",
        "count_planned_tasks": "Count of Planned task",
        "count_unexpected_unplanned_tasks": "Count of Remained task",
        "percent_unexpected_time": "Percent of time spent on Unexpected tasks",
        "percent_meeting_time": "Percent of time spent on Meetings",
        "percent_planned_time": "Percent of time spent on Planned tasks",
        "percent_unexpected_unplanned_tasks_time": "Percent of time spent on Remained tasks",
    }, inplace=True)

    return agg


# ============================================================
# Main
# ============================================================
def main():
    input_csv = DATA_DIR + JIRA_FILE_NAME
    planned_xlsx = DATA_DIR + "Tracked_Tasks/" + PLANNED_FILE_NAME
    excel_output = RESULTS_DIR + EXCEL_OUTPUT_NAME
    prod_output = RESULTS_DIR + PROD_REPORT_NAME

    plan_df = merge_excel_sheets_to_dataframe(planned_xlsx)
    weekly_task_tracking_report(input_csv, plan_df, excel_output)

    df = weekly_task_time_report(input_csv, in_progress_column="Time Spent")
    productivity_df = weekly_team_productivity_report(df)

    os.makedirs(RESULTS_DIR, exist_ok=True)
    productivity_df.to_csv(prod_output, sep="\t", index=False)

    print("✅ Weekly reports generated.")


if __name__ == "__main__":
    main()