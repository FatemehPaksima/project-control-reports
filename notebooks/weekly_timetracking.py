"""
Weekly Time Tracking Merger
============================
Merges a weekly Jira export with the planned-time spreadsheet and computes
the ratio between actual time spent and original estimated time.

Inputs:
    - Weekly Jira CSV export
    - Planning file with estimated times

Output:
    - CSV report with In Progress, OriginalTime and Percent columns
"""

import re
import os

import pandas as pd


# ============================================================
# Configuration
# ============================================================
INPUT_FILE = "./data/raw/weekly_report.csv"
PLAN_FILE = "./data/raw/planning_time.csv"
OUTPUT_FILE = "./output/Weekly/weekly_merged.csv"

# Pattern for task codes like "S20W1-42"
TASK_PATTERN = r"(S20W1-\d{1,2})"


# ============================================================
# Helpers
# ============================================================
def extract_summary_format(text: str):
    """Extract task code (e.g. S20W1-42) from combined text."""
    match = re.search(TASK_PATTERN, text)
    return match.group(0) if match else None


def extract_numeric_summary(summary: str):
    """Extract numeric part of the task code for sorting."""
    match = re.search(r"S20W1-(\d{1,2})", summary)
    return int(match.group(1)) if match else None


# ============================================================
# Main
# ============================================================
def main(input_file: str, plan_file: str, output_file: str) -> None:
    # ---- Load Jira export ------------------------------------------------
    df = pd.read_csv(input_file)

    # Clean text columns
    df["Summary"] = df["Summary"].fillna("").astype(str).str.upper()
    df["Description"] = df["Description"].fillna("").astype(str)

    # Combine Summary and Description to find task codes
    df["Combined_Text"] = df["Summary"] + " " + df["Description"]
    df["Summary"] = df["Combined_Text"].apply(extract_summary_format)

    # Keep only rows that contain a task code
    df.dropna(subset=["Summary"], inplace=True)

    # Ensure 'In Progress' is numeric
    df["In Progress"] = pd.to_numeric(df["In Progress"], errors="coerce")

    # ---- Group by task code + assignee ----------------------------------
    grouped_df = df.groupby(["Summary", "Assignee"], as_index=False).agg(
        {"In Progress": "sum"}
    )

    # ---- Load planned-time file -----------------------------------------
    plan_df = pd.read_csv(plan_file)
    plan_df["Summary"] = plan_df["Summary"].fillna("").astype(str).str.upper()

    # ---- Merge ----------------------------------------------------------
    merged_df = pd.merge(grouped_df, plan_df, on="Summary", how="inner")

    # Swap values between task name and In Progress (kept for compatibility)
    if "Task Name" in merged_df.columns and "In Progress" in merged_df.columns:
        merged_df["In Progress"], merged_df["taskName"] = (
            merged_df["taskName"],
            merged_df["In Progress"],
        )

    # ---- Sort by numeric part of the code -------------------------------
    merged_df["Numeric_Summary"] = merged_df["Summary"].apply(extract_numeric_summary)
    merged_df.sort_values(by="Numeric_Summary", inplace=True)
    merged_df.drop(columns="Numeric_Summary", inplace=True)

    # ---- Reorder columns ------------------------------------------------
    merged_df = merged_df[
        ["Summary", "Assignee", "taskName", "In Progress", "OriginalTime"]
    ]

    # ---- Compute percentage ---------------------------------------------
    merged_df["Percent"] = (
        merged_df["In Progress"] / merged_df["OriginalTime"] * 100
    ).round()

    # ---- Save -----------------------------------------------------------
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    merged_df.to_csv(output_file, index=False)

    print("Final merged DataFrame:")
    print(merged_df)
    print(f"\n✅ Saved to: {output_file}")


if __name__ == "__main__":
    main(INPUT_FILE, PLAN_FILE, OUTPUT_FILE)