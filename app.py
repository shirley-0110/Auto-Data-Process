import streamlit as st
import tempfile
import zipfile
import os
import traceback
import pandas as pd
import json

from pipeline.stat_builder import run_pipeline, find_sas_folder

st.set_page_config(
    page_title="Auto Data Process",
    layout="wide"
)

st.title("📊 CRF Schema vs Raw Data")



# =========================================================
# Helper functions
# =========================================================
def style_compare(df: pd.DataFrame):
    """
    根據 STATUS 高亮 compare table
    """
    def highlight_row(row):
        status = str(row.get("STATUS", "")).upper()

        if status == "DATATYPE_MISMATCH":
            return ["background-color: #f8d7da"] * len(row)   # 淡紅
        elif status == "MISSING_IN_RAW":
            return ["background-color: #fff3cd"] * len(row)   # 淡黃
        elif status == "EXTRA_IN_RAW":
            return ["background-color: #d1ecf1"] * len(row)   # 淡藍
        elif status == "MATCH":
            return ["background-color: #d4edda"] * len(row)   # 淡綠
        else:
            return [""] * len(row)

    return df.style.apply(highlight_row, axis=1)


def apply_filters(compare_df: pd.DataFrame,
                  dataset_filter,
                  status_filter,
                  keyword,
                  only_issues):
    """
    套用 compare table filter
    """
    df = compare_df.copy()

    if dataset_filter:
        df = df[df["DATASET"].isin(dataset_filter)]

    if status_filter:
        df = df[df["STATUS"].isin(status_filter)]

    if only_issues:
        df = df[df["STATUS"] != "MATCH"]

    if keyword:
        keyword = keyword.strip().upper()
        df = df[
            df["DATASET"].astype(str).str.upper().str.contains(keyword, na=False)
            | df["VARIABLE"].astype(str).str.upper().str.contains(keyword, na=False)
            | df["LABEL"].astype(str).str.upper().str.contains(keyword, na=False)
        ]

    return df


def render_summary(compare_df: pd.DataFrame):
    total = len(compare_df)

    match_cnt = int((compare_df["STATUS"] == "MATCH").sum()) if "STATUS" in compare_df.columns else 0
    mismatch_cnt = int((compare_df["STATUS"] == "DATATYPE_MISMATCH").sum()) if "STATUS" in compare_df.columns else 0
    missing_cnt = int((compare_df["STATUS"] == "MISSING_IN_RAW").sum()) if "STATUS" in compare_df.columns else 0
    extra_cnt = int((compare_df["STATUS"] == "EXTRA_IN_RAW").sum()) if "STATUS" in compare_df.columns else 0

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("總筆數", total)
    c2.metric("MATCH", match_cnt)
    c3.metric("DATATYPE_MISMATCH", mismatch_cnt)
    c4.metric("MISSING_IN_RAW", missing_cnt)
    c5.metric("EXTRA_IN_RAW", extra_cnt)


def get_review_record(compare_df, selected_dataset, selected_variable):
    df = compare_df[
        (compare_df["DATASET"] == selected_dataset) &
        (compare_df["VARIABLE"] == selected_variable)
    ]
    if len(df) == 0:
        return None
    return df.iloc[0]


def get_schema_detail(schema_df, selected_dataset, selected_variable):
    return schema_df[
        (schema_df["DATASET"] == selected_dataset) &
        (schema_df["VARIABLE"] == selected_variable)
    ]


def get_raw_detail(raw_df, selected_dataset, selected_variable):
    return raw_df[
        (raw_df["DATASET"] == selected_dataset) &
        (raw_df["VARIABLE"] == selected_variable)
    ]


def parse_raw_sample(raw_sample_value):
    """
    RAW_SAMPLE 在 stat_builder.py 是 json.dumps(list) 存成字串
    這裡把它轉回 list
    """
    if pd.isna(raw_sample_value):
        return []

    if isinstance(raw_sample_value, list):
        return raw_sample_value

    try:
        return json.loads(raw_sample_value)
    except Exception:
        return [str(raw_sample_value)]


# =========================================================
# Input area
# =========================================================
st.subheader("Input")

schema_file = st.file_uploader("Upload eCRF Schema", type=["xlsx"])
uploaded_zip = st.file_uploader("Upload CRScube ZIP", type=["zip"])


# =========================================================
# Run area
# =========================================================
if st.button("Run"):

    if not schema_file:
        st.error("Please upload schema")
        st.stop()

    if not uploaded_zip:
        st.error("Please upload CRScube ZIP")
        st.stop()

    try:
        with tempfile.TemporaryDirectory() as tmpdir:

            # save schema
            schema_path = os.path.join(tmpdir, "schema.xlsx")
            with open(schema_path, "wb") as f:
                f.write(schema_file.read())

            # save zip
            zip_path = os.path.join(tmpdir, "data.zip")
            with open(zip_path, "wb") as f:
                f.write(uploaded_zip.read())

            # unzip
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(tmpdir)

            # 找真正放 .sas7bdat 的資料夾
            cube_path = find_sas_folder(tmpdir)

            with st.spinner("Processing..."):
                schema_df, raw_df, compare_df = run_pipeline(
                    cube_path=cube_path,
                    schema_path=schema_path
                )

        st.session_state["schema_df"] = schema_df
        st.session_state["raw_df"] = raw_df
        st.session_state["compare_df"] = compare_df

        st.success("Done ✅")

    except Exception as e:
        st.error("Error occurred")
        st.text(str(e))
        st.text(traceback.format_exc())
        st.stop()


# =========================================================
# Result area
# =========================================================
if "compare_df" in st.session_state:

    schema_df = st.session_state["schema_df"]
    raw_df = st.session_state["raw_df"]
    compare_df = st.session_state["compare_df"]

    # -----------------------------
    # Sidebar
    # -----------------------------
    st.sidebar.header("🔍 Review / Filter")

    view_mode = st.sidebar.radio(
        "View Mode",
        ["Review", "Table"],
        index=0
    )

    dataset_options = sorted(compare_df["DATASET"].dropna().astype(str).unique().tolist()) if "DATASET" in compare_df.columns else []
    status_options = sorted(compare_df["STATUS"].dropna().astype(str).unique().tolist()) if "STATUS" in compare_df.columns else []

    # Table mode filters
    dataset_filter = st.sidebar.multiselect(
        "Dataset Filter",
        options=dataset_options
    )

    status_filter = st.sidebar.multiselect(
        "Status Filter",
        options=status_options
    )

    keyword = st.sidebar.text_input("Keyword Search")

    only_issues = st.sidebar.checkbox("Only Issues", value=True)

    filtered_compare = apply_filters(
        compare_df=compare_df,
        dataset_filter=dataset_filter,
        status_filter=status_filter,
        keyword=keyword,
        only_issues=only_issues
    )

    # Review selectors
    st.sidebar.divider()

    review_dataset = st.sidebar.selectbox(
        "Review Dataset",
        options=dataset_options if dataset_options else [""]
    )

    review_variable_options = []
    if review_dataset:
        tmp_df = compare_df[compare_df["DATASET"] == review_dataset]
        review_variable_options = sorted(tmp_df["VARIABLE"].dropna().astype(str).unique().tolist())

    review_variable = st.sidebar.selectbox(
        "Review Variable",
        options=review_variable_options if review_variable_options else [""]
    )

    # -----------------------------
    # Summary
    # -----------------------------
    st.subheader("Summary")
    render_summary(compare_df)

    st.markdown("""
**Legend**
- 🟩 MATCH  
- 🟥 DATATYPE_MISMATCH  
- 🟨 MISSING_IN_RAW  
- 🟦 EXTRA_IN_RAW  
""")

    st.divider()

    # =====================================================
    # Review Mode
    # =====================================================
    if view_mode == "Review":

        st.subheader("🔎 Review Mode")

        if review_dataset and review_variable:
            record = get_review_record(compare_df, review_dataset, review_variable)
            schema_detail = get_schema_detail(schema_df, review_dataset, review_variable)
            raw_detail = get_raw_detail(raw_df, review_dataset, review_variable)

            st.markdown(f"### {review_dataset} / {review_variable}")

            c1, c2, c3 = st.columns(3)

            # -------------------------
            # Schema panel
            # -------------------------
            with c1:
                st.markdown("#### 📄 Schema")

                if schema_detail.empty:
                    st.warning("No schema definition found")
                else:
                    row = schema_detail.iloc[0]
                    st.write("**Variable**:", row.get("VARIABLE"))
                    st.write("**Label**:", row.get("LABEL"))
                    st.write("**Schema Datatype**:", row.get("SCHEMA_DATATYPE"))
                    st.write("**Schema Datatype Std**:", row.get("SCHEMA_DATATYPE_STD"))

                    with st.expander("Show Schema Rows"):
                        st.dataframe(schema_detail, use_container_width=True)

            # -------------------------
            # Raw panel
            # -------------------------
            with c2:
                st.markdown("#### 📦 Raw Data")

                if raw_detail.empty:
                    st.warning("No raw variable found")
                else:
                    row = raw_detail.iloc[0]
                    st.write("**Variable**:", row.get("VARIABLE"))
                    st.write("**Raw Datatype**:", row.get("RAW_DATATYPE"))
                    st.write("**Raw Datatype Std**:", row.get("RAW_DATATYPE_STD"))

                    st.write("**Sample Values**:")
                    sample_values = parse_raw_sample(row.get("RAW_SAMPLE"))

                    if sample_values:
                        st.code("\n".join(sample_values))
                    else:
                        st.write("No sample available")

                    with st.expander("Show Raw Rows"):
                        st.dataframe(raw_detail, use_container_width=True)

            # -------------------------
            # Compare panel
            # -------------------------
            with c3:
                st.markdown("#### ⚠️ Comparison")

                if record is None:
                    st.warning("No compare record found")
                else:
                    status = str(record.get("STATUS", ""))

                    st.write("**Dataset**:", record.get("DATASET"))
                    st.write("**Variable**:", record.get("VARIABLE"))
                    st.write("**Status**:", status)

                    if status == "MATCH":
                        st.success("MATCH")
                    elif status == "DATATYPE_MISMATCH":
                        st.error("DATATYPE_MISMATCH")
                    elif status == "MISSING_IN_RAW":
                        st.warning("MISSING_IN_RAW")
                    elif status == "EXTRA_IN_RAW":
                        st.info("EXTRA_IN_RAW")
                    else:
                        st.write(status)

                    with st.expander("Show Compare Record"):
                        st.dataframe(pd.DataFrame([record]), use_container_width=True)

        else:
            st.info("Please select review dataset and variable from the sidebar.")

    # =====================================================
    # Table Mode
    # =====================================================
    else:
        st.subheader("📋 Table Mode")
        st.caption(f"Showing {len(filtered_compare)} / {len(compare_df)} rows")

        styled_df = style_compare(filtered_compare)

        # 如果你的 Streamlit 版本對 Styler 支援不好，
        # 可以改成 st.write(styled_df)
        st.dataframe(styled_df, use_container_width=True)

    st.divider()

    # -----------------------------
    # Detail tabs
    # -----------------------------
    tab1, tab2, tab3 = st.tabs(["Schema List", "Raw List", "Comparison Table"])

    with tab1:
        st.dataframe(schema_df, use_container_width=True)
        st.download_button(
            "Download Schema CSV",
            schema_df.to_csv(index=False).encode("utf-8-sig"),
            "schema_list.csv",
            mime="text/csv"
        )

    with tab2:
        st.dataframe(raw_df, use_container_width=True)
        st.download_button(
            "Download Raw CSV",
            raw_df.to_csv(index=False).encode("utf-8-sig"),
            "raw_list.csv",
            mime="text/csv"
        )

    with tab3:
        st.dataframe(compare_df, use_container_width=True)

        d1, d2 = st.columns(2)

        with d1:
            st.download_button(
                "Download Filtered Compare CSV",
                filtered_compare.to_csv(index=False).encode("utf-8-sig"),
                "compare_filtered.csv",
                mime="text/csv"
            )

        with d2:
            st.download_button(
                "Download Full Compare CSV",
                compare_df.to_csv(index=False).encode("utf-8-sig"),
                "compare_full.csv",
                mime="text/csv"
            )
