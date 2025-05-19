import streamlit as st
import json
import requests
import random
from io import BytesIO
from PIL import Image
from datetime import datetime
import os # Import os for checking file existence

def main():
    st.set_page_config(layout="wide")
    st.title("")

    # Initialize session state for combined results and current question display
    if 'data' not in st.session_state:
        st.session_state['data'] = get_random_data()
        st.session_state['question_index'] = 0
        st.session_state['responses'] = []
        st.session_state['score'] = 0
        st.session_state['combined_results'] = {}  # { (type, category, distance): [correct_count, total_count] }
        # Add state to track the index of the image currently displayed
        st.session_state['displayed_index'] = -1 # -1 means no image loaded yet
        st.session_state['displayed_image_data'] = None # To potentially store loaded image data

    data = st.session_state['data']
    if not data:
        st.error("Could not load data. Please check data.json and data loading logic.")
        return

    idx = st.session_state['question_index']

    if idx < len(data):
        item = data[idx]

        # --- Conditional Image Loading and Display ---
        # Only load and display the image if we have moved to a new question index
        # This prevents reloading/redisplaying on every radio button click for the same question
        if st.session_state['displayed_index'] != idx:
            img_url = item.get('image_path')
            if img_url:
                try:
                    # Use st.spinner to show loading explicitly for the image
                    with st.spinner("Loading image..."):
                        response = requests.get(img_url)
                        response.raise_for_status() # Raise an exception for bad status codes
                        image_data = BytesIO(response.content)
                        img = Image.open(image_data)
                        # Store the loaded image data in session state if you want to re-display without reloading
                        st.session_state['displayed_image_data'] = img
                        st.session_state['displayed_index'] = idx # Mark this index as displayed
                except requests.exceptions.RequestException as e:
                    st.error(f"Error loading image: {e}")
                    st.session_state['displayed_image_data'] = None # No image loaded on error
                    st.session_state['displayed_index'] = idx # Mark this index as processed (with error)
                except Exception as e:
                     st.error(f"Error processing image: {e}")
                     st.session_state['displayed_image_data'] = None
                     st.session_state['displayed_index'] = idx
            else:
                st.warning(f"No image_path provided for question at index {idx}.")
                st.session_state['displayed_image_data'] = None
                st.session_state['displayed_index'] = idx # Mark as processed (no image)

        # Display the image if it was successfully loaded for this index
        if st.session_state['displayed_image_data'] is not None:
             st.image(st.session_state['displayed_image_data'], caption="Image", width=1200)
        elif st.session_state['displayed_index'] == idx: # Only show placeholder/error if we tried for this index
            # Image failed to load or wasn't provided, placeholder if desired
            # st.write("Image not available.") # Optional: show a placeholder text

        # --- Question, Options, and Button (always displayed) ---
        st.subheader(item.get('question', 'No question provided'))
        options = item.get('options', [])
        correct_idx = item.get('correct_answer')

        if not options:
            st.warning(f"No options for question at index {idx}. Skipping.")
            # Auto-skip questions with no options
            st.session_state['question_index'] += 1
            # Reset displayed index so the next image loads
            st.session_state['displayed_index'] = -1
            st.session_state['displayed_image_data'] = None
            st.rerun() # Rerun immediately to load the next question
            return # Stop processing the rest of this question

        # The radio button. Selecting an option will still cause a rerun,
        # but the image loading is now conditional, reducing the delay.
        selected = st.radio("Select an answer:", options, key=f"opt_{idx}", index=None)

        # --- Submit Button Logic ---
        if st.button("Submit", key=f"sub_{idx}"):
            if selected is None:
                 st.warning("Please select an answer before submitting.")
                 # Do NOT rerun here, stay on the current question until submitted correctly
            else:
                # --- Process Submission ---
                try:
                    sel_idx = options.index(selected)
                except ValueError:
                    sel_idx = -1 # Should not happen if options are valid
                    st.error("Internal error: Invalid selection value.") # Handle gracefully
                    # Maybe don't proceed if selection is invalid?
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

                # --- Move to next question and RERUN ---
                st.session_state['question_index'] += 1
                # The displayed_index is intentionally *not* updated here.
                # On the *next* rerun, the script will see question_index != displayed_index
                # and trigger the loading of the new image.
                st.rerun()

    else:
        # Evaluation Finished
        st.subheader("Evaluation Finished!")
        total = len(st.session_state['data']) # Use total number of questions attempted
        correct = st.session_state['score']
        accuracy = (correct / total * 100) if total else 0
        st.write(f"Overall: {correct}/{total} correct ({accuracy:.2f}%)")

        st.subheader("Results by Type, Category & Distance:")
        combined = st.session_state['combined_results']
        if combined:
            # Sort for consistent output
            # Sorting key handles None distance by putting it last for a given type/category
            for (t, c, d), (corr, tot) in sorted(combined.items(), key=lambda x: (x[0][0], x[0][1], x[0][2] is None, x[0][2] if x[0][2] is not None else float('inf'))):
                label = 'None' if d is None else d
                acc = (corr / tot * 100) if tot else 0
                st.write(f"Type {t} | Category {c} | Distance {label}: {corr}/{tot} correct ({acc:.2f}%)")
        else:
            st.write("No combined results recorded.")


        # Save to JSON - ensure this only happens once per session end
        if 'results_saved' not in st.session_state:
            save_combined_results_json(st.session_state['combined_results'])
            st.session_state['results_saved'] = True  # Prevent duplicate saves

        st.success("Thank you!")

        if st.button("Restart Evaluation"):
            # Clear all session state variables
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()


def get_random_data(num_per=1):
    """Loads data and selects a specified number of items per category/distance combination."""
    data = load_data()

    # Define your desired distribution
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
        if t in cat_dist: # Check if type exists in cat_dist
            for cat, dists in cat_dist[t].items():
                 if cat in cat_dist[t]: # Check if category exists for the type
                    for d in dists:
                        # Filter data for the current type, category, and distance
                        filt = [i for i in data if i.get('type') == t and i.get('category') == cat and i.get('distance') == d]
                        if filt:
                            # Select num_per random items from the filtered list without replacement for this group
                            # Handle cases where there are fewer than num_per items
                            num_to_select = min(num_per, len(filt))
                            selected_items = random.sample(filt, num_to_select)
                            rand_list.extend(selected_items)
                        # else:
                            # Optional: Add a warning if no data found for a specific combination
                            # st.warning(f"No data found for Type: {t}, Category: {cat}, Distance: {d}")
                 # else:
                    # Optional: Warning for missing category in data/config
                    # st.warning(f"Category {cat} not found in data for Type: {t}")
        # else:
            # Optional: Warning for missing type in data/config
            # st.warning(f"Type {t} not found in data.")


    random.shuffle(rand_list) # Shuffle the final list
    # Optional: Display total number of questions loaded
    # st.info(f"Loaded {len(rand_list)} evaluation questions.")
    return rand_list


def load_data():
    """Loads data from data.json."""
    path = "./data.json"
    data = []
    if not os.path.exists(path):
        st.error(f"Data file not found at {path}. Please ensure data.json exists.")
        return []

    try:
        with open(path, 'r') as f: # Use 'r' for reading
            data = json.load(f)

        if not isinstance(data, list):
            st.error("Data format error: data.json should contain a JSON list.")
            return []

        # Basic validation for required fields in each item
        required_keys = ['type', 'category', 'distance', 'image_path', 'question', 'options', 'correct_answer']
        for i, item in enumerate(data):
            if not isinstance(item, dict):
                 st.error(f"Data format error: Item {i} is not a dictionary.")
                 return []
            for key in required_keys:
                if key not in item:
                    st.warning(f"Missing key '{key}' in item {i}. This item might be skipped or cause errors.")
            # Validate correct_answer index
            if 'correct_answer' in item and 'options' in item:
                 if not isinstance(item['correct_answer'], int) or not (0 <= item['correct_answer'] < len(item['options'])):
                      st.warning(f"Invalid correct_answer index ({item['correct_answer']}) for item {i}. Must be a valid index for options.")

        return data

    except json.JSONDecodeError:
        st.error(f"JSON decoding error: Could not parse {path}. Please check the JSON syntax.")
        return []
    except Exception as e:
        st.error(f"Loading error: {e}")
        return []

def save_combined_results_json(results):
    """
    Saves combined_results into a JSON file with a nested structure
    and timestamped sessions.
    """
    filename = "results.json"
    timestamp = datetime.now().isoformat()

    # Build nested results: { type: { category: { distance_label: {correct, total} } } }
    nested = {}
    for (t, c, d), (corr, tot) in results.items():
        # Use 'None' string for missing distances
        label = 'None' if d is None else str(d)
        # Initialize nested dicts
        if t not in nested:
            nested[t] = {}
        if c not in nested[t]:
            nested[t][c] = {}
        # Assign correct/total
        nested[t][c][label] = {
            "correct": corr,
            "total": tot
        }

    # Prepare session entry
    session_entry = {
        "timestamp": timestamp,
        "results": nested
    }

    # Load existing sessions
    existing = []
    if os.path.exists(filename):
        try:
            with open(filename, 'r') as f: # Use 'r' for reading
                # Handle empty file case
                content = f.read()
                if content:
                    existing = json.loads(content)
                    if not isinstance(existing, list):
                         st.warning(f"Existing {filename} is not a list. Overwriting.")
                         existing = []
                else:
                     existing = [] # File is empty
        except json.JSONDecodeError:
            st.error(f"Existing {filename} is corrupt (JSON error). Starting with empty results.")
            existing = []
        except Exception as e:
            st.error(f"Error reading {filename}: {e}. Starting with empty results.")
            existing = []

    # Append the new session and write back
    existing.append(session_entry)

    try:
        with open(filename, 'w') as f: # Use 'w' for writing
            json.dump(existing, f, indent=2)
    except Exception as e:
        st.error(f"Error writing to {filename}: {e}")


if __name__ == "__main__":
    main()
