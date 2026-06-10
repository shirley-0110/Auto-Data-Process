
import streamlit as st
import tempfile
import zipfile
import os

from pipeline.stat_builder import run_pipeline

st.title("Auto SDTM Data Processor")

# Step 1
schema_file = st.file_uploader("Upload eCRF Schema", type=["xlsx"])

# Step 2
mode = st.radio("Select Input Mode", ["Local Path", "Upload ZIP"])

cube_path = None

if mode == "Local Path":
    cube_path = st.text_input("Enter CRScube folder path")

elif mode == "Upload ZIP":
    uploaded_zip = st.file_uploader("Upload CRScube ZIP", type=["zip"])

# Run
if st.button("Run"):

    if not schema_file:
        st.error("Please upload schema")
        st.stop()

    # save schema
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

            # ✅ debug
            st.write("Extracted files:", os.listdir(tmpdir))

            # ✅ 自動找真正 SAS folder（你剛剛寫的 function）
            from pipeline.stat_builder import find_sas_folder

            cube_path = find_sas_folder(tmpdir)

            st.write("Final cube path:", cube_path)
            st.write("Files in folder:", os.listdir(cube_path))


            cube_path = tmpdir

    

    if not cube_path:
        st.error("No data path")
        st.stop()

    st.info("Processing...")

    outputs, qc = run_pipeline(
        cube_path=cube_path,
        schema_path=schema_path
    )

    st.success("Done ✅")

    st.subheader("VISIT QC")
    st.dataframe(qc)

    st.download_button(
        "Download QC CSV",
        qc.to_csv(index=False),
        "visit_qc.csv"
    )
