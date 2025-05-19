import streamlit as st
import json
import requests
import random

from io import BytesIO
from PIL import Image
from datetime import datetime

st.markdown(
    """
    <style>
      .reportview-container .main .block-container {
        max-width: 1200px;
        margin-left: auto;
        margin-right: auto;
        padding-left: 0;
        padding-right: 0;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

def main():
    st.set_page_config(layout="centered")
    st.title("")

    # Initialize session state for combined results
    if 'data' not in st.session_state:
        st.session_state['data'] = get_random_data()
        st.session_state['question_index'] = 0
        st.session_state['responses'] = []
        st.session_state['score'] = 0
        st.session_state['combined_results'] = {}  # { (type, category, distance): [correct_count, total_count] }

    data = st.session_state['data']
    if not data:
        st.error("Could not load data. Please check data.json and data loading logic.")
        return

    idx = st.session_state['question_index']
    if idx < len(data):
        item = data[idx]
        # Display image
        img_url = item.get('image_path')
        response = requests.get(img_url)
        image_data = BytesIO(response.content)
        img = Image.open(image_data)
        st.image(img, caption="Image", width=1200)

        # Display question and options
        st.subheader(item.get('question', 'No question provided'))
        options = item.get('options', [])
        correct_idx = item.get('correct_answer')
        if not options:
            st.warning(f"No options for question at index {idx}. Skipping.")
            st.session_state['question_index'] += 1
            st.rerun()
            return
        selected = st.radio("Select an answer:", options, key=f"opt_{idx}", index=None)
        if st.button("Submit", key=f"sub_{idx}"):
            try:
                sel_idx = options.index(selected)
            except ValueError:
                sel_idx = -1
                st.error("Invalid selection.")
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

            st.session_state['question_index'] += 1
            st.rerun()

    else:
        # # Show final results
        # st.subheader("Evaluation Finished!")
        # total = st.session_state['question_index']
        # correct = st.session_state['score']
        # accuracy = (correct / total * 100) if total else 0
        # st.write(f"Overall: {correct}/{total} correct ({accuracy:.2f}%)")

        # st.subheader("Results by Type, Category & Distance:")
        # combined = st.session_state['combined_results']
        # if combined:
        #     # Sort for consistent output
        #     for (t, c, d), (corr, tot) in sorted(combined.items(), key=lambda x: (x[0][0], x[0][1], x[0][2] is None, x[0][2])):
        #         label = 'None' if d is None else d
        #         acc = (corr / tot * 100) if tot else 0
        #         st.write(f"Type {t} | Category {c} | Distance {label}: {corr}/{tot} correct ({acc:.2f}%)")
        # else:
        #     st.write("No combined results recorded.")

        # Save to JSON
        if 'results_saved' not in st.session_state:
            save_combined_results_json(st.session_state['combined_results'])
            st.session_state['results_saved'] = True  # Prevent duplicate saves

        st.success("Thank you!")

        if st.button("Restart Evaluation"):
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()


def get_random_data(num_per=1):
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
        for cat, dists in cat_dist[t].items():
            for d in dists:
                filt = [i for i in data if i['type']==t and i['category']==cat and i['distance']==d]
                if filt:
                    for _ in range(num_per):
                        sel = random.choice(filt)
                        while sel in rand_list:
                            sel = random.choice(filt)
                        rand_list.append(sel)
    random.shuffle(rand_list)
    return rand_list


def load_data():
    path = "./data.json"
    try:
        with open(path) as f:
            data = json.load(f)
        if not isinstance(data, list):
            st.error("Data format error.")
            return []
        return data
    except Exception as e:
        st.error(f"Loading error: {e}")
        return []


def save_combined_results_json(results):
    # Save combined_results into a JSON list of sessions with nested type→category→distance structure
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
            with open(filename, 'r') as f:
                existing = json.load(f)
        except Exception:
            existing = []
    # Append and write back
    existing.append(session_entry)
    with open(filename, 'w') as f:
        json.dump(existing, f, indent=2)

if __name__ == "__main__":
    main()
