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

    # Initialize session state for evaluation start
    if 'evaluation_started' not in st.session_state:
        st.session_state['evaluation_started'] = False

    # --- Instructions Page ---
    if not st.session_state['evaluation_started']:
        st.subheader("Instructions:")
        st.write("""
        1.  You will be asked to answer 62 very simple visual questions. This should take no more than 10 to 15 minutes.
        2.  If none of the answer choices seem correct, please still select one (even at random) so you can continue to the next question.
        3.  Use a large screen (such as a monitor or laptop) for this task, as some visual details may not be visible on a mobile device.

        Click the button below to start the evaluation when you are ready.
        """)

        if st.button("Start"):
            # Initialize evaluation state when the button is clicked
            st.session_state['data'] = get_random_data()
            st.session_state['question_index'] = 0
            st.session_state['responses'] = []
            st.session_state['score'] = 0
            st.session_state['combined_results'] = {}
            st.session_state['displayed_index'] = -1
            st.session_state['displayed_image_data'] = None
            st.session_state['evaluation_started'] = True
            st.rerun()

    # --- Evaluation Logic (only runs if evaluation_started is True) ---
    else:
        # Initialize evaluation state if not already initialized (this might happen on first load after start button clicked)
        # This check might be redundant if the button logic always initializes, but good practice
        if 'data' not in st.session_state:
             st.error("Evaluation data not initialized. Please restart.")
             st.session_state['evaluation_started'] = False # Reset state to show instructions again
             st.rerun()
             return


        data = st.session_state['data']
        if not data:
            st.error("Could not load data. Please check data.json and data loading logic.")
            # Optionally reset state if data load fails after starting
            st.session_state['evaluation_started'] = False
            st.session_state['data'] = None # Clear potentially bad data
            st.rerun()
            return

        idx = st.session_state['question_index']

        if idx < len(data):
            item = data[idx]

            # Wrap the question display area in a container
            # This can help stabilize the layout of the grouped elements
            question_container = st.container()

            with question_container:
                # --- Conditional Image Loading Logic ---
                # Only attempt to load image if we are displaying a new question
                if st.session_state.get('displayed_index', -1) != idx:
                    img_url = item.get('image_path')
                    st.session_state['displayed_image_data'] = None # Reset image data for the new question
                    if img_url:
                        try:
                            with st.spinner(f"Loading image for question {idx+1}/{len(data)}..."):
                                response = requests.get(img_url, timeout=10)
                                response.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)
                                image_data = BytesIO(response.content)
                                st.session_state['displayed_image_data'] = Image.open(image_data)
                            st.session_state['displayed_index'] = idx # Mark this index as displayed
                        except requests.exceptions.Timeout:
                            st.error(f"Timeout loading image for question {idx+1}. Please check the image URL.")
                            st.session_state['displayed_index'] = idx # Mark as attempted to load
                        except requests.exceptions.RequestException as e:
                            st.error(f"Error loading image for question {idx+1}: {e}")
                            st.session_state['displayed_index'] = idx # Mark as attempted to load
                        except Exception as e:
                             st.error(f"Error processing image for question {idx+1}: {e}")
                             st.session_state['displayed_index'] = idx # Mark as attempted to load
                    else:
                        st.warning(f"No image_path provided for question {idx+1}.")
                        st.session_state['displayed_index'] = idx # Mark as attempted (no image path)

                # --- Image Display Logic ---
                # Display the image if it was successfully loaded for the current question index
                if st.session_state.get('displayed_image_data') is not None and st.session_state.get('displayed_index') == idx:
                     st.image(st.session_state['displayed_image_data'], caption=f"Question {idx+1}", width=1200)
                elif st.session_state.get('displayed_index') == idx:
                     # Display a message if loading was attempted but failed or no path was provided
                     # The specific error/warning would have been shown during loading
                     pass # Error/Warning is shown above during loading attempt
                # Note: If displayed_index != idx, it means we haven't attempted to load/display the image for this question yet,
                # which should be handled by the conditional logic above on rerun.

                # --- Question, Options, and Button (always displayed FOR THIS QUESTION) ---
                st.subheader(item.get('question', f'Question {idx+1}: No question text provided'))

                options = item.get('options', [])
                correct_idx = item.get('correct_answer')

                if not options:
                    st.warning(f"No options for question {idx+1}. Skipping.")
                    # Move to the next question automatically if no options are available
                    st.session_state['question_index'] += 1
                    st.session_state['displayed_index'] = -1 # Reset displayed index for next question
                    st.session_state['displayed_image_data'] = None # Reset image data for next question
                    st.rerun() # Rerun to load the next question
                    return # Exit the current execution

                # Use a unique key for the radio button based on the question index
                selected = st.radio("Select an answer:", options, key=f"opt_{idx}", index=None)

                # --- Submit Button Logic ---
                # Use a unique key for the button based on the question index
                if st.button("Submit", key=f"sub_{idx}"):
                    if selected is None:
                        st.warning("Please select an answer before submitting.")
                    else:
                        # --- Process Submission ---
                        try:
                            # Find the index of the selected answer in the options list
                            sel_idx = options.index(selected)
                        except ValueError:
                            # This should ideally not happen if 'selected' comes directly from the options list
                            sel_idx = -1
                            st.error("Internal error: Invalid selection value.")
                            return # Stop processing for this submission

                        st.session_state['responses'].append(sel_idx)

                        # Check if the selected index matches the correct answer index
                        correct = (sel_idx == correct_idx)
                        if correct:
                            st.session_state['score'] += 1

                        # Track combined results based on item properties
                        t = item.get('type')
                        c = item.get('category')
                        d = item.get('distance') # Can be None

                        # Use a tuple as the key for the combined results dictionary
                        key = (t, c, d)

                        # Initialize the entry for this key if it doesn't exist [correct, total]
                        if key not in st.session_state['combined_results']:
                            st.session_state['combined_results'][key] = [0, 0]

                        # Increment the total count for this combination
                        st.session_state['combined_results'][key][1] += 1
                        # Increment the correct count if the answer was correct
                        if correct:
                            st.session_state['combined_results'][key][0] += 1

                        # Optional: Display immediate feedback (can add st.success/st.error based on 'correct')
                        # st.write(f"Your answer is: {'Correct' if correct else 'Incorrect'}")
                        # time.sleep(1) # Pause briefly

                        # --- Move to next question and RERUN ---
                        st.session_state['question_index'] += 1
                        # Reset displayed index and image data so the next question's image is loaded
                        st.session_state['displayed_index'] = -1
                        st.session_state['displayed_image_data'] = None
                        st.rerun() # Rerun the script to display the next question or the finish screen

        else:
            # --- Evaluation Finished ---
            st.subheader("Evaluation Finished!")
            total = len(st.session_state.get('data', [])) # Use .get for safety
            correct = st.session_state.get('score', 0) # Use .get for safety
            accuracy = (correct / total * 100) if total else 0

            combined = st.session_state.get('combined_results', {}) # Use .get for safety

            # Save results to Google Drive only once after completion
            if 'results_saved' not in st.session_state or not st.session_state['results_saved']:
                save_combined_results_json(st.session_state['combined_results'])
                st.session_state['results_saved'] = True # Mark as saved

            st.success("Thank you!")


def get_random_data(num_per=1):
    """Loads data and selects a specified number of items per category/distance combination."""
    data = load_data()
    types = ["synth", "real"]
    # This dictionary defines the structure of data expected and controls sampling
    cat_dist = {
        "synth": {1: [50,40,30,20,10,5,None], 2:[50,40,30,20,10,5],
                  3:[50,40,30,20,10,5,None], 4:[50,40,30,20,10,5],
                  5:[50,40,30,20,10], 6:[50,40,30,20,10]},
        "real": {1:[50,40,30,20,10,5,None], 2:[50,40,30,20,10,5],
                 3:[50,40,30,20,10,5,None], 4:[50,40,30,20,10,5]}
    }

    rand_list = []
    if not data:
        return [] # Return empty list if no data was loaded initially

    for t in types:
        if t in cat_dist:
            for cat, dists in cat_dist[t].items():
                if cat in cat_dist[t]: # Redundant check, but doesn't hurt
                    for d in dists:
                        # Filter the loaded data to find items matching type, category, and distance
                        filt = [i for i in data if i.get('type') == t and i.get('category') == cat and i.get('distance') == d]

                        if filt: # Only attempt to sample if there are items matching the filter
                            num_to_select = min(num_per, len(filt)) # Ensure we don't ask for more items than available

                            if num_to_select > 0:
                                try:
                                    # Randomly sample the required number of items from the filtered list
                                    selected_items = random.sample(filt, num_to_select)
                                    rand_list.extend(selected_items) # Add the selected items to the list
                                except ValueError as e:
                                     # This exception can occur if num_to_select > len(filt), though min() should prevent it.
                                     # Keep it for robust error handling.
                                     st.warning(f"Could not sample {num_to_select} items for Type: {t}, Category: {cat}, Distance: {d}. Available: {len(filt)}. Error: {e}")
                            # else:
                                # st.info(f"No items to select for Type: {t}, Category: {cat}, Distance: {d} as num_to_select is 0.")
                        # else:
                            # st.info(f"No data items found for Type: {t}, Category: {cat}, Distance: {d}.")


    if not rand_list:
         st.error("No data found matching the specified types, categories, and distances after filtering and sampling.")
         # Consider if this should halt the app or just display a warning. For now, it returns empty list.

    random.shuffle(rand_list) # Shuffle the final list of selected items
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

        # Optional: Add data validation for each item
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

            # Validate correct_answer index if options and correct_answer are present
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
    file_name = f"{timestamp_ms}.json" # Use a unique timestamp for each file

    # Replace with your actual Google Drive Folder ID if you shared a specific folder
    # You can get the folder ID from the URL when viewing the folder in Google Drive
    # Example URL: https://drive.google.com/drive/folders/YOUR_FOLDER_ID_HERE
    # If folder_id is None, the file will be saved in the service account's root Drive folder
    # It's highly recommended to use a specific folder.
    folder_id = "1B6Q1DwCCK4JpIZKgZemkZidq6zTrmca_" # Replace with your actual folder ID
    if folder_id is None or folder_id == "YOUR_FOLDER_ID_HERE":
         st.warning(f"No specific folder_id provided or placeholder used. Results will be saved to the service account's root Drive folder as '{file_name}'.")
         st.warning("Consider using a dedicated folder for better organization and control by setting 'folder_id'.")
         folder_id = None # Ensure folder_id is None if not set or is placeholder

    timestamp = datetime.now().isoformat()

    # Structure the current session results in a nested dictionary
    nested = {}
    for (t, c, d), (corr, tot) in results.items():
        label = 'None' if d is None else str(d) # Convert distance to string for JSON key
        if t not in nested:
            nested[t] = {}
        if c not in nested[t]:
            nested[t][c] = {}
        nested[t][c][label] = {"correct": corr, "total": tot}

    session_entry = {"timestamp": timestamp, "results": nested}

    # For this implementation, we are creating a new file for each session
    # If you intended to append to a single file, the logic below would need
    # to download the existing file, append, and then upload. The current
    # implementation creates a new file named with a timestamp, which is safer
    # for concurrent evaluations but results in many files.
    # The existing code was already trying to search for a file with a timestamp,
    # implying it also intended to create unique files or possibly find one
    # from the *current* session's start time if that was the file naming logic.
    # Let's stick to creating a new file per session as the original file naming
    # suggests. The previous search/download logic seems more suited for appending
    # to a single file, which isn't happening with the timestamped filename.
    # So, we will simplify this part to just create a new file.

    new_content = json.dumps([session_entry], indent=2) # Wrap in a list to match original file structure assumption

    # --- Prepare content for Upload (Encode to Bytes) ---
    new_content_bytes = new_content.encode('utf-8')
    file_content_io = BytesIO(new_content_bytes)
    # ----------------------------------------------------

    # 4. Upload/Update the file on Google Drive
    try:
        media = MediaIoBaseUpload(file_content_io, mimetype='application/json', resumable=True)

        file_metadata = {'name': file_name, 'mimeType': 'application/json'}
        if folder_id:
             file_metadata['parents'] = [folder_id] # Place file in the specified folder

        # Create new file
        request = drive_service.files().create(
             body=file_metadata,
             media_body=media,
             fields='id, name' # Fields to return in the response
        )
        response = request.execute()

    except HttpError as upload_error:
        st.error(f"An API error occurred saving file to Drive: {upload_error}")
        st.warning("Results could not be saved to Google Drive.")
    except Exception as e:
        st.error(f"An unexpected error occurred saving file to Drive: {e}")
        st.warning("Results could not be saved to Google Drive.")


if __name__ == "__main__":
    main()
