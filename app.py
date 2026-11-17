from concurrent.futures import ThreadPoolExecutor, as_completed
import io
import json
import re
import pandas as pd
from pyproj import CRS
from google.oauth2 import service_account
import streamlit as st
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import laspy
from laspy import LazBackend

st.title("⚡ High-Speed LiDAR CRS Checker")
st.write(
    "Instantly scans multi-GB `.laz` files from Google Drive using service"
    " account auth."
)

folder_link = st.text_input(
    "Google Drive Folder Link:",
    placeholder="https://drive.google.com/drive/folders/...",
)


def extract_folder_id(link):
  match = re.search(r"/folders/([a-zA-Z0-9_-]+)", link)
  if not match:
    if len(link.strip()) > 20 and "/" not in link.strip():
      return link.strip()
    raise ValueError("Invalid Google Drive folder link or ID.")
  return match.group(1)


if folder_link:
  if st.button("Lightning Scan Projections"):
    try:
      folder_id = extract_folder_id(folder_link)

      # Authenticate using the single JSON secret block
      if "GOOGLE_CREDENTIALS_JSON" in st.secrets:
        cred_dict = json.loads(st.secrets["GOOGLE_CREDENTIALS_JSON"])
        credentials = service_account.Credentials.from_service_account_info(
            cred_dict, scopes=["https://www.googleapis.com/auth/drive.readonly"]
        )
        drive_service = build(
            "drive", "v3", credentials=credentials, cache_discovery=False
        )
      else:
        st.error("GOOGLE_CREDENTIALS_JSON not found in Streamlit secrets.")
        st.stop()

      laz_files = []

      def scan_folder(f_id):
        page_token = None
        while True:
          response = (
              drive_service.files()
              .list(
                  q=f"'{f_id}' in parents and trashed=false",
                  pageSize=100,
                  pageToken=page_token,
                  fields="nextPageToken,files(id,name,mimeType,size)",
                  supportsAllDrives=True,
                  includeItemsFromAllDrives=True,
              )
              .execute()
          )

          for item in response.get("files", []):
            if item["mimeType"] == "application/vnd.google-apps.folder":
              scan_folder(item["id"])
            elif item["name"].lower().endswith(".laz"):
              laz_files.append({"id": item["id"], "name": item["name"]})

          page_token = response.get("nextPageToken")
          if not page_token:
            break

      with st.spinner("Indexing folder contents..."):
        scan_folder(folder_id)

      if not laz_files:
        st.warning(
            "No .laz files found. Ensure the folder is shared with your service"
            " account email."
        )
      else:
        st.success(
            f"Found {len(laz_files)} .laz file(s). Scanning headers in"
            " parallel..."
        )

        non_utm_files = []
        progress_bar = st.progress(0)
        completed_count = [0]

        def check_file_header(file_info):
          try:
            # Create a thread-local Drive client for thread safety
            local_service = build(
                "drive", "v3", credentials=credentials, cache_discovery=False
            )
            request = local_service.files().get_media(fileId=file_info["id"])
            buffer = io.BytesIO()

            downloader = MediaIoBaseDownload(
                buffer, request, chunksize=2 * 1024 * 1024
            )
            downloader.next_chunk()
            buffer.seek(0)

            with laspy.open(buffer, laz_backend=LazBackend.Laszip) as reader:
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
                return {
                    "File Name": file_info["name"],
                    "Detected CRS": crs_desc,
                }
          except Exception as e:
            return {
                "File Name": file_info["name"],
                "Detected CRS": f"Error: {str(e)}",
            }
          return None

        with ThreadPoolExecutor(max_workers=5) as executor:
          futures = {
              executor.submit(check_file_header, f): f for f in laz_files
          }
          for future in as_completed(futures):
            result = future.result()
            if result:
              non_utm_files.append(result)

            completed_count[0] += 1
            progress_bar.progress(completed_count[0] / len(laz_files))

        st.subheader("Scan Results")
        st.write(f"Total non-UTM files found: {len(non_utm_files)}")

        if non_utm_files:
          st.dataframe(pd.DataFrame(non_utm_files))
          st.warning("Some files are not using UTM projections.")
        else:
          st.success(
              "All files in the folder are confirmed UTM projections!"
          )

    except Exception as e:
      st.error(f"Error: {str(e)}")
