import streamlit as st
import json
import requests
import random
from io import BytesIO
from PIL import Image
from datetime import datetime
import os
import time # Import time for sleep

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
                        st.success("Correct!")
                        st.session_state['score'] += 1
                    else:
                        st.error(f"Incorrect. Correct answer was: {options[correct_idx]}")

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
        st.write(f"Overall: {correct}/{total} correct ({accuracy:.2f}%)")

        st.subheader("Results by Type, Category & Distance:")
        combined = st.session_state['combined_results']
        if combined:
            for (t, c, d), (corr, tot) in sorted(combined.items(), key=lambda x: (x[0][0], x[0][1], x[0][2] is None, x[0][2] if x[0][2] is not None else float('inf'))):
                label = 'None' if d is None else d
                acc = (corr / tot * 100) if tot else 0
                st.write(f"Type {t} | Category {c} | Distance {label}: {corr}/{tot} correct ({acc:.2f}%)")
        else:
            st.write("No combined results recorded.")

        if 'results_saved' not in st.session_state:
            save_combined_results_json(st.session_state['combined_results'])
            st.session_state['results_saved'] = True

        st.success("Thank you!")

        if st.button("Restart Evaluation"):
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()


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
    Saves combined_results into a JSON file with a nested structure
    and timestamped sessions.
    """
    filename = "results.json"
    timestamp = datetime.now().isoformat()

    nested = {}
    for (t, c, d), (corr, tot) in results.items():
        label = 'None' if d is None else str(d)
        if t not in nested: nested[t] = {}
        if c not in nested[t]: nested[t][c] = {}
        nested[t][c][label] = {"correct": corr, "total": tot}

    session_entry = {"timestamp": timestamp, "results": nested}

    existing = []
    if os.path.exists(filename):
        try:
            with open(filename, 'r') as f:
                content = f.read()
                if content:
                    existing = json.loads(content)
                    if not isinstance(existing, list):
                         st.warning(f"Existing {filename} is not a list. Starting new results file.")
                         existing = []
                else:
                     existing = []
        except json.JSONDecodeError:
            st.error(f"Existing {filename} is corrupt (JSON error). Starting new results file.")
            existing = []
        except Exception as e:
            st.error(f"Error reading {filename}: {e}. Starting new results file.")
            existing = []

    existing.append(session_entry)

    try:
        with open(filename, 'w') as f:
            json.dump(existing, f, indent=2)
    except Exception as e:
        st.error(f"Error writing to {filename}: {e}")


if __name__ == "__main__":
    main()
