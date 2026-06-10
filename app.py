
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

schema_file = st.file_uploader("Upload eCRF Schema", type=["xlsx"])
uploaded_zip = st.file_uploader("Upload CRScube ZIP", type=["zip"])

if st.button("Run"):

    if not schema_file or not uploaded_zip:
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
            f.write(uploaded_zip.read())

        # unzip
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(tmpdir)

        cube_path = find_sas_folder(tmpdir)

        schema_df, raw_df, compare_df = run_pipeline(
            cube_path=cube_path,
            schema_path=schema_path
        )

    st.success("Done ✅")

    st.dataframe(compare_df)

