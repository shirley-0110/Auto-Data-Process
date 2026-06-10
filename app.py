
import streamlit as st
import tempfile
import zipfile
import os
import traceback
import pandas as pd

from Pipeline.stat_builder import run_pipeline, find_sas_folder

st.set_page_config(
    page_title="Schema vs Raw Comparator",
    layout="wide"
)

st.title("📊 Schema vs Raw Comparator")

# =========================================================
# Helper functions
# =========================================================
def style_compare(df: pd.DataFrame):
    """
    根據 STATUS 高亮整列
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


# =========================================================
# Input area
# =========================================================
with st.container():
    st.subheader("Input")

    input_mode = st.radio(
        "Input Mode",
        ["Upload ZIP", "Local Path"],
        horizontal=True
    )

    schema_file = st.file_uploader("Upload eCRF Schema", type=["xlsx"])

    uploaded_zip = None
    cube_path = None

    if input_mode == "Upload ZIP":
        uploaded_zip = st.file_uploader("Upload CRScube ZIP", type=["zip"])
    else:
        cube_path = st.text_input("Enter CRScube folder path")


# =========================================================
# Run
# =========================================================
if st.button("Run"):

    if not schema_file:
        st.error("Please upload schema")
        st.stop()

    try:
        # 先存 schema
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
            tmp.write(schema_file.read())
            schema_path = tmp.name

        if input_mode == "Upload ZIP":
            if not uploaded_zip:
                st.error("Please upload ZIP")
                st.stop()

            with tempfile.TemporaryDirectory() as tmpdir:

                zip_path = os.path.join(tmpdir, "data.zip")
                with open(zip_path, "wb") as f:
                    f.write(uploaded_zip.read())

                with zipfile.ZipFile(zip_path, "r") as zip_ref:
                    zip_ref.extractall(tmpdir)

                # 找到真正 sas folder
                cube_path = find_sas_folder(tmpdir)

                with st.spinner("Processing..."):
                    schema_df, raw_df, compare_df = run_pipeline(
                        cube_path=cube_path,
                        schema_path=schema_path
                    )

        else:
            if not cube_path or not os.path.exists(cube_path):
                st.error("Please enter a valid local path")
                st.stop()

            with st.spinner("Processing..."):
                schema_df, raw_df, compare_df = run_pipeline(
                    cube_path=cube_path,
                    schema_path=schema_path
                )

        # 存到 session_state，讓 filter 不需要重跑
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

    st.divider()
    st.subheader("Summary")
    render_summary(compare_df)

    st.divider()
    st.subheader("Filter")

    f1, f2, f3, f4 = st.columns([2, 2, 2, 1])

    dataset_options = sorted(compare_df["DATASET"].dropna().astype(str).unique().tolist()) if "DATASET" in compare_df.columns else []
    status_options = sorted(compare_df["STATUS"].dropna().astype(str).unique().tolist()) if "STATUS" in compare_df.columns else []

    dataset_filter = f1.multiselect(
        "Filter by Dataset",
        options=dataset_options
    )

    status_filter = f2.multiselect(
        "Filter by Status",
        options=status_options,
        default=[]
    )

    keyword = f3.text_input("Search keyword (dataset / variable / label)")

    only_issues = f4.checkbox("Only Issues", value=False)

    filtered_compare = apply_filters(
        compare_df=compare_df,
        dataset_filter=dataset_filter,
        status_filter=status_filter,
        keyword=keyword,
        only_issues=only_issues
    )

    st.caption(f"顯示筆數：{len(filtered_compare)} / {len(compare_df)}")

    tab1, tab2, tab3 = st.tabs(["Schema List", "Raw List", "Comparison Result"])

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
        st.markdown("### Comparison Result")

        # 高亮
        styled_df = style_compare(filtered_compare)

        # 如果你的 Streamlit 版本不支援 styling 顏色，
        # 可以把 st.dataframe 改成 st.write(styled_df)
        st.dataframe(styled_df, use_container_width=True)

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


