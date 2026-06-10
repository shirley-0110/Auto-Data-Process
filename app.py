
import streamlit as st
import tempfile
import zipfile
import os

from pipeline.stat_builder import run_pipeline, find_sas_folder

st.title("Auto Data Processor")

# Upload schema
schema_file = st.file_uploader("Upload eCRF Schema", type=["xlsx"])

# Mode
mode = st.radio("Select Input Mode", ["Local Path", "Upload ZIP"])

cube_path = None

# Local Path
if mode == "Local Path":
    cube_path = st.text_input("Enter CRScube folder path")

# Upload ZIP
elif mode == "Upload ZIP":
    uploaded_zip = st.file_uploader("Upload CRScube ZIP", type=["zip"])


# Run
if st.button("Run"):

    if not schema_file:
        st.error("Please upload schema")
        st.stop()

    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        tmp.write(schema_file.read())
        schema_path = tmp.name

    if mode == "Upload ZIP":

        if not uploaded_zip:
            st.error("Please upload ZIP")
            st.stop()

        with tempfile.TemporaryDirectory() as tmpdir:

            zip_path = os.path.join(tmpdir, "data.zip")

            with open(zip_path, "wb") as f:
                f.write(uploaded_zip.read())

            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(tmpdir)

            st.write("Extracted:", os.listdir(tmpdir))

            cube_path = find_sas_folder(tmpdir)

            st.write("Final path:", cube_path)
            st.write("Files:", os.listdir(cube_path))

            with st.spinner("Processing..."):

                schema_df, raw_df, compare_df = run_pipeline(
                    cube_path=cube_path,
                    schema_path=schema_path
                )

    else:
        with st.spinner("Processing..."):

            schema_df, raw_df, compare_df = run_pipeline(
                cube_path=cube_path,
                schema_path=schema_path
            )

    st.success("Done ✅")

    # ====================================================
    # 顯示結果
    # ====================================================
    st.subheader("Schema List")
    st.dataframe(schema_df)

    st.subheader("Raw List")
    st.dataframe(raw_df)

    st.subheader("Comparison Result")
    st.dataframe(compare_df)

    # Download
    st.download_button(
        "Download Comparison CSV",
        compare_df.to_csv(index=False),
        "compare_result.csv"
    )
