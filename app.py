import io
import re
import pandas as pd
import streamlit as st
from pyproj import CRS
from laspy import LazBackend
import laspy
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

st.title("LiDAR CRS Projection Checker")
st.write(
    "Paste a public Google Drive folder link containing `.laz` files to check"
    " their projections."
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
  if st.button("Scan and Check Projections"):
    try:
      folder_id = extract_folder_id(folder_link)

      # Build Drive service using an API key if provided in Streamlit secrets,
      # or build without credentials for public files
      api_key = st.secrets.get("GOOGLE_API_KEY", None)
      if api_key:
        drive_service = build(
            "drive",
            "v3",
            developerKey=api_key,
            cache_discovery=False,
        )
      else:
        # Fallback build without auth (works for fully public 'Anyone with link' items)
        drive_service = build(
            "drive", "v3", cache_discovery=False
        )

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

      with st.spinner("Scanning Google Drive folder for .laz files..."):
        scan_folder(folder_id)

      if not laz_files:
        st.warning(
            "No .laz files found. Note: Folders under 'Shared with me' require"
            " an API Key or making sure the folder is publicly accessible."
        )
      else:
        st.success(f"Found {len(laz_files)} .laz file(s). Processing...")
        non_utm_files = []

        progress_bar = st.progress(0)
        for i, file_info in enumerate(laz_files):
          try:
            request = drive_service.files().get_media(fileId=file_info["id"])
            buffer = io.BytesIO()
            downloader = MediaIoBaseDownload(buffer, request)
            done = False
            while not done:
              _, done = downloader.next_chunk()
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
                non_utm_files.append({
                    "File Name": file_info["name"],
                    "Detected CRS": crs_desc,
                })
          except Exception as e:
            non_utm_files.append({
                "File Name": file_info["name"],
                "Detected CRS": f"Error: {str(e)}",
            })

          progress_bar.progress((i + 1) / len(laz_files))

        st.subheader("Scan Results")
        st.write(f"Total non-UTM files found: {len(non_utm_files)}")

        if non_utm_files:
          st.dataframe(pd.DataFrame(non_utm_files))
          st.warning("Some files are not using UTM projections.")
        else:
          st.success("All files in the folder are confirmed UTM projections!")

    except Exception as e:
      st.error(f"Error accessing Google Drive folder: {str(e)}")
