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

# --- Data Loading and Saving Functions (Kept as is) ---
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
    # st.info(f"Loaded {len(rand_list[:1])} evaluation questions.") # Moved message to evaluation state
    return rand_list[:1]


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
    # Using a fixed file name to append results, rather than a new file each time
    file_name = "evaluation_results.json"
    # Replace with your actual Google Drive Folder ID if you shared a specific folder
    # You can get the folder ID from the URL when viewing the folder in Google Drive
    # Example URL: https://drive.google.com/drive/folders/YOUR_FOLDER_ID_HERE
    # If folder_id is None, the file will be saved in the service account's root Drive folder
    # It's highly recommended to use a specific folder.
    folder_id = "1B6Q1DwCCK4JpIZKgZemkZidq6zTrmca_" # <<< CHANGE THIS to your actual folder ID
    if folder_id is None or folder_id == "YOUR_FOLDER_ID_HERE":
        st.warning(f"No specific folder_id provided or placeholder used. Results will be saved to the service account's root Drive folder as '{file_name}'.")
        st.warning("Consider using a dedicated folder for better organization and control by replacing 'YOUR_FOLDER_ID_HERE'.")
        # For safety, if no folder_id is set, let's search only in root
        folder_q_part = " and 'root' in parents"
    else:
         folder_q_part = f" and '{folder_id}' in parents"


    timestamp = datetime.now().isoformat()

    # Structure the current session results
    nested = {}
    for (t, c, d), (corr, tot) in results.items():
        label = 'None' if d is None else str(d)
        if t not in nested: nested[t] = {}
        if c not in nested[t]: nested[c] = {} # Corrected: should be nested[t][c]
        if label not in nested[t][c]: nested[t][c][label] = {} # Corrected: should be nested[t][c][label]
        nested[t][c][label] = {"correct": corr, "total": tot}

    session_entry = {"timestamp": timestamp, "results": nested}

    existing_data = []
    file_id = None

    # 1. Search for the existing file in Google Drive
    try:
        # Search for the file by name and mimeType, restricted by folder if specified
        q = f"name='{file_name}' and mimeType='application/json' and trashed=false{folder_q_part}"

        results = drive_service.files().list(
            q=q,
            spaces='drive',
            fields='files(id, name, parents)', # Request parents field to confirm location
        ).execute()

        items = results.get('files', [])

        # Double-check parent ID if folder_id was specified, to be absolutely sure
        if folder_id and folder_id != "YOUR_FOLDER_ID_HERE":
             items = [item for item in items if folder_id in item.get('parents', [])]
             if len(items) > 1:
                 st.warning(f"Multiple files named '{file_name}' found in folder ID '{folder_id}'. Using the first one found.")

        if items:
            # Assuming the (filtered) first result is the correct file
            file_id = items[0]['id']
            st.info(f"Found existing results file on Drive: {file_name} (ID: {file_id})")

            # 2. Download existing content
            try:
                request = drive_service.files().get_media(fileId=file_id)
                downloaded_bytes = BytesIO()
                downloader = MediaIoBaseDownload(downloaded_bytes, request)
                done = False
                while done is False:
                    status, done = downloader.next_chunk()
                downloaded_bytes.seek(0)

                content_bytes = downloaded_bytes.read()
                if content_bytes.strip():
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
    new_content_bytes = new_content.encode('utf-8')
    file_content_io = BytesIO(new_content_bytes)
    # ----------------------------------------------------

    # 4. Upload/Update the file on Google Drive
    try:
        media = MediaIoBaseUpload(file_content_io, mimetype='application/json', resumable=True)

        if file_id:
            # Update existing file
            st.info(f"Updating existing file ID: {file_id}")
            request = drive_service.files().update(fileId=file_id, media_body=media, fields='id, name')
            response = request.execute()
            st.success(f"Results successfully updated in Google Drive file: {response.get('name')}")
        else:
            # Create new file
            st.info(f"Creating new file: {file_name}")
            file_metadata = {'name': file_name, 'mimeType': 'application/json'}
            if folder_id and folder_id != "YOUR_FOLDER_ID_HERE":
                 file_metadata['parents'] = [folder_id] # Place file in the specified folder

            request = drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, name'
            )
            response = request.execute()
            st.success(f"New results file created in Google Drive: {response.get('name')}")

    except HttpError as upload_error:
        st.error(f"An API error occurred saving file to Drive: {upload_error}")
        st.warning("Results could not be saved to Google Drive.")
    except Exception as e:
        st.error(f"An unexpected error occurred saving file to Drive: {e}")
        st.warning("Results could not be saved to Google Drive.")


def main():
    st.set_page_config(layout="wide")

    # --- State Management ---
    if 'page_state' not in st.session_state:
        st.session_state['page_state'] = 'instructions' # Start with instructions

    # --- Display Content Based on State ---
    if st.session_state['page_state'] == 'instructions':
        # --- Instructions Page ---
        st.header("Instructions")
        st.write("""
        Welcome to the evaluation!

        Please read the following instructions carefully before you begin:

        * This evaluation consists of multiple questions, each presenting an image.
        * For each image, you will be asked a question related to its content.
        * Select the option that you believe is the correct answer.
        * Click the "Submit" button to record your answer and move to the next question.
        * You must select an answer before you can submit.
        * Your progress is saved as you go.
        * Once you complete all questions, your results will be shown (or processed) and you will see a completion message.

        Click the button below to start the evaluation when you are ready.
        """)

        if st.button("Start Evaluation"):
            # Initialize all evaluation-related session state variables here
            st.session_state['data'] = get_random_data()
            if not st.session_state['data']:
                 st.error("Could not load data. Evaluation cannot start.")
                 # Optionally keep the state as 'instructions' or set to 'error'
                 st.session_state['page_state'] = 'instructions' # Stay on instructions page if data load fails
                 return # Stop execution for this rerun
            else:
                st.session_state['question_index'] = 0
                st.session_state['responses'] = []
                st.session_state['score'] = 0
                st.session_state['combined_results'] = {}
                st.session_state['displayed_index'] = -1 # Reset image display state
                st.session_state['displayed_image_data'] = None # Reset image data
                st.session_state['results_saved'] = False # Reset save state
                st.session_state['page_state'] = 'evaluation' # Transition to evaluation state
                st.rerun() # Rerun the app to show the first question


    elif st.session_state['page_state'] == 'evaluation':
        # --- Evaluation Page (Your existing logic) ---
        data = st.session_state.get('data') # Use .get for safety, though initialized before
        if not data:
             st.error("Evaluation data not found. Please restart.")
             st.session_state['page_state'] = 'instructions' # Go back to instructions
             st.rerun()
             return # Stop execution

        idx = st.session_state['question_index']

        if idx < len(data):
            item = data[idx]

            # Wrap the question display area in a container
            question_container = st.container()

            with question_container:
                # --- Conditional Image Loading Logic ---
                # Only attempt to load image if it's a new question or not loaded yet
                if st.session_state['displayed_index'] != idx:
                    img_url = item.get('image_path')
                    st.session_state['displayed_image_data'] = None # Clear previous image data
                    if img_url:
                        try:
                            with st.spinner(f"Loading image for question {idx+1}..."):
                                response = requests.get(img_url, timeout=10)
                                response.raise_for_status()
                                image_data = BytesIO(response.content)
                                st.session_state['displayed_image_data'] = Image.open(image_data)
                            st.session_state['displayed_index'] = idx # Mark image as loaded for this index
                        except requests.exceptions.Timeout:
                            st.error(f"Timeout loading image for question {idx+1}.")
                            st.session_state['displayed_index'] = idx # Mark as attempted for this index
                            st.session_state['displayed_image_data'] = None # Ensure no image is displayed
                        except requests.exceptions.RequestException as e:
                            st.error(f"Error loading image for question {idx+1}: {e}")
                            st.session_state['displayed_index'] = idx # Mark as attempted for this index
                            st.session_state['displayed_image_data'] = None # Ensure no image is displayed
                        except Exception as e:
                            st.error(f"Error processing image for question {idx+1}: {e}")
                            st.session_state['displayed_index'] = idx # Mark as attempted for this index
                            st.session_state['displayed_image_data'] = None # Ensure no image is displayed
                    else:
                        st.warning(f"No image_path provided for question {idx+1}.")
                        st.session_state['displayed_index'] = idx # Mark as attempted for this index
                        st.session_state['displayed_image_data'] = None # Ensure no image is displayed

                # --- Image Display Logic ---
                if st.session_state['displayed_image_data'] is not None and st.session_state['displayed_index'] == idx:
                     st.image(st.session_state['displayed_image_data'], caption=f"Question {idx+1}/{len(data)}", width=1200)
                elif st.session_state['displayed_index'] == idx:
                     st.warning(f"Image not available for question {idx+1}.")


                # --- Question, Options, and Button (always displayed FOR THIS QUESTION) ---
                st.subheader(item.get('question', f'Question {idx+1}: No question text provided'))
                options = item.get('options', [])
                correct_idx = item.get('correct_answer')

                if not options:
                    st.warning(f"No options for question {idx+1}. Skipping.")
                    # Immediately move to the next question if options are missing
                    st.session_state['question_index'] += 1
                    st.session_state['displayed_index'] = -1 # Reset for next image load
                    st.session_state['displayed_image_data'] = None
                    st.rerun()
                    return # Stop processing for this question

                # Add a unique key based on the question index
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
                            sel_idx = -1 # Indicate an invalid selection
                            st.error("Internal error: Invalid selection value.")
                            return # Prevent processing if selection is invalid

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
                             st.session_state['combined_results'][key] = [0, 0] # [correct, total]
                        st.session_state['combined_results'][key][1] += 1 # Increment total count for this key
                        if correct:
                            st.session_state['combined_results'][key][0] += 1 # Increment correct count if correct

                        # Optional: Provide immediate feedback (can be removed if you don't want it)
                        # if correct:
                        #     st.success("Correct!")
                        # else:
                        #     st.error(f"Incorrect. The correct answer was: {options[correct_idx]}")

                        # Wait a moment before moving to the next question (optional)
                        # time.sleep(1)

                        # --- Move to next question and RERUN ---
                        st.session_state['question_index'] += 1
                        st.rerun()

        else:
            # Evaluation Finished - Transition to 'finished' state
            st.session_state['page_state'] = 'finished'
            st.rerun() # Rerun to display the finished page


    elif st.session_state['page_state'] == 'finished':
        # --- Evaluation Finished Page ---
        st.header("Evaluation Finished!")
        total = len(st.session_state.get('data', [])) # Use .get for safety
        correct = st.session_state.get('score', 0)
        accuracy = (correct / total * 100) if total else 0

        st.subheader("Results Summary")
        st.write(f"You answered {correct} out of {total} questions correctly.")
        st.write(f"Overall Accuracy: **{accuracy:.2f}%**")

        # Display combined results (optional - uncomment if you want to show this on the page)
        # combined = st.session_state.get('combined_results', {})
        # if combined:
        #     st.subheader("Detailed Results by Category")
        #     # Sort for better readability
        #     sorted_combined = sorted(combined.items(), key=lambda x: (x[0][0], x[0][1], x[0][2] is None, x[0][2] if x[0][2] is not None else float('inf')))
        #     for (t, c, d), (corr, tot) in sorted_combined:
        #         label = 'None' if d is None else d
        #         acc = (corr / tot * 100) if tot else 0
        #         st.write(f"Type: {t} | Category: {c} | Distance: {label}: {corr}/{tot} correct ({acc:.2f}%)")
        # else:
        #     st.write("No detailed category results recorded.")


        # Save results to Google Drive only once
        if not st.session_state.get('results_saved', False):
            save_combined_results_json(st.session_state.get('combined_results', {}))
            st.session_state['results_saved'] = True # Mark as saved

        st.success("Thank you for participating in the evaluation!")

        # Optional: Add a button to restart the evaluation
        if st.button("Start Another Evaluation"):
            # Clear all session state variables to start fresh
            for key in st.session_state.keys():
                 del st.session_state[key]
            st.rerun()


if __name__ == "__main__":
    main()
