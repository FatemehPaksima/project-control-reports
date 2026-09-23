"""
Monthly Reports Generator
===========================
Aggregates Jira CSV exports from multiple projects into a single report
and produces sprint-level metrics.

Outputs:
    - Combined monthly report (CSV)
    - Sprint transition graph (edges)
    - Person-task distribution
    - Meeting, learning, bug, and failure distributions
    - JNMS vs PNMS task distribution
"""

import os
from os import listdir
from os.path import isfile, join
from collections import Counter

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


# ============================================================
# Configuration
# ============================================================
MONTH = "M01"                              # e.g. "Tir403"
OVERALL_REPORT_NAME = f"{MONTH}_report.csv"
REPORTS_DIR = "./data/raw"
RESULTS_DIR = "./output"


# ============================================================
# Helpers
# ============================================================
def get_level(sprint: str):
    """Extract 'Sprint NN' from a string like 'Sprint 15 - level 2'."""
    parts = str(sprint).split(" ")
    if len(parts) > 2:
        return parts[1] + " " + parts[2]
    return None


def format_node_string(input_string: str) -> str:
    """Format 'Sprint N' with zero-padded number (e.g. 'Sprint 05')."""
    parts = input_string.split(" ")
    if len(parts) != 2:
        raise ValueError(f"Expected 'Word Number', got: {input_string!r}")
    word, num_str = parts
    return f"{word} {int(num_str):02d}"


def graph_maker(df_sub: pd.DataFrame):
    """Build sprint transition edges."""
    edges = []
    for ind in df_sub.index:
        zero_level = get_level(df_sub["Sprint"][ind])
        if not zero_level:
            continue
        one_level = (
            get_level(df_sub["Sprint.1"][ind])
            if len(str(df_sub["Sprint.1"][ind])) > 3
            else zero_level
        )
        edges.append((zero_level, one_level))

        if len(str(df_sub["Sprint.2"][ind])) > 3:
            two_level = get_level(df_sub["Sprint.2"][ind])
            edges.append((one_level, two_level))
            edges.append((zero_level, two_level))
        else:
            edges.append((one_level, one_level))
    return edges


# ============================================================
# Step 1 — Combine all project reports into one CSV
# ============================================================
def combine_reports(reports_dir: str, output_name: str) -> str:
    """Merge all Jira CSVs in a directory into a single report."""
    only_files = [f for f in listdir(reports_dir) if isfile(join(reports_dir, f))]
    df = pd.DataFrame()

    for file in only_files:
        if "report" in file.lower():
            continue
        print(f"Processing file: {file}")
        fdf = pd.read_csv(os.path.join(reports_dir, file), sep="|", header=0)
        fdf["Project"] = file.split("_")[0]
        df = pd.concat([df, fdf], ignore_index=True)

    out_path = os.path.join(reports_dir, output_name)
    df.to_csv(out_path, index=False, header=True, sep=",")
    print(f"Combined report saved as: {out_path}")
    return out_path


# ============================================================
# Step 2 — Load combined report
# ============================================================
def load_report(path: str) -> pd.DataFrame:
    try:
        df = pd.read_csv(path, header=0, delimiter=",")
        print("Overall report loaded successfully.")
        return df
    except FileNotFoundError:
        print(f"Error: {path} does not exist.")
    except pd.errors.EmptyDataError:
        print(f"Error: {path} is empty.")
    except pd.errors.ParserError:
        print(f"Error: {path} could not be parsed.")
    return pd.DataFrame()


# ============================================================
# Step 3 — Sprint failure rate
# ============================================================
def sprint_failure_rate(started_tasks: pd.DataFrame) -> np.ndarray:
    rates = []
    print("Sprint i\tissues\tnot_resolved\trate")
    for sprint in range(1, 18):
        issues = started_tasks["Sprint"].str.endswith(f"Sprint {sprint}").sum()
        not_resolved = (
            (started_tasks["Sprint"].str.endswith(f"Sprint {sprint}"))
            & (started_tasks["Sprint.1"].str.contains("Sprint "))
        ).sum()
        rate = not_resolved / issues if issues else 0
        rates.append(rate)
        print(f"Sprint {sprint}\t{issues}\t{not_resolved}\t{rate:.4f}")
    return np.array(rates)


# ============================================================
# Step 4 — Write sprint edges to files
# ============================================================
def write_edges(edges, edge_counts, date_period: str, out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)

    # Plain edges
    with open(os.path.join(out_dir, f"{date_period}_Edges.txt"), "w", encoding="utf8") as fout:
        fout.write("Source\tTarget\n")
        for edge in edges:
            src = int(edge[0].replace("_Resolved", "").replace("Sprint ", ""))
            tgt = int(edge[1].replace("_Resolved", "").replace("Sprint ", ""))
            if src <= tgt:
                fout.write(f"{format_node_string(edge[0])}\t{format_node_string(edge[1])}\n")

    # Weighted edges
    with open(os.path.join(out_dir, f"{date_period}_weighted_Edges.txt"), "w", encoding="utf8") as fout:
        fout.write("Source\tTarget\tWeight\n")
        for item, count in edge_counts.items():
            src = int(item[0].replace("_Resolved", "").replace("Sprint ", ""))
            tgt = int(item[1].replace("_Resolved", "").replace("Sprint ", ""))
            if src <= tgt:
                fout.write(f"{format_node_string(item[0])}\t{format_node_string(item[1])}\t{count}\n")

    # Resolved-weighted edges
    with open(os.path.join(out_dir, f"{date_period}_weighted_Edges_Resolved.txt"), "w", encoding="utf8") as fout:
        fout.write("Source\tTarget\tWeight\n")
        for item, count in edge_counts.items():
            src = int(item[0].replace("_Resolved", "").replace("Sprint ", ""))
            tgt = int(item[1].replace("_Resolved", "").replace("Sprint ", ""))
            if src == tgt:
                fout.write(f"{format_node_string(item[0])}\t{format_node_string(item[1])}_Resolved\t{count}\n")
            elif src < tgt:
                fout.write(f"{format_node_string(item[0])}\t{format_node_string(item[1])}\t{count}\n")


# ============================================================
# Step 5 — Person-task mapping
# ============================================================
def person_task_mapping(sprint_df: pd.DataFrame, date_period: str, out_dir: str) -> None:
    df_sub = sprint_df[["Assignee", "Resolution", "Project"]]
    person_task_df = df_sub.groupby(["Project", "Assignee"]).count().reset_index().head(100)

    with open(os.path.join(out_dir, f"{date_period}_Person_Task.txt"), "w", encoding="utf8") as fout:
        fout.write("Person\tBoard\tCount\n")
        for _, row in person_task_df.iterrows():
            count = row.iloc[2]
            if count <= 0:
                continue
            assignee = str(row.iloc[1])
            parts = assignee.split(".")
            if len(parts) < 2:
                continue
            family_name = parts[0].title()[0] + ". " + parts[1].title()
            fout.write(f"{family_name}\t{row.iloc[0]}\t{count}\n")


# ============================================================
# Step 6 — Meeting / Learning / Bug / Failure distributions
# ============================================================
def meeting_distribution(started_tasks: pd.DataFrame, start: int, end: int,
                         date_period: str, out_dir: str) -> np.ndarray:
    delta = end - start + 1
    rates = np.zeros((delta, 3))

    with open(os.path.join(out_dir, f"{date_period}_Meeting_distribution.txt"), "w", encoding="utf8") as fout:
        fout.write("Sprint i\tTotal_issues\tMeetings\tRate\n")
        for sprint in range(start, end):
            issues = started_tasks[started_tasks["Sprint"].str.endswith(f"Sprint {sprint}")]
            meeting_count = (
                issues["Summary"].str.contains("meeting|Meeting", na=False)
                | issues["Description"].str.contains("meeting|Meeting", na=False)
            ).sum()

            rates[sprint - start, 0] = issues.shape[0]
            rates[sprint - start, 1] = meeting_count
            rates[sprint - start, 2] = meeting_count / issues.shape[0] if issues.shape[0] else 0
            fout.write(f"Sprint {sprint}\t{rates[sprint - start, 0]}\t"
                       f"{rates[sprint - start, 1]}\t{rates[sprint - start, 2]:.4f}\n")
    return rates


def learning_distribution(started_tasks: pd.DataFrame, start: int, end: int,
                          date_period: str, out_dir: str) -> np.ndarray:
    delta = end - start
    rates = np.zeros((delta, 3))

    with open(os.path.join(out_dir, f"{date_period}_Learning_distribution.txt"), "w", encoding="utf8") as fout:
        fout.write("Sprint\tTotal_issues\tLearning Tasks\tRate\n")
        for sprint in range(start, end):
            issues = started_tasks[started_tasks["Sprint"].str.endswith(f"Sprint {sprint}")]
            learning_count = (
                issues["Labels"].str.contains(r"Learning|learning", case=False, na=False)
                | issues["Labels.1"].str.contains(r"Learning|learning", case=False, na=False)
                | issues["Labels.2"].str.contains(r"Learning|learning", case=False, na=False)
                | issues["Summary"].str.contains(r"Learning|learning", case=False, na=False)
                | issues["Description"].str.contains(r"Learning|learning", case=False, na=False)
            ).sum()

            total = issues.shape[0]
            rates[sprint - start, 0] = total
            rates[sprint - start, 1] = learning_count
            rates[sprint - start, 2] = learning_count / total if total else 0
            fout.write(f"Sprint {sprint}\t{total}\t{learning_count}\t"
                       f"{rates[sprint - start, 2]:.2f}\n")
    return rates


def learning_meeting_distribution(started_tasks: pd.DataFrame, start: int, end: int,
                                  date_period: str, out_dir: str) -> np.ndarray:
    delta = end - start + 1
    rates = np.zeros((delta, 3))

    def create_masks(issues):
        learning_mask = (
            issues["Labels"].str.contains(r"Learning|learning", case=False, na=False)
            | issues["Labels.1"].str.contains(r"Learning|learning", case=False, na=False)
            | issues["Labels.2"].str.contains(r"Learning|learning", case=False, na=False)
            | issues["Summary"].str.contains(r"Learning|learning", case=False, na=False)
            | issues["Description"].str.contains(r"Learning|learning", case=False, na=False)
        )
        meeting_mask = (
            issues["Summary"].str.contains("meeting|Meeting", case=False, na=False)
            | issues["Description"].str.contains("meeting|Meeting", case=False, na=False)
        )
        return learning_mask, meeting_mask

    with open(os.path.join(out_dir, f"{date_period}_LearningMeeting_distribution.txt"),
              "w", encoding="utf8") as fout:
        fout.write("Sprint\tTotal_Issues\tEducationalMeetings\tRate\n")
        for sprint in range(start, end):
            issues = started_tasks[started_tasks["Sprint"].str.endswith(f"Sprint {sprint}")]
            learning_mask, meeting_mask = create_masks(issues)
            count = (learning_mask & meeting_mask).sum()
            total = issues.shape[0]
            rates[sprint - start, 0] = total
            rates[sprint - start, 1] = count
            rates[sprint - start, 2] = count / total if total else 0
            fout.write(f"Sprint {sprint}\t{total}\t{count}\t"
                       f"{rates[sprint - start, 2]:.2f}\n")
    return rates


def bug_distribution(started_tasks: pd.DataFrame, start: int, end: int,
                     date_period: str, out_dir: str) -> np.ndarray:
    delta = end - start + 1
    rates = np.zeros((delta, 3))

    with open(os.path.join(out_dir, f"{date_period}_Bug_distribution.txt"),
              "w", encoding="utf8") as fout:
        fout.write("Sprint i\tTotal_issues\tBug Tasks\tRate\n")
        for sprint in range(start, end):
            issues = started_tasks[started_tasks["Sprint"].str.endswith(f"Sprint {sprint}")]
            bug_count = issues["Issue Type"].str.contains(r"Bug", case=False, na=False).sum()
            total = issues.shape[0]
            rates[sprint - start, 0] = total
            rates[sprint - start, 1] = bug_count
            rates[sprint - start, 2] = bug_count / total if total else 0
            fout.write(f"Sprint {sprint}\t{total}\t{bug_count}\t"
                       f"{rates[sprint - start, 2]:.2f}\n")
    return rates


def bug_task_distribution(started_tasks: pd.DataFrame, start: int, end: int,
                          date_period: str, out_dir: str) -> np.ndarray:
    delta = end - start + 1
    rates = np.zeros((delta, 4))

    with open(os.path.join(out_dir, f"{date_period}_Bug_task_distribution.txt"),
              "w", encoding="utf8") as fout:
        fout.write("Sprint #\tBugs\tTasks\tBug/Task\tBug/All\n")
        for sprint in range(start, end):
            issues = started_tasks[started_tasks["Sprint"].str.endswith(f"Sprint {sprint}")]
            task_group = issues.groupby(["Issue Type"]).count()["Issue id"].reset_index(name="count")

            bugs = task_group.loc[task_group["Issue Type"] == "Bug", "count"]
            tasks = task_group.loc[task_group["Issue Type"] == "Task", "count"]
            bug_count = bugs.iloc[0] if not bugs.empty else 0
            task_count = tasks.iloc[0] if not tasks.empty else 0

            rates[sprint - start, 0] = bug_count
            rates[sprint - start, 1] = task_count
            rates[sprint - start, 2] = bug_count / task_count if task_count else 0
            rates[sprint - start, 3] = bug_count / (bug_count + task_count) if (bug_count + task_count) else 0

            fout.write(f"Sprint {sprint}\t{rates[sprint - start, 0]}\t"
                       f"{rates[sprint - start, 1]}\t"
                       f"{rates[sprint - start, 2]:.2f}\t"
                       f"{rates[sprint - start, 3]:.2f}\n")
    return rates


def failure_distribution(started_tasks: pd.DataFrame, start: int, end: int,
                         date_period: str, out_dir: str) -> np.ndarray:
    delta = end - start + 1
    rates = np.zeros((delta, 3))

    with open(os.path.join(out_dir, f"{date_period}_Failure_distribution.txt"),
              "w", encoding="utf8") as fout:
        fout.write("Sprint i\tissues\tnot_resolved\trate\n")
        for sprint in range(start, end):
            issues = started_tasks["Sprint"].str.endswith(f"Sprint {sprint}").sum()
            not_resolved = (
                (started_tasks["Sprint"].str.endswith(f"Sprint {sprint}"))
                & (started_tasks["Sprint.1"].str.contains("Sprint "))
            ).sum()
            rates[sprint - start, 0] = issues
            rates[sprint - start, 1] = not_resolved
            rates[sprint - start, 2] = not_resolved / issues if issues else 0
            fout.write(f"Sprint {sprint}\t{issues}\t{not_resolved}\t"
                       f"{rates[sprint - start, 2]:.2f}\n")
    return rates


def jnms_vs_pnms_distribution(started_tasks: pd.DataFrame, start: int, end: int,
                              date_period: str, out_dir: str) -> np.ndarray:
    delta = end - start + 1
    rates = np.zeros((delta, 3))

    with open(os.path.join(out_dir, f"{date_period}_PROJ_A_vs_PROJ_B_distribution.txt"),
              "w", encoding="utf8") as fout:
        fout.write("Sprint i\tTotal_issues\tPROJ_A\tPROJ_A Rate\n")
        for sprint in range(start, end + 1):
            issues = started_tasks[started_tasks["Sprint"].str.endswith(f"Sprint {sprint}")]
            jnms_count = (
                issues["Labels"].str.contains(r"JNMS|J-NMS|jnms", case=False, na=False)
                | issues["Labels.1"].str.contains(r"JNMS|J-NMS|jnms", case=False, na=False)
                | issues["Labels.2"].str.contains(r"JNMS|J-NMS|jnms", case=False, na=False)
                | issues["Summary"].str.contains(r"JNMS|J-NMS|jnms", case=False, na=False)
                | issues["Description"].str.contains(r"JNMS|J-NMS|jnms", case=False, na=False)
            ).sum()

            if issues.shape[0] > 0:
                rates[sprint - start, 0] = issues.shape[0]
                rates[sprint - start, 1] = jnms_count
                rates[sprint - start, 2] = jnms_count / rates[sprint - start, 0]
            else:
                rates[sprint - start, :] = [0, -1, -1]

            fout.write(f"Sprint {sprint}\t{rates[sprint - start, 0]}\t"
                       f"{rates[sprint - start, 1]}\t"
                       f"{rates[sprint - start, 2]:.2f}\n")
    return rates


# ============================================================
# Step 7 — Save sprint records
# ============================================================
def save_sprint_records(started_tasks: pd.DataFrame, start: int, end: int,
                        out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    selected_columns = ["Project", "Assignee", "Summary", "Description"]
    for sprint in range(start, end + 1):
        print(f"We are in sprint {sprint}")
        issues = started_tasks[started_tasks["Sprint"].str.endswith(f"Sprint {sprint}")]
        if issues.shape[0] > 0:
            issues[selected_columns].to_csv(
                os.path.join(out_dir, f"Sprint={sprint}.txt"),
                header=True, index=False, sep="\t",
            )


# ============================================================
# Main pipeline
# ============================================================
def main():
    os.makedirs(RESULTS_DIR, exist_ok=True)

    # 1) Combine reports
    overall_path = combine_reports(REPORTS_DIR, OVERALL_REPORT_NAME)

    # 2) Load
    df = load_report(overall_path)
    if df.empty:
        return

    # 3) Filter rows with a Sprint value
    started_tasks = df[~df["Sprint"].isna()]

    # 4) Range-based analysis (change start/end to match your data)
    start_sprint, end_sprint = 15, 20
    sprint_indices = [f"Sprint {s}" for s in range(start_sprint, end_sprint + 1)]
    sprint_criteria = "|".join(sprint_indices)
    sprint_df = started_tasks[started_tasks["Sprint"].str.contains(sprint_criteria, na=False)]

    # 5) Edges
    df_sub = sprint_df[["Sprint", "Sprint.1", "Sprint.2", "Project"]].copy()
    df_sub.fillna(0, inplace=True)
    edges = graph_maker(df_sub)
    edge_counts = Counter(edges)

    date_period = f"{start_sprint}-{end_sprint}_Report"
    write_edges(edges, edge_counts, date_period, RESULTS_DIR)

    # 6) Person-task
    person_task_mapping(sprint_df, date_period, RESULTS_DIR)

    # 7) Distributions
    meeting_distribution(started_tasks, start_sprint, end_sprint + 1, date_period, RESULTS_DIR)
    learning_distribution(started_tasks, start_sprint, end_sprint, date_period, RESULTS_DIR)
    learning_meeting_distribution(started_tasks, start_sprint, end_sprint, date_period, RESULTS_DIR)
    bug_distribution(started_tasks, start_sprint, end_sprint, date_period, RESULTS_DIR)
    bug_task_distribution(started_tasks, start_sprint, end_sprint, date_period, RESULTS_DIR)
    failure_distribution(started_tasks, start_sprint, end_sprint, date_period, RESULTS_DIR)
    jnms_vs_pnms_distribution(started_tasks, 13, 16, date_period, RESULTS_DIR)

    # 8) Save records
    save_sprint_records(started_tasks, 1, 18, os.path.join(RESULTS_DIR, "Sprints"))

    # 9) Plot failure rate
    rates = sprint_failure_rate(started_tasks)
    plt.figure()
    plt.plot(rates * 100, "*-")
    plt.title("Sprint Failure Rate (%)")
    plt.xlabel("Sprint")
    plt.ylabel("Failure Rate (%)")
    plt.grid()
    plt.savefig(os.path.join(RESULTS_DIR, "failure_rate.png"), dpi=120)
    plt.close()

    print("\n✅ Monthly reports generation complete.")


if __name__ == "__main__":
    main()