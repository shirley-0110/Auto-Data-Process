
import streamlit as st
import tempfile
import zipfile
import os
import traceback

from pipeline.stat_builder import run_pipeline, find_sas_folder


st.set_page_config(page_title="Auto Data Process", layout="wide")

st.title("Schema vs Raw Comparator")

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


if st.button("Run"):
    if not schema_file:
        st.error("Please upload schema")
        st.stop()

    # 先存 schema
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        tmp.write(schema_file.read())
        schema_path = tmp.name

    try:
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

                st.write("Extracted files:")
                st.write(os.listdir(tmpdir))

                cube_path = find_sas_folder(tmpdir)

                st.write(f"Final cube path: {cube_path}")
                st.write("Files in folder:")
                st.write(os.listdir(cube_path))

                with st.spinner("Processing..."):
                    schema_df, raw_df, compare_df = run_pipeline(
                        cube_path=cube_path,
                        schema_path=schema_path
                    )

        else:
            if not cube_path:
                st.error("Please enter cube path")
                st.stop()

            with st.spinner("Processing..."):
                schema_df, raw_df, compare_df = run_pipeline(
                    cube_path=cube_path,
                    schema_path=schema_path
                )

        st.success("Done ✅")

        st.subheader("Schema List")
        st.dataframe(schema_df, use_container_width=True)

        st.subheader("Raw List")
        st.dataframe(raw_df, use_container_width=True)

        st.subheader("Comparison Result")
        st.dataframe(compare_df, use_container_width=True)

        st.download_button(
            "Download Comparison CSV",
            compare_df.to_csv(index=False).encode("utf-8-sig"),
            "compare_result.csv",
            mime="text/csv"
        )

    except Exception as e:
        st.error("Error occurred:")
        st.write(str(e))
        st.text(traceback.format_exc())
        st.stop()

