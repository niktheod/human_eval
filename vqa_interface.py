import streamlit as st
import json
import requests
import random
from io import BytesIO, StringIO # Import StringIO for text
from PIL import Image
from datetime import datetime
import os
import time

# Imports for Google Drive API
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
from googleapiclient.errors import HttpError
import base64 # Needed if credentials are base64 encoded (not in this example format, but good to know)
from datetime import datetime


SCOPES = ['https://www.googleapis.com/auth/drive.file'] # Scope for accessing specific files created/opened by the app

def get_drive_service():
    """Authenticates and returns a Google Drive service object."""
    try:
        # Load credentials from Streamlit secrets
        creds_info = st.secrets["google_credentials"]
        creds = service_account.Credentials.from_service_account_info(
            creds_info, scopes=SCOPES)

        service = build('drive', 'v3', credentials=creds)
        return service
    except Exception as e:
        st.error(f"Error authenticating with Google Drive: {e}")
        return None

def main():
    st.set_page_config(layout="wide")
    st.title("")

    # Initialize session state
    if 'data' not in st.session_state:
        st.session_state['data'] = get_random_data()
        st.session_state['question_index'] = 0
        st.session_state['responses'] = []
        st.session_state['score'] = 0
        st.session_state['combined_results'] = {}
        st.session_state['displayed_index'] = -1
        st.session_state['displayed_image_data'] = None

    data = st.session_state['data']
    if not data:
        st.error("Could not load data. Please check data.json and data loading logic.")
        return

    idx = st.session_state['question_index']

    if idx < len(data):
        item = data[idx]

        # Wrap the question display area in a container
        # This can help stabilize the layout of the grouped elements
        question_container = st.container()

        with question_container:
            # --- Conditional Image Loading Logic ---
            if st.session_state['displayed_index'] != idx:
                img_url = item.get('image_path')
                st.session_state['displayed_image_data'] = None
                if img_url:
                    try:
                        with st.spinner(f"Loading image for question {idx+1}..."):
                            response = requests.get(img_url, timeout=10)
                            response.raise_for_status()
                            image_data = BytesIO(response.content)
                            st.session_state['displayed_image_data'] = Image.open(image_data)
                        st.session_state['displayed_index'] = idx
                    except requests.exceptions.Timeout:
                        st.error(f"Timeout loading image for question {idx+1}.")
                        st.session_state['displayed_index'] = idx
                    except requests.exceptions.RequestException as e:
                        st.error(f"Error loading image for question {idx+1}: {e}")
                        st.session_state['displayed_index'] = idx
                    except Exception as e:
                           st.error(f"Error processing image for question {idx+1}: {e}")
                           st.session_state['displayed_index'] = idx
                else:
                    st.warning(f"No image_path provided for question {idx+1}.")
                    st.session_state['displayed_index'] = idx


            # --- Image Display Logic ---
            if st.session_state['displayed_image_data'] is not None and st.session_state['displayed_index'] == idx:
                   st.image(st.session_state['displayed_image_data'], caption=f"Question {idx+1}", width=1200)
            elif st.session_state['displayed_index'] == idx:
                   st.warning(f"Image not available for question {idx+1}.")


            # --- Question, Options, and Button (always displayed FOR THIS QUESTION) ---
            st.subheader(item.get('question', f'Question {idx+1}: No question text provided'))
            options = item.get('options', [])
            correct_idx = item.get('correct_answer')

            if not options:
                st.warning(f"No options for question {idx+1}. Skipping.")
                st.session_state['question_index'] += 1
                st.session_state['displayed_index'] = -1
                st.session_state['displayed_image_data'] = None
                st.rerun()
                return

            selected = st.radio("Select an answer:", options, key=f"opt_{idx}", index=None)

            # --- Submit Button Logic ---
            if st.button("Submit", key=f"sub_{idx}"):
                if selected is None:
                   st.warning("Please select an answer before submitting.")
                else:
                    # --- Process Submission ---
                    try:
                        sel_idx = options.index(selected)
                    except ValueError:
                        sel_idx = -1
                        st.error("Internal error: Invalid selection value.")
                        return

                    st.session_state['responses'].append(sel_idx)
                    correct = (sel_idx == correct_idx)
                    if correct:
                        st.session_state['score'] += 1

                    # Track combined results
                    t = item.get('type')
                    c = item.get('category')
                    d = item.get('distance')
                    key = (t, c, d)
                    if key not in st.session_state['combined_results']:
                        st.session_state['combined_results'][key] = [0, 0]
                    st.session_state['combined_results'][key][1] += 1
                    if correct:
                        st.session_state['combined_results'][key][0] += 1

                    # Wait a moment before moving to the next question to show feedback
                    time.sleep(1)

                    # --- Move to next question and RERUN ---
                    st.session_state['question_index'] += 1
                    st.rerun()

    else:
        # Evaluation Finished
        st.subheader("Evaluation Finished!")
        total = len(st.session_state['data'])
        correct = st.session_state['score']
        accuracy = (correct / total * 100) if total else 0

        combined = st.session_state['combined_results']
        # if combined:
        #     for (t, c, d), (corr, tot) in sorted(combined.items(), key=lambda x: (x[0][0], x[0][1], x[0][2] is None, x[0][2] if x[0][2] is not None else float('inf'))):
        #         label = 'None' if d is None else d
        #         acc = (corr / tot * 100) if tot else 0
        #         st.write(f"Type {t} | Category {c} | Distance {label}: {corr}/{tot} correct ({acc:.2f}%)")
        # else:
        #     st.write("No combined results recorded.")

        if 'results_saved' not in st.session_state:
            save_combined_results_json(st.session_state['combined_results'])
            st.session_state['results_saved'] = True

        st.success("Thank you!")


def get_random_data(num_per=1):
    """Loads data and selects a specified number of items per category/distance combination."""
    data = load_data()
    types = ["synth", "real"]
    cat_dist = {
        "synth": {1: [50,40,30,20,10,5,None], 2:[50,40,30,20,10,5],
                  3:[50,40,30,20,10,5,None], 4:[50,40,30,20,10,5],
                  5:[50,40,30,20,10], 6:[50,40,30,20,10]},
        "real": {1:[50,40,30,20,10,5,None], 2:[50,40,30,20,10,5],
                 3:[50,40,30,20,10,5,None], 4:[50,40,30,20,10,5]}
    }
    rand_list = []

    for t in types:
        if t in cat_dist:
            for cat, dists in cat_dist[t].items():
                    if cat in cat_dist[t]:
                        for d in dists:
                            filt = [i for i in data if i.get('type') == t and i.get('category') == cat and i.get('distance') == d]
                            if filt:
                                num_to_select = min(num_per, len(filt))
                                if num_to_select > 0:
                                    try:
                                        selected_items = random.sample(filt, num_to_select)
                                        rand_list.extend(selected_items)
                                    except ValueError as e:
                                        st.warning(f"Could not sample {num_to_select} items for Type: {t}, Category: {cat}, Distance: {d}. Available: {len(filt)}. Error: {e}")

    if not rand_list:
           st.error("No data found matching the specified types, categories, and distances.")

    random.shuffle(rand_list)
    st.info(f"Loaded {len(rand_list)} evaluation questions.")
    return rand_list


def load_data():
    """Loads data from data.json."""
    path = "./data.json"
    data = []
    if not os.path.exists(path):
        st.error(f"Data file not found at {path}. Please ensure data.json exists.")
        return []

    try:
        with open(path, 'r') as f:
            data = json.load(f)

        if not isinstance(data, list):
            st.error("Data format error: data.json should contain a JSON list.")
            return []

        required_keys = ['type', 'category', 'distance', 'image_path', 'question', 'options', 'correct_answer']
        valid_data = []
        for i, item in enumerate(data):
            if not isinstance(item, dict):
                   st.warning(f"Data format error: Item at index {i} is not a dictionary. Skipping.")
                   continue
            is_valid = True
            for key in required_keys:
                if key not in item:
                    st.warning(f"Missing key '{key}' in item at index {i}. Skipping.")
                    is_valid = False
                    break
            if not is_valid:
                continue

            if 'options' in item and 'correct_answer' in item:
                   if not isinstance(item['correct_answer'], int) or not (0 <= item['correct_answer'] < len(item['options'])):
                       st.warning(f"Invalid correct_answer index ({item.get('correct_answer')}) for item at index {i}. Must be a valid index for options. Skipping.")
                       continue

            valid_data.append(item)

        if not valid_data:
               st.error("No valid question data found in data.json after parsing and validation.")

        return valid_data

    except json.JSONDecodeError:
        st.error(f"JSON decoding error: Could not parse {path}. Please check the JSON syntax.")
        return []
    except Exception as e:
        st.error(f"Loading error: {e}")
        return []

def save_combined_results_json(results):
    """
    Saves combined_results into a JSON file on Google Drive.
    Searches for an existing file by name and updates it, or creates a new one.
    Handles reading and writing data as bytes.
    """
    drive_service = get_drive_service()
    if not drive_service:
        st.error("Cannot save results: Google Drive service not available due to authentication failure.")
        return

    # Define the file name and optionally a folder ID
    timestamp_ms = int(time.time() * 1000)
    file_name = f"{timestamp_ms}.json"
    # Replace with your actual Google Drive Folder ID if you shared a specific folder
    # You can get the folder ID from the URL when viewing the folder in Google Drive
    # Example URL: https://drive.google.com/drive/folders/YOUR_FOLDER_ID_HERE
    # If folder_id is None, the file will be saved in the service account's root Drive folder
    # It's highly recommended to use a specific folder.
    folder_id = "1B6Q1DwCCK4JpIZKgZemkZidq6zTrmca_"
    if folder_id is None:
           st.warning(f"No specific folder_id provided. Results will be saved to the service account's root Drive folder as '{file_name}'.")
           st.warning("Consider using a dedicated folder for better organization and control.")

    timestamp = datetime.now().isoformat()

    # Structure the current session results
    nested = {}
    for (t, c, d), (corr, tot) in results.items():
        label = 'None' if d is None else str(d)
        if t not in nested: nested[t] = {}
        if c not in nested[t]: nested[t][c] = {}
        nested[t][c][label] = {"correct": corr, "total": tot}

    session_entry = {"timestamp": timestamp, "results": nested}

    existing_data = []
    file_id = None

    # 1. Search for the existing file in Google Drive
    try:
        q = f"name='{file_name}' and mimeType='application/json' and trashed=false"
        if folder_id:
            # Search within a specific folder
            q += f" and '{folder_id}' in parents"
        else:
            # If no folder_id specified, limit search to root for slightly more control,
            # though service account scope might handle this.
             q += " and 'root' in parents"


        results = drive_service.files().list(
            q=q,
            spaces='drive',
            fields='files(id, name, parents)', # Request parents field to confirm location if needed
            # Add corpus='user' or corpus='domain' if searching shared drives
            # corpus='user', # This is often the default for service accounts accessing their own or shared-with-them files
            # includeItemsFromAllDrives=True and supportsAllDrives=True # Needed for Shared Drives
        ).execute()

        items = results.get('files', [])

        # Filter items to ensure they are in the correct folder if folder_id is specified
        # This handles cases where files of the same name might exist elsewhere accessible to the service account
        if folder_id:
            items = [item for item in items if folder_id in item.get('parents', [])]
            # If multiple files with the same name exist in the folder, pick the first one
            if len(items) > 1:
                   st.warning(f"Multiple files named '{file_name}' found in folder ID '{folder_id}'. Using the first one found.")

        if items:
            # Assuming the (filtered) first result is the correct file
            file_id = items[0]['id']
            st.info(f"Found existing results file on Drive: {file_name} (ID: {file_id})")

            # 2. Download existing content
            try:
                request = drive_service.files().get_media(fileId=file_id)
                downloaded_bytes = BytesIO() # Use BytesIO for downloading binary content
                downloader = MediaIoBaseDownload(downloaded_bytes, request)
                done = False
                # Optional: Show download progress
                # progress_bar = st.progress(0, text="Downloading existing results...")
                while done is False:
                    status, done = downloader.next_chunk()
                    # progress_bar.progress(int(status.progress() * 100), text=f"Downloading existing results ({int(status.progress() * 100)}%)...")
                # progress_bar.empty() # Clear progress bar after completion

                downloaded_bytes.seek(0) # Rewind to the beginning of the BytesIO buffer

                # Decode bytes to string, handle potential empty file
                content_bytes = downloaded_bytes.read()
                if content_bytes.strip(): # Check if content is not just whitespace bytes
                    content_str = content_bytes.decode('utf-8')
                    existing_data = json.loads(content_str)
                    if not isinstance(existing_data, list):
                        st.warning(f"Existing Drive file '{file_name}' content is not a list. Starting a new results list.")
                        existing_data = []
                else:
                   st.info(f"Existing Drive file '{file_name}' is empty. Starting a new results list.")
                   existing_data = []

            except HttpError as download_error:
                st.error(f"An API error occurred downloading existing file from Drive: {download_error}")
                # If download fails, proceed as if file was empty or corrupt
                existing_data = []
                st.warning("Could not download existing results. Starting a new results list.")
            except json.JSONDecodeError:
                st.error(f"Existing Drive file '{file_name}' is corrupt (JSON error). Starting a new results list.")
                existing_data = []
            except Exception as e:
                   st.error(f"An unexpected error occurred reading existing Drive file '{file_name}': {e}. Starting a new results list.")
                   existing_data = []

        else:
            file_id = None # Ensure file_id is None if not found

    except HttpError as search_error:
        st.error(f"An API error occurred searching for file on Drive: {search_error}")
        # If search fails, proceed as if file doesn't exist
        file_id = None
        st.warning("Could not search for existing results file. Will attempt to create a new one.")
    except Exception as e:
           st.error(f"An unexpected error occurred searching for file on Drive: {e}")
           file_id = None
           st.warning("Could not search for existing results file. Will attempt to create a new one.")


    # 3. Append the new session data
    existing_data.append(session_entry)
    new_content = json.dumps(existing_data, indent=2)

    # --- Prepare content for Upload (Encode to Bytes) ---
    # Encode the JSON string into bytes using UTF-8
    new_content_bytes = new_content.encode('utf-8')

    # Use BytesIO to create a bytes-based file-like object from the bytes content
    file_content_io = BytesIO(new_content_bytes)
    # No need for seek(0) here because BytesIO(initial_bytes) sets position to 0 initially
    # ----------------------------------------------------


    # 4. Upload/Update the file on Google Drive
    try:
        # MediaIoBaseUpload now receives a BytesIO object, which provides bytes
        media = MediaIoBaseUpload(file_content_io, mimetype='application/json', resumable=True)
        # chunksize=-1 means upload in a single chunk, suitable for smaller files

        if file_id:
            # Update existing file
            st.info(f"Updating existing file ID: {file_id}")
            # The body= parameter is for metadata updates, media_body is for content
            request = drive_service.files().update(fileId=file_id, media_body=media, fields='id, name')
            response = request.execute()
            st.success(f"Results successfully updated in Google Drive file: {response.get('name')}")
        else:
            # Create new file
            file_metadata = {'name': file_name, 'mimeType': 'application/json'}
            if folder_id:
                file_metadata['parents'] = [folder_id] # Place file in the specified folder

            request = drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, name' # Fields to return in the response
            )
            response = request.execute()
            # file_id = response.get('id') # You might want to store this ID if you don't search every time

    except HttpError as upload_error:
        st.error(f"An API error occurred saving file to Drive: {upload_error}")
        st.warning("Results could not be saved to Google Drive.")
    except Exception as e:
        st.error(f"An unexpected error occurred saving file to Drive: {e}")
        st.warning("Results could not be saved to Google Drive.")


if __name__ == "__main__":
    main()
