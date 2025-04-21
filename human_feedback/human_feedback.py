import streamlit as st
import json
import pandas as pd
from collections import defaultdict
import copy

st.set_page_config(layout="wide", page_title="Taxonomy Reviewer")
st.title("📝 Taxonomy Review Tool")
SESSION_STATE_KEY = "topic_phrase_data"
MISMATCH_KEY = "mismatched_feedback"


@st.cache_data
def load_initial_data(uploaded_file):
    if uploaded_file is not None:
        try:
            # Read file content first to make cache depend on content
            file_content = uploaded_file.getvalue()
            data = json.loads(file_content)

            if not isinstance(data, dict):
                st.error("Error: JSON file should contain a single dictionary {topic: [phrases]}.")
                return None
            # Basic validation
            validated_data = {}
            for topic, phrases in data.items():
                if isinstance(phrases, list):
                    # Ensure unique phrases per topic initially and convert to string
                    validated_data[topic] = sorted(list(set(str(p) for p in phrases if p is not None)))
                else:
                    st.warning(f"Warning: Value for topic '{topic}' is not a list. Skipping.")
            return validated_data
        except json.JSONDecodeError:
            st.error("Error: Invalid JSON file.")
            return None
        except Exception as e:
            st.error(f"An error occurred loading the file: {e}")
            return None
    return None

def get_dataframe(topic_data):
    """Converts the topic dictionary to a long-format DataFrame."""
    if not topic_data:
        return pd.DataFrame(columns=['Topic', 'Phrase', 'Mismatch'])
    rows = []
    mismatched_set = st.session_state.get(MISMATCH_KEY, set())
    for topic, phrases in topic_data.items():
        for phrase in phrases:
            is_mismatched = (topic, phrase) in mismatched_set
            rows.append({"Topic": topic, "Phrase": phrase, "Mismatch": is_mismatched})
    # Create DataFrame at the end for efficiency
    df = pd.DataFrame(rows) if rows else pd.DataFrame(columns=['Topic', 'Phrase', 'Mismatch'])
    return df


def get_topic_summary(topic_data):
    """Creates a summary DataFrame of topics and phrase counts."""
    if not topic_data:
        return pd.DataFrame(columns=['Topic', 'Phrase Count'])
    summary = [{"Topic": topic, "Phrase Count": len(phrases)} for topic, phrases in topic_data.items()]
    df_summary = pd.DataFrame(summary).sort_values(by='Topic').reset_index(drop=True)
    return df_summary

def add_topic_state(new_topic_name):
    if new_topic_name and new_topic_name not in st.session_state[SESSION_STATE_KEY]:
        st.session_state[SESSION_STATE_KEY][new_topic_name] = []
        st.success(f"Topic '{new_topic_name}' added.")
        # Rerun to update topic lists in UI immediately
        st.rerun()
    elif new_topic_name in st.session_state[SESSION_STATE_KEY]:
        st.warning(f"Topic '{new_topic_name}' already exists.")
    else:
        st.error("Please enter a valid topic name.")

def rename_topic_state(old_topic_name, new_topic_name):
    if old_topic_name and new_topic_name and old_topic_name in st.session_state[SESSION_STATE_KEY]:
        if new_topic_name in st.session_state[SESSION_STATE_KEY] and old_topic_name != new_topic_name:
            st.error(f"Cannot rename: Topic '{new_topic_name}' already exists.")
        elif old_topic_name == new_topic_name:
             st.warning("Old and new topic names are the same.")
        else:
            new_data = {}
            for topic, phrases in st.session_state[SESSION_STATE_KEY].items():
                if topic == old_topic_name:
                    new_data[new_topic_name] = phrases
                else:
                    new_data[topic] = phrases
            st.session_state[SESSION_STATE_KEY] = new_data
            current_mismatches = st.session_state.get(MISMATCH_KEY, set())
            updated_mismatches = set()
            for topic, phrase in current_mismatches:
                if topic == old_topic_name:
                    updated_mismatches.add((new_topic_name, phrase))
                else:
                    updated_mismatches.add((topic, phrase))
            st.session_state[MISMATCH_KEY] = updated_mismatches
            st.success(f"Topic '{old_topic_name}' renamed to '{new_topic_name}'.")
            st.rerun()
    else:
        st.error("Please select a valid topic to rename and provide a new name.")

def delete_topic_state(topic_to_delete):
    if topic_to_delete and topic_to_delete in st.session_state[SESSION_STATE_KEY]:
        deleted_phrases = st.session_state[SESSION_STATE_KEY].pop(topic_to_delete)
        # Remove related mismatches
        current_mismatches = st.session_state.get(MISMATCH_KEY, set())
        st.session_state[MISMATCH_KEY] = {(t, p) for t, p in current_mismatches if t != topic_to_delete}
        st.success(f"Topic '{topic_to_delete}' and its {len(deleted_phrases)} phrases deleted.")
        st.rerun()
    else:
        st.error("Please select a valid topic to delete.")

def add_phrase_state(topic, new_phrase):
    if topic and new_phrase and topic in st.session_state[SESSION_STATE_KEY]:
        # Standardize or clean the phrase if needed before checking/adding
        phrase_to_add = str(new_phrase).strip()
        if not phrase_to_add:
             st.error("Phrase cannot be empty.")
             return
        if phrase_to_add not in st.session_state[SESSION_STATE_KEY][topic]:
            st.session_state[SESSION_STATE_KEY][topic].append(phrase_to_add)
            st.session_state[SESSION_STATE_KEY][topic].sort() # Keep sorted
            st.success(f"Phrase '{phrase_to_add}' added to topic '{topic}'.")
            # No automatic rerun needed, table updates on interaction
        else:
            st.warning(f"Phrase '{phrase_to_add}' already exists in topic '{topic}'.")
    elif not topic:
         st.error("Please select a topic.")
    elif not new_phrase:
         st.error("Please enter a phrase to add.")
    else:
         st.error(f"Selected topic '{topic}' not found.")

def move_phrase_state(phrase_to_move, source_topic, target_topic):
    if not phrase_to_move or not source_topic or not target_topic:
        st.error("Please select a phrase, source topic, and target topic.")
        return
    if source_topic not in st.session_state[SESSION_STATE_KEY]:
         st.error(f"Source topic '{source_topic}' not found.")
         return
    if phrase_to_move not in st.session_state[SESSION_STATE_KEY][source_topic]:
         st.error(f"Phrase '{phrase_to_move}' not found in source topic '{source_topic}'.")
         return

    target_topic_clean = str(target_topic).strip()
    if not target_topic_clean:
        st.error("Target topic name cannot be empty.")
        return

    # If target is a new topic, create it
    if target_topic_clean not in st.session_state[SESSION_STATE_KEY]:
         st.session_state[SESSION_STATE_KEY][target_topic_clean] = []
         st.info(f"New topic '{target_topic_clean}' created.")
         # Need to rerun if a new topic was created to update selection lists
         new_topic_created = True
    else:
         new_topic_created = False


    # Perform the move
    st.session_state[SESSION_STATE_KEY][source_topic].remove(phrase_to_move)
    # Ensure phrase isn't already in target before adding
    if phrase_to_move not in st.session_state[SESSION_STATE_KEY][target_topic_clean]:
        st.session_state[SESSION_STATE_KEY][target_topic_clean].append(phrase_to_move)
        st.session_state[SESSION_STATE_KEY][target_topic_clean].sort()

    # Update mismatches if the phrase was marked
    mismatch_tuple = (source_topic, phrase_to_move)
    current_mismatches = st.session_state.get(MISMATCH_KEY, set())
    if mismatch_tuple in current_mismatches:
        current_mismatches.remove(mismatch_tuple)
        st.session_state[MISMATCH_KEY] = current_mismatches # Update the state

    st.success(f"Phrase '{phrase_to_move}' moved from '{source_topic}' to '{target_topic_clean}'.")
    if new_topic_created:
        st.rerun() # Rerun only if a new topic forces UI option updates

def delete_phrase_state(topic, phrase_to_delete):
    if topic and phrase_to_delete and topic in st.session_state[SESSION_STATE_KEY]:
        if phrase_to_delete in st.session_state[SESSION_STATE_KEY][topic]:
            st.session_state[SESSION_STATE_KEY][topic].remove(phrase_to_delete)
            # Remove from mismatches
            st.session_state.get(MISMATCH_KEY, set()).discard((topic, phrase_to_delete))
            st.success(f"Phrase '{phrase_to_delete}' deleted from topic '{topic}'.")
            # No rerun needed usually
        else:
            st.warning(f"Phrase '{phrase_to_delete}' not found in topic '{topic}'.")
    elif not topic:
        st.error("Please select a topic.")
    elif not phrase_to_delete:
         st.error("Please select a phrase to delete.")
    else:
         st.error(f"Selected topic '{topic}' not found.")


# Download Button for JSON file
def download_data(topic_data):
    """Serialize topic data to JSON formatted string."""
    try:
        save_data = {topic: sorted(list(set(phrases))) for topic, phrases in topic_data.items()}
        json_str = json.dumps(save_data, indent=2, ensure_ascii=False)
        return json_str.encode('utf-8')  # Encode string to bytes for downloading
    except Exception as e:
        st.error(f"Failed to prepare data for download: {e}")
        return None

# --- Initialization ---
if SESSION_STATE_KEY not in st.session_state:
    st.session_state[SESSION_STATE_KEY] = None
if MISMATCH_KEY not in st.session_state:
    st.session_state[MISMATCH_KEY] = set()

# --- File Upload and Loading ---
uploaded_file = st.sidebar.file_uploader("Upload Topic-Phrase JSON", type=["json"], key="file_uploader")

# Load data into session state ONLY if it's not already there or if forced
force_reload = st.sidebar.button("🔄 Reload from Uploaded File", key="reload_btn")
if uploaded_file is not None and (st.session_state[SESSION_STATE_KEY] is None or force_reload):
    initial_data = load_initial_data(uploaded_file)
    if initial_data:
        st.session_state[SESSION_STATE_KEY] = initial_data
        st.session_state[MISMATCH_KEY] = set() # Reset mismatches on reload
        st.sidebar.success("Data loaded successfully.")
        # Don't rerun here, let Streamlit flow continue naturally
elif force_reload:
     st.sidebar.warning("Please upload a file first to reload.")


# --- Main Content - Only if data is loaded ---
if st.session_state[SESSION_STATE_KEY] is not None:
    current_data = st.session_state[SESSION_STATE_KEY]
    all_topics_list = sorted(current_data.keys()) # Get current list of topics

    if st.session_state.get(SESSION_STATE_KEY):
        download_data = download_data(st.session_state[SESSION_STATE_KEY])
        if download_data:
            st.sidebar.download_button(
                label="💾 Download Updated JSON",
                data=download_data,
                file_name="updated_topic_data.json",
                mime="application/json",
                key="download_json_button"
            )
        else:
            st.sidebar.error("Unable to prepare JSON for download.")
    else:
        st.sidebar.warning("No data available to download.")

    # Topic CRUD (in expander)
    with st.sidebar.expander("➕ Topic Operations", expanded=False):
        st.subheader("Add New Topic")
        new_topic_name_input = st.text_input("New Topic Name:", key="new_topic_name")
        st.button("Add Topic", key="add_topic_btn", on_click=add_topic_state, args=(new_topic_name_input,))

        st.subheader("Rename Topic")
        topic_to_rename = st.selectbox("Select Topic to Rename:", all_topics_list, index=None, key="topic_rename_select")
        renamed_topic_name_input = st.text_input("Enter New Name:", key="renamed_topic_name")
        st.button("Rename Selected Topic", key="rename_topic_btn", on_click=rename_topic_state, args=(topic_to_rename, renamed_topic_name_input), disabled=(not topic_to_rename))

        st.subheader("Delete Topic")
        topic_to_delete_select = st.selectbox("Select Topic to Delete:", all_topics_list, index=None, key="topic_delete_select")
        st.warning("⚠️ Deleting a topic also deletes all its phrases.")
        st.button("Delete Selected Topic", key="delete_topic_btn", type="primary", on_click=delete_topic_state, args=(topic_to_delete_select,), disabled=(not topic_to_delete_select))

    # Phrase CRUD (in expander)
    with st.sidebar.expander("✏️ Phrase Operations", expanded=False):
        # Add Phrase
        st.subheader("Add Phrase to Topic")
        topic_for_add_phrase = st.selectbox("Select Topic:", all_topics_list, index=None, key="topic_add_phrase")
        new_phrase_input = st.text_input("New Phrase:", key="new_phrase")
        st.button("Add Phrase", key="add_phrase_btn", on_click=add_phrase_state, args=(topic_for_add_phrase, new_phrase_input), disabled=(not topic_for_add_phrase))

        # Move Phrase
        st.subheader("Move Phrase to Different Topic")
        source_topic_move = st.selectbox("1. Select Source Topic:", all_topics_list, index=None, key="source_topic_move")
        phrases_in_source = sorted(current_data.get(source_topic_move, []))
        phrase_to_move_select = st.selectbox("2. Select Phrase to Move:", phrases_in_source, index=None, key="phrase_to_move", disabled=not source_topic_move)
        allow_new_target = st.checkbox("Allow creating a new target topic?", key="allow_new_target", value=False)
        if allow_new_target:
            target_topic_move = st.text_input("3. Enter Target Topic (New or Existing):", key="target_topic_move_input")
        else:
            # Exclude source topic from target list when not allowing new
            available_targets = [t for t in all_topics_list if t != source_topic_move]
            target_topic_move = st.selectbox("3. Select Target Topic:", available_targets, index=None, key="target_topic_move_select", disabled=not source_topic_move)
        st.button("Move Selected Phrase", key="move_phrase_btn", on_click=move_phrase_state, args=(phrase_to_move_select, source_topic_move, target_topic_move), disabled=(not phrase_to_move_select or not target_topic_move or not source_topic_move))

        # Delete Phrase
        st.subheader("Delete Phrase from Topic")
        topic_for_delete_phrase = st.selectbox("1. Select Topic:", all_topics_list, index=None, key="topic_delete_phrase")
        phrases_in_delete_topic = sorted(current_data.get(topic_for_delete_phrase, []))
        phrase_to_delete_select = st.selectbox("2. Select Phrase to Delete:", phrases_in_delete_topic, index=None, key="phrase_to_delete", disabled=not topic_for_delete_phrase)
        st.button("Delete Selected Phrase", key="delete_phrase_btn", type="primary", on_click=delete_phrase_state, args=(topic_for_delete_phrase, phrase_to_delete_select), disabled=(not phrase_to_delete_select))


    # --- Feedback Section (in expander) ---
    with st.sidebar.expander("🚩 Mismatch Feedback", expanded=False):
         st.info("Mark phrases as mismatched in the main table below using the checkbox.")
         st.subheader("View Mismatched Phrases")
         mismatched_set = st.session_state.get(MISMATCH_KEY, set())
         if mismatched_set:
             # Filter out any mismatches whose topic/phrase might have been deleted
             valid_mismatches = {(t,p) for t,p in mismatched_set if t in current_data and p in current_data[t]}
             if valid_mismatches != mismatched_set: # Update state if invalid entries found
                 st.session_state[MISMATCH_KEY] = valid_mismatches
                 mismatched_set = valid_mismatches

             if mismatched_set:
                 df_mismatched = pd.DataFrame(list(mismatched_set), columns=['Topic', 'Phrase']).sort_values(by=['Topic', 'Phrase'])
                 st.dataframe(df_mismatched, hide_index=True, use_container_width=True)
                 if st.button("Clear All Mismatch Flags", key="clear_mismatch_btn"):
                     st.session_state[MISMATCH_KEY] = set()
                     st.rerun()
             else:
                 st.write("No currently valid phrases marked as mismatched.")

         else:
             st.write("No phrases marked as mismatched.")

    st.header("Explore Topics and Phrases")
    topic_search_term = st.text_input("Search Topics:", placeholder="Type to filter topics below...", key="topic_search")
    topic_search_term_lower = topic_search_term.lower()

    # Filter topics based on search term
    filtered_topic_list = [
        topic for topic in all_topics_list
        if topic_search_term_lower in topic.lower()
    ] if topic_search_term else all_topics_list # Show all if search is empty

    # Multiselect using the filtered list
    selected_topics = st.multiselect(
        f"Select topics to view phrases ({len(filtered_topic_list)}/{len(all_topics_list)} shown):",
        options=filtered_topic_list, # Options are filtered
        default=[], # Start with none selected
        key="topic_selector"
    )

    col1, col2 = st.columns(spec=[1, 2], gap="large")

    with col1:
        st.subheader("Topic Summary")
        df_summary = get_topic_summary(current_data)
        # Optionally filter summary based on search term as well
        df_summary_display = df_summary[df_summary['Topic'].str.contains(topic_search_term, case=False)] if topic_search_term else df_summary
        st.dataframe(
            df_summary_display,
            use_container_width=True,
            hide_index=True,
            key="summary_table"
        )
        st.caption(f"Total Topics: {len(df_summary)}")

    with col2:
        st.subheader("Phrases for Selected Topics")
        if not selected_topics:
            st.info("Select one or more topics from the list above to see their phrases.")
        else:
            selected_data = {topic: current_data[topic] for topic in selected_topics if topic in current_data}
            filtered_df_display = get_dataframe(selected_data)


            edited_df = st.data_editor(
                filtered_df_display,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Mismatch": st.column_config.CheckboxColumn(
                        "Mismatch?", # Column header
                        help="Check this box if the phrase doesn't seem to belong to this topic.",
                        default=False,
                    ),
                    "Topic": st.column_config.TextColumn(disabled=True),
                    "Phrase": st.column_config.TextColumn(disabled=True)
                },
                key="phrase_editor",
                num_rows="fixed"
            )
            
            current_mismatches = st.session_state.get(MISMATCH_KEY, set())
            new_mismatches = set(current_mismatches) # Start with current
            changed = False

            # Use merge to efficiently find differences
            # Need to ensure indices align or use merge on Topic, Phrase
            try:
                original_subset_df = filtered_df_display[['Topic', 'Phrase', 'Mismatch']]
                comparison_df = pd.merge(
                    edited_df[['Topic', 'Phrase', 'Mismatch']],
                    original_subset_df,
                    on=['Topic', 'Phrase'],
                    how='outer',
                    suffixes=('_edited', '_original')
                )

                # Find rows where Mismatch status changed
                changed_rows = comparison_df[comparison_df['Mismatch_edited'] != comparison_df['Mismatch_original']]

                for _, row in changed_rows.iterrows():
                    topic, phrase = row['Topic'], row['Phrase']
                    edited_mismatch = row['Mismatch_edited']
                    original_tuple = (topic, phrase)
                    changed = True
                    if edited_mismatch: # Checked in editor
                        new_mismatches.add(original_tuple)
                    else: # Unchecked in editor
                        new_mismatches.discard(original_tuple)

            except Exception as e:
                st.error(f"Error comparing mismatch changes: {e}") # Catch potential merge errors etc.

            # Update state only if a change was detected
            if changed and new_mismatches != current_mismatches:
                 st.session_state[MISMATCH_KEY] = new_mismatches
                 st.rerun() # Rerun to update sidebar display


            st.caption(f"Displaying {len(filtered_df_display)} phrases for {len(selected_topics)} selected topic(s). Use the checkbox for mismatch feedback.")

else:
    st.info("⬆️ Please upload a JSON file using the sidebar to begin.")

