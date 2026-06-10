import streamlit as st
import tempfile
import zipfile
import os
import traceback
import pandas as pd

from pipeline.stat_builder import run_pipeline, find_sas_folder

st.set_page_config(
    page_title="Auto Data Process",
    layout="wide"
)

st.title("📊 CRF Schema vs Raw Data")





# =========================================================
# Functions
# =========================================================
def style_compare(df):
    def highlight(row):
        status = str(row["STATUS"])
        if status == "DATATYPE_MISMATCH":
            return ["background-color: #f8d7da"] * len(row)
        elif status == "MISSING_IN_RAW":
            return ["background-color: #fff3cd"] * len(row)
        elif status == "EXTRA_IN_RAW":
            return ["background-color: #d1ecf1"] * len(row)
        elif status == "MATCH":
            return ["background-color: #d4edda"] * len(row)
        return [""] * len(row)

    return df.style.apply(highlight, axis=1)


def apply_filters(df, datasets, statuses, keyword, only_issues):
    df = df.copy()

    if datasets:
        df = df[df["DATASET"].isin(datasets)]

    if statuses:
        df = df[df["STATUS"].isin(statuses)]

    if only_issues:
        df = df[df["STATUS"] != "MATCH"]

    if keyword:
        k = keyword.upper()
        df = df[
            df["VARIABLE"].astype(str).str.upper().str.contains(k, na=False) |
            df["DATASET"].astype(str).str.upper().str.contains(k, na=False) |
            df["LABEL"].astype(str).str.upper().str.contains(k, na=False)
        ]

    return df
    # End =========================================================



# Input
schema_file = st.file_uploader("Upload eCRF Schema", type=["xlsx"])
zip_file = st.file_uploader("Upload Dataset ZIP", type=["zip"])

if st.button("Run"):

    if not schema_file or not zip_file:
        st.error("Please upload both schema and zip")
        st.stop()

    with tempfile.TemporaryDirectory() as tmpdir:

        # save schema
        schema_path = os.path.join(tmpdir, "schema.xlsx")
        with open(schema_path, "wb") as f:
            f.write(schema_file.read())

        # save zip
        zip_path = os.path.join(tmpdir, "data.zip")
        with open(zip_path, "wb") as f:
            f.write(zip_file.read())

        # unzip
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(tmpdir)

        cube_path = find_sas_folder(tmpdir)

        schema_df, raw_df, compare_df = run_pipeline(
            cube_path=cube_path,
            schema_path=schema_path
        )

    st.success("Done ✅")

    st.session_state["schema"] = schema_df
    st.session_state["raw"] = raw_df
    st.session_state["compare"] = compare_df

    except Exception as e:
        st.error("Error")
        st.text(traceback.format_exc())


# =========================================================
# Result
# =========================================================
if "compare" in st.session_state:

    schema_df = st.session_state["schema"]
    raw_df = st.session_state["raw"]
    compare_df = st.session_state["compare"]

    # =========================
    # Sidebar Filters
    # =========================
    st.sidebar.header("🔍 Filter")

    datasets = st.sidebar.multiselect(
        "Dataset",
        sorted(compare_df["DATASET"].dropna().unique())
    )

    statuses = st.sidebar.multiselect(
        "Status",
        sorted(compare_df["STATUS"].unique())
    )

    keyword = st.sidebar.text_input("Keyword")

    only_issues = st.sidebar.checkbox("Only Problems", value=True)

    filtered_df = apply_filters(
        compare_df, datasets, statuses, keyword, only_issues
    )

    # =========================
    # Summary (Dashboard)
    # =========================
    st.subheader("📊 Summary")

    col1, col2, col3, col4 = st.columns(4)

    total = len(compare_df)
    match = (compare_df["STATUS"] == "MATCH").sum()
    mismatch = (compare_df["STATUS"] == "DATATYPE_MISMATCH").sum()
    missing = (compare_df["STATUS"] == "MISSING_IN_RAW").sum()

    col1.metric("Total", total)
    col2.metric("Match", match)
    col3.metric("Mismatch", mismatch)
    col4.metric("Missing", missing)

    # =========================
    # Legend
    # =========================
    st.markdown("""
    ### 🎨 Legend
    - 🟩 MATCH  
    - 🟥 DATATYPE_MISMATCH  
    - 🟨 MISSING_IN_RAW  
    - 🟦 EXTRA_IN_RAW  
    """)

    # =========================
    # Tabs
    # =========================
    tab1, tab2, tab3 = st.tabs(["Compare", "Schema", "Raw"])

    with tab1:
        st.dataframe(style_compare(filtered_df), use_container_width=True)
        st.caption(f"Showing {len(filtered_df)} / {len(compare_df)} rows")

        st.download_button(
            "Download Filtered",
            filtered_df.to_csv(index=False),
            "filtered.csv"
        )

    with tab2:
        st.dataframe(schema_df, use_container_width=True)

    with tab3:
        st.dataframe(raw_df, use_container_width=True)


