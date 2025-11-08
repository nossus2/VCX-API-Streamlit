
import streamlit as st
import json, os
from json import JSONDecodeError
from pathlib import Path
import pandas as pd
import time
from typing import Optional, Tuple
from VCX import *
from pathlib import Path
import os, json

import re
import matplotlib.pyplot as plt

# --- LOUD DEBUGGING AT THE VERY TOP ---
st.set_page_config(layout="wide")
st.title("🐞 VCX APP DEBUGGER")

# 1. Prove this file is running
st.header("1. File Execution Test")
st.success("This message is from your local `app.py`. The file is being copied and run correctly!")

# 2. Check Environment Variables
st.header("2. Environment Variable Check")
st.write("Checking variables the container sees:")

try:
    school = os.environ['school']
    client_id = os.environ['client_id']
    secret = os.environ['secret']
    db_path = os.environ['STUDENT_DB_PATH']

    st.json({
        "school": school,
        "client_id": client_id,
        "secret_is_set": f"True, length={len(secret)}", # Never print the secret
        "STUDENT_DB_PATH": db_path
    })
    st.success("All required environment variables are loaded!")
except KeyError as e:
    st.error(f"FATAL: Missing environment variable: {e}. The `--env-file` command failed or the .env file is incomplete.")
    st.stop() # Stop the script here

st.header("3. App Logic")
st.info("Attempting to run the rest of the app...")
st.divider()
# --- END OF LOUD DEBUGGING ---

# ==============================
# Utilities
# ==============================


def resolve_db_path() -> Path:
    # 1) If env var is set AND exists, use it (works in Docker)
    env_path = os.getenv("STUDENT_DB_PATH")
    if env_path:
        p = Path(env_path)
        if p.exists():
            return p

    # 2) Try typical local layouts
    here = Path(__file__).resolve().parent
    candidates = [
        here / "app" / "data" / "student_list.json",             # if this file is inside app/
        here.parent / "app" / "data" / "student_list.json",  # if this file is at project root
    ]
    for c in candidates:
        if c.exists():
            return c

    # 3) Last resort: point to 'app/data/student_list.json' under project root
    # (Create the folder/file on first save if needed)
    return candidates[0]  # or pick the one that matches your structure

DB_PATH = resolve_db_path()
print(DB_PATH)

def load_students():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Student DB not found at: {DB_PATH}")
    with DB_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)

def save_students(data):
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = DB_PATH.with_suffix(DB_PATH.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f)  # same formatting as your prior call
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, DB_PATH)



def validate_email(email: str) -> bool:
    return (
        isinstance(email, str)
        and "@" in email
        and "." in email.split("@")[-1]
        and len(email) <= 254
    )


@st.cache_resource(show_spinner=False)

def to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


# ==============================
# Session State Setup
# ==============================

DEFAULT_STATE = {
    "phase": "idle",  # idle | checking | collecting | ready | error
    "email": "",
    "df": None,
    "error_msg": "",
    "confirmed": False,  # whether user confirmed the email
    "show_confirm_update": False,  # show confirmation UI for DB update
    "is_updating": False,  # update in progress flag
    "last_updated": None,  # timestamp of last successful update
}

for k, v in DEFAULT_STATE.items():
    st.session_state.setdefault(k, v)


def reset_for_new_lookup():
    for k, v in DEFAULT_STATE.items():
        st.session_state[k] = v

# --- init once ---
if "phase" not in st.session_state:
    st.session_state.phase = "idle"
if "email" not in st.session_state:
    st.session_state.email = ""
if "sourcedId" not in st.session_state:
    st.session_state.sourcedId = None
if "error_msg" not in st.session_state:
    st.session_state.error_msg = ""
# keep a separate widget key so typing doesn't fight with app state
if "email_input" not in st.session_state:
    st.session_state.email_input = st.session_state.email
# ==============================
# UI
# ==============================

st.set_page_config(page_title="Student Interim Report", page_icon="📧", layout="wide")
st.title("Student Interim Report")
st.caption("Enter an email, validate against Veracross database, run API pipeline, and export the results.")

# ---- Header action row ----
h1, h2 = st.columns([4, 1])
with h2:
    if st.button("🔄 Update database", help="Refresh or rebuild the database file from the source."):
        st.session_state.show_confirm_update = True
        st.rerun()

# Connection Credentials and VCX Building
c = {
    "school": credentials[0],
    "client_id": credentials[1],
    "client_secret": credentials[2],
    "scopes": ['https://purl.imsglobal.org/spec/or/v1p1/scope/roster-core.readonly',
               'https://purl.imsglobal.org/spec/or/v1p1/scope/roster.readonly', 'classes:list',
               'academics.classes:list', 'academics.classes:read', 'academics.enrollments:list',
               'academics.enrollments:read', 'classes:read', 'report_card.enrollments.qualitative_grades:list']
}
endpointOne = "students"
endpointTwo = "classes"
vc = Veracross(c)
student_list = []
df = None

# ---- Confirmation 'pop-up' (inline). If Streamlit >= 1.32, swap this for st.dialog(...). ----
if st.session_state.show_confirm_update:
    st.warning("Are you sure you want to update the database file? Only choose this if new students have been admitted to the school.", icon="⚠️")
    c1, c2 = st.columns([1,1])
    with c1:
        if st.button("Yes, update now", key="confirm_update_yes"):
            st.session_state.is_updating = True
            st.session_state.show_confirm_update = False
            with st.spinner("Updating database..."):
                try:
                    num = 100
                    student_list.append(vc.pull("oneRoster", endpointOne))
                    student_list.append(vc.pull("oneRoster", endpointOne + "?offset=" + str(num)))
                    student_list.append(vc.pull("oneRoster", endpointOne + "?offset=" + str(num + 100)))
                    save_students(student_list)
                    st.session_state.last_updated = time.strftime("%Y-%m-%d %H:%M:%S")
                    st.success(f"Database updated successfully at {st.session_state.last_updated}.")
                except Exception as e:
                    st.error(f"Database update failed: {e}")
                finally:
                    st.session_state.is_updating = False
            st.rerun()
    with c2:
        if st.button("Cancel", key="confirm_update_no"):
            st.session_state.show_confirm_update = False
            st.info("Update canceled.")
            st.rerun()

student_list = load_students()

# Show last updated timestamp if available
if st.session_state.last_updated:
    st.caption(f"Last database update: {st.session_state.last_updated}")

with st.form("email_form", clear_on_submit=False):
    st.text_input(
    "Student email address",
        key="email",  # <-- the widget writes directly to st.session_state.email
        placeholder="name@indianmountain.org",
        help="Enter the email to look up in Veracross database."
    )
    submitted = st.form_submit_button("Submit", type="primary")

# --- submit handler: do NOT assign to st.session_state.email; it's already set by the widget ---
if submitted:
    typed_email = st.session_state.email.strip()
    if not validate_email(typed_email):
        st.session_state.phase = "error"
        st.session_state.error_msg = (
            "Please enter a valid email address (e.g., first_last@indianmountain.org)."
        )
    else:
        st.session_state.phase = "checking"
        st.session_state.error_msg = ""

# --- lookup (single pass, no loops) ---
if st.session_state.get("phase") == "checking":
    with st.spinner("Checking database for a match..."):
        found_id = find_any_id_by_item(student_list, "email", st.session_state.email, "sourcedId")

    if found_id is None:
        st.session_state.phase = "idle"
        st.session_state.sourcedId = None
        st.info("We couldn't find that email in the database. Please verify and try again.")
        st.stop()  # stop this run cleanly

    # found a match
    st.session_state.sourcedId = found_id
    st.session_state.phase = "collecting"
    st.rerun()  # optional: jump straight to the next UI

# --- elsewhere, guard before using the ID ---
if st.session_state.get("phase") == "collecting":
    sourced_id = st.session_state.sourcedId
    # ... proceed ...
elif st.session_state.get("phase") == "error":
    st.error(st.session_state.error_msg)


writingSpace = st.empty()

# Phase: collecting → run API pipeline
if st.session_state.phase == "collecting":
    with st.spinner("Running API pipeline and filtering data..."):
        try:
            endpointThree = "students/" +  st.session_state.sourcedId + "/classes"
            classes_data = vc.pull("oneRoster", endpointThree)
            print("pulled classes data")
            if classes_data is None:
                # Force a clear error instead of a 'NoneType' crash
                raise Exception(
                    "The vc.pull() function returned None. This most likely indicates an API authorization failure (401 Error), an invalid endpoint, or empty data. Please check your API keys, scopes, and the 'endpointFour' variable.")

            # Extract all veracrossId's from the data
            veracrossId = find_all_matches(classes_data, "classes", "classCode")
            print("pulled veracross data")

            endpointFour = "students/" +  st.session_state.sourcedId
            student_data = vc.pull("oneRoster", endpointFour)
            print("pulled student data")

            # Extract identifier which is the Veracross student ID number
            studentId = student_data.get('user', {}).get('identifier', 'Not found')
            print(studentId)

            # Pull the enrollment data for the student using Veracross ID.
            # This gives us the enrollment ids which we need for grade reports.
            endpointFive = "academics/enrollments"
            enrollments_data = vc.pull("non", endpointFive + "?person_id=" + studentId)

            # Extracts enrollments Ids and class descriptions a list then filters non-academic classes.
            enrollment_ids = []
            for item in enrollments_data:
                enrollment_ids.append(item.get('id'))
                enrollment_ids.append(item.get('class_description'))
            enrollment_ids = filter_pairs(enrollment_ids)

            # Pulls qualitative report card data and adds class descriptions to the lists
            # Counts down through the classes as it pulls data from each one
            qualitative_data = []
            for i in range(0, len(enrollment_ids), 2):
                endpointSix = "report_card/enrollments/" + str(enrollment_ids[i]) + "/qualitative_grades"
                qd = vc.pull("non", endpointSix)
                qualitative_data.append(qd)
                qualitative_data.append(enrollment_ids[i+1])
                writingSpace.markdown(str(int((len(enrollment_ids) - i)/2)) + " classes left to process.")
                if len(enrollment_ids) -i == 2:
                    writingSpace.markdown("")

            # Create an empty list to hold the processed data
            processed_data = []
            # Iterate through the main list using an index
            # This allows us to look at the next item
            for i in range(len(qualitative_data)):
                current_item = qualitative_data[i]

                # Check if the current item is a list (which might contain dicts)
                if isinstance(current_item, list):

                    # The class name is the next item in the list
                    class_name = None
                    if (i + 1) < len(qualitative_data) and isinstance(qualitative_data[i + 1], str):
                        class_name = qualitative_data[i + 1]

                    # Iterate through the dictionaries in this list
                    for item in current_item:
                        # We must check if 'item' is a dictionary,
                        # because the list could be empty (like at the start)
                        if isinstance(item, dict):
                            # Safely get the proficiency level abbreviation
                            abbreviation = item.get('proficiency_level', {}).get('abbreviation')

                            # Check if the abbreviation is NOT None (the filter)
                            if abbreviation is not None:
                                # If it's not None, extract the required information
                                gp_abbr = item.get('grading_period', {}).get('abbreviation')
                                rc_desc = item.get('rubric_criteria', {}).get('description')

                                # Create a new dictionary with the extracted data
                                extracted_item = {
                                    'class': class_name,  # The new field
                                    'grading_period': gp_abbr,
                                    'description': rc_desc,
                                    'score': abbreviation
                                }

                                # Add this new dictionary to our processed list
                                processed_data.append(extracted_item)

            # Creates the table with alignment for numeric columns and a different style
            df = pd.DataFrame(processed_data)
            st.session_state.phase = "ready"
            # table_md = tabulate(processed_data, headers="keys", tablefmt="pipe", colalign=("left", "center", "right"))
            tab_table, tab_chart = st.tabs(["Table", "Charts"])
            # view table with csv download option
            with tab_table:
                st.markdown("### Student Data Table")
                st.dataframe(df)
                csv_bytes = df.to_csv(index=False).encode("utf-8")

                st.download_button(
                    label="📥 Download as CSV",
                    data=csv_bytes,
                    file_name="student_data.csv",
                    mime="text/csv"
                )

            # Data Visualization - to do
            with tab_chart:
                st.caption("Charts for interim scores for each class.")

                # --- Prep + ordering ---
                f = df.copy()
                f["grading_period"] = f["grading_period"].astype(str)
                f["score"] = pd.to_numeric(f["score"], errors="coerce")

                def _period_num(s: str) -> int:
                    m = re.search(r"(\d+)$", s or "")
                    return int(m.group(1)) if m else 9999

                ordered_periods = sorted(f["grading_period"].dropna().unique(), key=_period_num)
                f["grading_period"] = pd.Categorical(
                    f["grading_period"], categories=ordered_periods, ordered=True
                )

                classes = sorted(f["class"].dropna().unique())
                descriptions = sorted(f["description"].dropna().unique())

                if f.empty or not classes:
                    st.info("No data available to plot.")
                    st.stop()

                # --- One tab per class ---
                tabs = st.tabs(classes)
                for tab, cls in zip(tabs, classes):
                    with tab:
                        st.subheader(cls)

                        sub = f[f["class"] == cls]
                        if sub.empty:
                            st.write("No rows for this class.")
                            continue

                        # Pivot: rows = grading_period, columns = description, values = score
                        pivot = (
                            sub.pivot_table(
                                index="grading_period",
                                columns="description",
                                values="score",
                                aggfunc="mean",  # use 'first' if each combo is unique
                            )
                            .sort_index()
                        )

                        # Download CSV for this class
                        csv_bytes = pivot.reset_index().to_csv(index=False).encode("utf-8")
                        st.download_button(
                            label=f"📥 Download {cls} data (CSV)",
                            data=csv_bytes,
                            file_name=f"{cls.replace(' ', '_').lower()}_trends.csv",
                            mime="text/csv",
                            key=f"dl_{cls}"
                        )

                        # Plot: one figure per class; no subplots, no explicit colors
                        fig, ax = plt.subplots(figsize=(8, 4.5))
                        for desc in pivot.columns:
                            ax.plot(
                                pivot.index.astype(str),
                                pivot[desc],
                                marker="o",
                                label=str(desc),
                            )
                        ax.set_xlabel("Grading Period")
                        ax.set_ylabel("Score")
                        ax.set_title(f"{cls} — Scores by Description")
                        ax.grid(True, linestyle="--", alpha=0.3)
                        # Force 0–5 scale regardless of data
                        ax.set_ylim(0.5, 5.5)
                        ax.set_yticks([1, 2, 3, 4, 5])
                        ax.legend(loc="best")
                        st.pyplot(fig)

                        with st.expander("Show rows for this class"):
                            st.dataframe(sub.sort_values(["grading_period", "description"]))

            st.divider()
            left, right = st.columns([1, 1])
            with left:
                if st.button("🔁 New lookup"):
                    reset_for_new_lookup()
                    st.rerun()
            with right:
                st.caption("Tip: Use the **New lookup** button to start fresh.")

        except Exception as e:
            st.session_state.error_msg = f"Something went wrong while fetching data: {e}"
            st.session_state.phase = "error"

# Phase: error → show message
if st.session_state.phase == "error":
    st.error(st.session_state.error_msg or "An unknown error occurred.")
    if st.button("Try again"):
        reset_for_new_lookup()
        st.rerun()

# Idle (first load or after editing email)
if st.session_state.phase == "idle":
    st.info("Enter an email above and click **Lookup** to begin.")
