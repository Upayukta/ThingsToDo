import os
import tempfile
import pandas as pd
import streamlit as st
from pyproj import CRS
from laspy import LazBackend
import laspy

st.title("LiDAR Projection Checker")
st.write("Upload your `.laz` point cloud files to verify their spatial reference systems (UTM vs. Geographic).")

uploaded_files = st.file_uploader("Upload .laz files", type=["laz"], accept_multiple_files=True)

if uploaded_files:
    if st.button("Run Projection Check"):
        results = []

        with st.spinner("Processing point cloud files..."):
            for uploaded_file in uploaded_files:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".laz") as tmp_file:
                    tmp_file.write(uploaded_file.getvalue())
                    tmp_path = tmp_file.name

                try:
                    with laspy.open(tmp_path, laz_backend=LazBackend.Laszip) as las_file:
                        header = las_file.header
                        wkt_string = header.parse_crs().to_wkt()
                        crs = CRS.from_wkt(wkt_string)
                        is_geographic = crs.is_geographic

                        results.append({
                            "File Name": uploaded_file.name,
                            "Coordinate System": crs.name,
                            "Is Geographic (WGS84)": is_geographic
                        })
                except Exception as e:
                    results.append({
                        "File Name": uploaded_file.name,
                        "Coordinate System": f"Error: {str(e)}",
                        "Is Geographic (WGS84)": "N/A"
                    })
                finally:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)

        df_results = pd.DataFrame(results)
        st.dataframe(df_results)

        geo_count = df_results[df_results["Is Geographic (WGS84)"] == True].shape[0]
        if geo_count > 0:
            st.warning(f"Found {geo_count} file(s) mapped to a Geographic Coordinate System instead of UTM.")
        else:
            st.success("All files are correctly projected!")
