import os
import io
import tempfile
import pandas as pd
import streamlit as st
from pyproj import CRS
from laspy import LazBackend
import laspy

st.title("LiDAR CRS Projection Checker")
st.write("Upload your `.laz` point cloud files to verify if they use UTM projections.")

# Streamlit file uploader (replaces Google Drive folder linking)
uploaded_files = st.file_uploader("Upload .laz files", type=["laz"], accept_multiple_files=True)

if uploaded_files:
    if st.button("Run CRS Check"):
        non_utm_files = []
        
        with st.spinner("Processing point cloud files..."):
            for uploaded_file in uploaded_files:
                try:
                    # Read uploaded file contents into memory
                    laz_bytes = uploaded_file.read()
                    
                    with laspy.open(io.BytesIO(laz_bytes), laz_backend=LazBackend.Laszip) as reader:
                        header = reader.header
                        crs = header.parse_crs()
                        
                        is_utm = False
                        crs_desc = "Missing or Unknown CRS"
                        
                        if crs:
                            proj_crs = CRS.from_user_input(crs)
                            crs_desc = proj_crs.name
                            
                            if proj_crs.is_projected and "UTM" in proj_crs.name.upper():
                                is_utm = True
                        
                        if not is_utm:
                            non_utm_files.append({
                                "File Name": uploaded_file.name,
                                "Detected CRS": crs_desc
                            })
                except Exception as e:
                    non_utm_files.append({
                        "File Name": uploaded_file.name,
                        "Detected CRS": f"Error: {str(e)}"
                    })
        
        st.subheader("Scan Results")
        st.write(f"Total files scanned: {len(uploaded_files)}")
        st.write(f"Total non-UTM files found: {len(non_utm_files)}")
        
        if non_utm_files:
            df_results = pd.DataFrame(non_utm_files)
            st.dataframe(df_results)
            st.warning("Some files are not using UTM projections.")
        else:
            st.success("All uploaded files are confirmed UTM projections!")
