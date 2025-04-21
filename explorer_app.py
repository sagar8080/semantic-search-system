from pathlib import Path
import streamlit as st
import json
import pandas as pd
from collections import defaultdict
import copy
import networkx as nx
from pyvis.network import Network
import streamlit.components.v1 as components
import os
import re
from knowledge_graph.utils import *

# --- Constants ---
TOPIC_MAPPING_STATE_KEY = "topic_phrase_data"
TOPICS_JSON_STATE_KEY = "topics_json_data"
MISMATCH_KEY = "mismatched_feedback"
GRAPH_HTML_KEY = "graph_html_content"
TOPIC_DOC_MAP_KEY = "topic_doc_map"
TOPIC_MAPPING_FILE_PATH = 'topics/topic_mapping.json'
TOPICS_FILE_PATH = 'topics/topics.json'

# --- Utility Functions ---
@st.cache_data(show_spinner="Loading JSON from path...")
def load_json_from_path(file_path, expected_format="dict"):
    """Loads data from a JSON file path with validation."""
    if not os.path.exists(file_path):
        st.error(f"Error: File not found at path '{file_path}'.")
        return None
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            file_content_str = f.read()
            content = re.sub(r',\s*(\]|\})', r'\1', file_content_str)
            data = json.loads(content)

        if expected_format == "dict" and not isinstance(data, dict):
            st.error(f"Error: File '{file_path}' should contain a single dictionary.")
            return None
        return data
    except json.JSONDecodeError as e:
        st.error(f"Error: Invalid JSON in file '{file_path}' near line {e.lineno}, col {e.colno}: {e.msg}")
        return None
    except Exception as e:
        st.error(f"An error occurred loading file '{file_path}': {e}")
        return None

def normalize_key(key_string):
    """Normalizes keys by stripping whitespace and lowercasing."""
    if not isinstance(key_string, str):
        key_string = str(key_string)
    return key_string.strip().lower()

@st.cache_data(show_spinner="Creating topic-document mapping...")
def create_direct_topic_to_doc_details_mapping_cached(_topic_mapping_data, _topics_data):
    """Creates a mapping from broad topics directly to a unique set of document details (cached)."""
    topic_to_docs_map = defaultdict(set)

    if not _topic_mapping_data or not _topics_data:
        return {}

    topic_mapping_data = copy.deepcopy(_topic_mapping_data)
    topics_data = copy.deepcopy(_topics_data)

    normalized_topic_mapping = {normalize_key(k): v for k, v in topic_mapping_data.items()}
    normalized_topics = {normalize_key(k): v for k, v in topics_data.items()}

    for broad_topic_norm, phrases in normalized_topic_mapping.items():
        if not isinstance(phrases, list): continue
        for phrase_raw in phrases:
            phrase_norm = normalize_key(phrase_raw)
            if phrase_norm in normalized_topics:
                document_list = normalized_topics[phrase_norm]
                if not isinstance(document_list, list): continue
                for doc_entry in document_list:
                    if isinstance(doc_entry, dict) and len(doc_entry) == 1:
                        doc_id, doc_details = list(doc_entry.items())[0]
                        if isinstance(doc_details, dict) and 'url' in doc_details and 'title' in doc_details:
                            url = doc_details.get('url', 'N/A')
                            title = doc_details.get('title', 'No Title')
                            topic_to_docs_map[broad_topic_norm].add((str(doc_id), url, title))

    final_map = {}
    for topic, details_set in topic_to_docs_map.items():
         final_map[topic] = [{"doc_id": d[0], "url": d[1], "title": d[2]} for d in sorted(list(details_set))]

    return final_map

def get_dataframe(topic_data):
    """Converts the topic dictionary to a long-format DataFrame."""
    if not topic_data:
        return pd.DataFrame(columns=['Topic', 'Phrase', 'Mismatch'])
    rows = []
    mismatched_set = st.session_state.get(MISMATCH_KEY, set())
    for topic, phrases in topic_data.items():
        if isinstance(phrases, list):
            for phrase in phrases:
                is_mismatched = (topic, phrase) in mismatched_set
                rows.append({"Topic": topic, "Phrase": phrase, "Mismatch": is_mismatched})
        else:
            pass

    df = pd.DataFrame(rows) if rows else pd.DataFrame(columns=['Topic', 'Phrase', 'Mismatch'])
    return df.sort_values(by=['Topic', 'Phrase']).reset_index(drop=True)

def get_topic_summary(topic_data):
    """Creates a summary DataFrame of topics and phrase counts."""
    if not topic_data:
        return pd.DataFrame(columns=['Topic', 'Phrase Count'])
    summary = [{"Topic": topic, "Phrase Count": len(phrases) if isinstance(phrases, list) else 0}
               for topic, phrases in topic_data.items()]
    df_summary = pd.DataFrame(summary).sort_values(by='Topic').reset_index(drop=True)
    return df_summary

def add_topic_state(new_topic_name):
    if TOPIC_MAPPING_STATE_KEY not in st.session_state or st.session_state[TOPIC_MAPPING_STATE_KEY] is None:
        st.error("Data not loaded yet.")
        return
    current_data = st.session_state[TOPIC_MAPPING_STATE_KEY]
    if new_topic_name and new_topic_name not in current_data:
        current_data[new_topic_name] = []
        st.session_state[TOPIC_MAPPING_STATE_KEY] = current_data # Update state
        st.success(f"Topic '{new_topic_name}' added.")
        st.rerun()
    elif new_topic_name in current_data:
        st.warning(f"Topic '{new_topic_name}' already exists.")
    else:
        st.error("Please enter a valid topic name.")

def rename_topic_state(old_topic_name, new_topic_name):
    if TOPIC_MAPPING_STATE_KEY not in st.session_state or st.session_state[TOPIC_MAPPING_STATE_KEY] is None: return
    current_data = st.session_state[TOPIC_MAPPING_STATE_KEY]
    if old_topic_name and new_topic_name and old_topic_name in current_data:
        if new_topic_name in current_data and old_topic_name != new_topic_name:
            st.error(f"Cannot rename: Topic '{new_topic_name}' already exists.")
        elif old_topic_name == new_topic_name: pass # No change
        else:
            new_dict = {new_topic_name if topic == old_topic_name else topic: phrases
                        for topic, phrases in current_data.items()}
            st.session_state[TOPIC_MAPPING_STATE_KEY] = new_dict
            # Update mismatches
            mismatches = st.session_state.get(MISMATCH_KEY, set())
            st.session_state[MISMATCH_KEY] = {(new_topic_name if t == old_topic_name else t, p) for t, p in mismatches}
            st.success(f"Topic '{old_topic_name}' renamed to '{new_topic_name}'.")
            st.rerun()
    elif not old_topic_name: st.error("Select topic to rename.")
    elif not new_topic_name: st.error("Enter new topic name.")

def delete_topic_state(topic_to_delete):
    if TOPIC_MAPPING_STATE_KEY not in st.session_state or st.session_state[TOPIC_MAPPING_STATE_KEY] is None: return
    current_data = st.session_state[TOPIC_MAPPING_STATE_KEY]
    if topic_to_delete and topic_to_delete in current_data:
        count = len(current_data.pop(topic_to_delete))
        st.session_state[TOPIC_MAPPING_STATE_KEY] = current_data # Update state
        mismatches = st.session_state.get(MISMATCH_KEY, set())
        st.session_state[MISMATCH_KEY] = {(t, p) for t, p in mismatches if t != topic_to_delete}
        st.success(f"Topic '{topic_to_delete}' ({count} phrases) deleted.")
        st.rerun()
    elif not topic_to_delete: st.error("Select topic to delete.")

def add_phrase_state(topic, new_phrase):
    if TOPIC_MAPPING_STATE_KEY not in st.session_state or st.session_state[TOPIC_MAPPING_STATE_KEY] is None: return
    current_data = st.session_state[TOPIC_MAPPING_STATE_KEY]
    if topic and new_phrase and topic in current_data:
        phrase_to_add = str(new_phrase).strip()
        if not phrase_to_add: st.error("Phrase cannot be empty."); return
        if phrase_to_add not in current_data[topic]:
            current_data[topic].append(phrase_to_add)
            current_data[topic].sort()
            st.session_state[TOPIC_MAPPING_STATE_KEY] = current_data
            st.success(f"Phrase '{phrase_to_add}' added to '{topic}'.")
        else: st.warning(f"Phrase '{phrase_to_add}' already in '{topic}'.")
    elif not topic: st.error("Select topic.")
    elif not new_phrase: st.error("Enter phrase.")

def move_phrase_state(phrase_to_move, source_topic, target_topic):
    if TOPIC_MAPPING_STATE_KEY not in st.session_state or st.session_state[TOPIC_MAPPING_STATE_KEY] is None: return
    current_data = st.session_state[TOPIC_MAPPING_STATE_KEY]
    if not all([phrase_to_move, source_topic, target_topic]): st.error("Select phrase, source, and target."); return
    if source_topic not in current_data or phrase_to_move not in current_data[source_topic]:
        st.error(f"Phrase '{phrase_to_move}' not found in '{source_topic}'."); return
    target_topic_clean = str(target_topic).strip()
    if not target_topic_clean: st.error("Target topic cannot be empty."); return

    new_topic_created = False
    if target_topic_clean not in current_data:
        current_data[target_topic_clean] = []
        new_topic_created = True

    current_data[source_topic].remove(phrase_to_move)
    if phrase_to_move not in current_data[target_topic_clean]:
        current_data[target_topic_clean].append(phrase_to_move)
        current_data[target_topic_clean].sort()

    mismatches = st.session_state.get(MISMATCH_KEY, set())
    mismatches.discard((source_topic, phrase_to_move))
    st.session_state[MISMATCH_KEY] = mismatches

    st.session_state[TOPIC_MAPPING_STATE_KEY] = current_data
    st.success(f"Moved '{phrase_to_move}' from '{source_topic}' to '{target_topic_clean}'.")
    if new_topic_created: st.rerun()

def delete_phrase_state(topic, phrase_to_delete):
    if TOPIC_MAPPING_STATE_KEY not in st.session_state or st.session_state[TOPIC_MAPPING_STATE_KEY] is None: return
    current_data = st.session_state[TOPIC_MAPPING_STATE_KEY]
    if topic and phrase_to_delete and topic in current_data:
        if phrase_to_delete in current_data[topic]:
            current_data[topic].remove(phrase_to_delete)
            mismatches = st.session_state.get(MISMATCH_KEY, set())
            mismatches.discard((topic, phrase_to_delete))
            st.session_state[MISMATCH_KEY] = mismatches
            st.session_state[TOPIC_MAPPING_STATE_KEY] = current_data
            st.success(f"Deleted '{phrase_to_delete}' from '{topic}'.")
            # No rerun needed
        else: st.warning(f"Phrase '{phrase_to_delete}' not in '{topic}'.")
    elif not topic: st.error("Select topic.")
    elif not phrase_to_delete: st.error("Select phrase.")

def download_data(topic_data, filename="topics/updated_topic_mapping_data.json"):
    """Serialize topic data to JSON formatted string for download."""
    if not topic_data:
        st.error("No data available to download.")
        return None, None
    try:
        save_data = {topic: sorted(list(set(phrases))) for topic, phrases in topic_data.items() if isinstance(phrases, list)}
        file_path = Path(filename)
        file_path.touch(exist_ok=True)
        with open(filename, "w+") as f:
            json.dump(save_data, f, indent=4)
        return True
    except Exception as e:
        st.error(f"Failed to prepare data for download: {e}")
        return False

# --- Streamlit UI ---
st.set_page_config(layout="wide", page_title="Proximity Exploration Tool")
st.title("📝 Proximity Exploration Tool")

# --- Data Loading & Initialization ---
# Load data only once per session unless explicitly reloaded
if TOPIC_MAPPING_STATE_KEY not in st.session_state:
    st.session_state[TOPIC_MAPPING_STATE_KEY] = load_json_from_path(TOPIC_MAPPING_FILE_PATH, expected_format="dict")
    st.session_state[MISMATCH_KEY] = set()

if TOPICS_JSON_STATE_KEY not in st.session_state:
    st.session_state[TOPICS_JSON_STATE_KEY] = load_json_from_path(TOPICS_FILE_PATH, expected_format="dict")

# Derive the topic-doc map if both base files loaded successfully
if TOPIC_DOC_MAP_KEY not in st.session_state or st.session_state[TOPIC_DOC_MAP_KEY] is None:
    if st.session_state.get(TOPIC_MAPPING_STATE_KEY) and st.session_state.get(TOPICS_JSON_STATE_KEY):
        st.session_state[TOPIC_DOC_MAP_KEY] = create_direct_topic_to_doc_details_mapping_cached(
            st.session_state[TOPIC_MAPPING_STATE_KEY],
            st.session_state[TOPICS_JSON_STATE_KEY]
        )
    else:
        st.session_state[TOPIC_DOC_MAP_KEY] = {}


taxonomy_data_loaded = st.session_state.get(TOPIC_MAPPING_STATE_KEY) is not None
full_data_loaded = taxonomy_data_loaded and st.session_state.get(TOPICS_JSON_STATE_KEY) is not None


# --- Sidebar ---
with st.sidebar:
    if st.button("🔄 Reload", key="reload_btn"):
        load_json_from_path.clear()
        create_direct_topic_to_doc_details_mapping_cached.clear()
        st.session_state.pop(TOPIC_MAPPING_STATE_KEY, None)
        st.session_state.pop(TOPICS_JSON_STATE_KEY, None)
        st.session_state.pop(MISMATCH_KEY, None)
        st.session_state.pop(TOPIC_DOC_MAP_KEY, None)
        st.rerun()

    # --- Actions ---
    st.header("Actions")
    if taxonomy_data_loaded:
        condition = download_data(st.session_state[TOPIC_MAPPING_STATE_KEY])
        if condition:
            st.button(
                label="💾 Save Updated Topic Map",
                key="save_json_button"
            )
    else:
        st.warning("Load Topic Map data first to enable download.")


    # --- CRUD Operations (Sidebar) ---
    st.header("Modify Taxonomy")
    if taxonomy_data_loaded:
        current_topic_map_data = st.session_state[TOPIC_MAPPING_STATE_KEY]
        all_topics_list = sorted(current_topic_map_data.keys())

        with st.expander("➕ Topic Operations", expanded=False):
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

        with st.expander("✏️ Phrase Operations", expanded=False):
            st.subheader("Add Phrase to Topic")
            topic_for_add_phrase = st.selectbox("Select Topic:", all_topics_list, index=None, key="topic_add_phrase")
            new_phrase_input = st.text_input("New Phrase:", key="new_phrase")
            st.button("Add Phrase", key="add_phrase_btn", on_click=add_phrase_state, args=(topic_for_add_phrase, new_phrase_input), disabled=(not topic_for_add_phrase))

            st.subheader("Move Phrase to Different Topic")
            source_topic_move = st.selectbox("1. Source Topic:", all_topics_list, index=None, key="source_topic_move")
            phrases_in_source = sorted(current_topic_map_data.get(source_topic_move, [])) if source_topic_move else []
            phrase_to_move_select = st.selectbox("2. Phrase to Move:", phrases_in_source, index=None, key="phrase_to_move", disabled=not source_topic_move)
            allow_new_target = st.checkbox("Allow creating new target topic?", key="allow_new_target", value=True) # Default to allow creation
            if allow_new_target:
                target_topic_move = st.text_input("3. Target Topic (New or Existing):", key="target_topic_move_input")
            else:
                available_targets = [t for t in all_topics_list if t != source_topic_move]
                target_topic_move = st.selectbox("3. Target Topic:", available_targets, index=None, key="target_topic_move_select", disabled=not source_topic_move)
            st.button("Move Selected Phrase", key="move_phrase_btn", on_click=move_phrase_state, args=(phrase_to_move_select, source_topic_move, target_topic_move), disabled=(not phrase_to_move_select or not target_topic_move or not source_topic_move))

            st.subheader("Delete Phrase from Topic")
            topic_for_delete_phrase = st.selectbox("1. Select Topic:", all_topics_list, index=None, key="topic_delete_phrase")
            phrases_in_delete_topic = sorted(current_topic_map_data.get(topic_for_delete_phrase, [])) if topic_for_delete_phrase else []
            phrase_to_delete_select = st.selectbox("2. Select Phrase to Delete:", phrases_in_delete_topic, index=None, key="phrase_to_delete", disabled=not topic_for_delete_phrase)
            st.button("Delete Selected Phrase", key="delete_phrase_btn", type="primary", on_click=delete_phrase_state, args=(topic_for_delete_phrase, phrase_to_delete_select), disabled=(not phrase_to_delete_select))

        # --- Feedback Section (in expander) ---
        with st.expander("🚩 Mismatch Feedback", expanded=False):
            st.info("Mark phrases as mismatched in the main table below.")
            mismatched_set = st.session_state.get(MISMATCH_KEY, set())
            if mismatched_set:
                # Filter out mismatches related to topics/phrases that no longer exist
                valid_mismatches = {(t,p) for t,p in mismatched_set if t in current_topic_map_data and p in current_topic_map_data.get(t, [])}
                if valid_mismatches != mismatched_set:
                    st.session_state[MISMATCH_KEY] = valid_mismatches
                    mismatched_set = valid_mismatches # Update local variable
                    st.rerun() # Rerun to reflect the cleanup

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
    else:
        st.info("Load Topic Map data to enable taxonomy modifications.")


    # --- Filters for Main View ---
    st.header("View Filters")
    if taxonomy_data_loaded: # Filters depend at least on the topic list
        all_topics_list = sorted(st.session_state[TOPIC_MAPPING_STATE_KEY].keys())

        # Filter for Document Finder
        st.subheader("Document Finder")
        selected_topic_single = st.selectbox(
            "Select a Topic:",
            options=[""] + all_topics_list,
            index=0,
            key="doc_filter_topic",
            help="Select a single topic to view its associated documents."
        )

        # Filter for Graph Explorer
        st.subheader("Graph Explorer")
        selected_topics_multi = st.multiselect(
            "Select Topics for Graph:",
            options=all_topics_list,
            default=[],
            key="graph_filter_topics",
            help="Select one or more topics to visualize in the graph."
        )
    else:
        st.info("Load Topic Map data to enable filters.")


# --- Main UI Tabs ---
tab1, tab2, tab3 = st.tabs(["Knowledge Graph Viewer", "Document Finder", "Taxonomy Reviewer Tool"])

# --- Tab 1: Knowledge Graph Viewer ---
with tab1:
    st.header("Knowledge Graph Viewer")
    st.info("Visualize connections between selected topics | Select topics in the sidebar.")

    driver = get_neo4j_driver() # Attempt to get driver (placeholder)
    if driver is None:
        st.warning("Graph DB connection not configured. Displaying basic topic graph based on selected filters.")

    if not taxonomy_data_loaded:
        st.error("❌ Topic Map data not loaded. Cannot display graph.")
    else:
        selected_topics_multi = st.session_state.get("graph_filter_topics", [])
        if not selected_topics_multi:
            st.info("👈 Select one or more topics from the sidebar 'Filters' section to visualize.")
        else:
            st.write(f"Displaying graph for topics: {', '.join(selected_topics_multi)}")
            subgraph_data = fetch_subgraph_data(driver, selected_topics_multi)
            graph_html = generate_pyvis_html_from_neo4j_data(subgraph_data)
            components.html(graph_html, height=750, scrolling=False)


# --- Tab 2: Document Finder ---
with tab2:
    st.header("Document Finder")
    st.info("Find documents associated with a specific topic based on the loaded data. Select a topic in the sidebar.")

    driver = get_neo4j_driver()

    if not full_data_loaded:
         st.warning("⚠️ Required data is not fully loaded. Document lookup might be incomplete or unavailable.")
         if not taxonomy_data_loaded: st.stop() # Stop if no topics are even loaded

    selected_topic_single = st.session_state.get("doc_filter_topic", "")

    if not selected_topic_single:
        st.info("👈 Select a topic from the sidebar 'Filters' section.")
    else:
        st.subheader(f"Documents Related to Topic: '{selected_topic_single}'")
        if full_data_loaded and TOPIC_DOC_MAP_KEY in st.session_state:
            topic_doc_map = st.session_state[TOPIC_DOC_MAP_KEY]
            documents = topic_doc_map.get(normalize_key(selected_topic_single), [])
            if documents:
                 st.write(f"Found {len(documents)} documents:")
                 df_docs = pd.DataFrame(documents)
                 st.dataframe(df_docs, use_container_width=True, hide_index=True,
                     column_config={"doc_id": "ID", "title": "Title", "url": st.column_config.LinkColumn("URL", display_text="Visit 🔗")},
                     key="doc_finder_table_json")
            else:
                 st.info(f"No documents found for '{selected_topic_single}' based on the loaded JSON files.")
        elif not full_data_loaded:
             st.warning("Document lookup requires pre-loaded data: Please try again!")


with tab3:
    st.header("Taxonomy Reviewer Tool")
    st.info("Review, edit, and manage the topic-phrase relationships. Changes are reflected in the session and can be saved.")

    if not taxonomy_data_loaded:
        st.error("❌ Topic Map data ('topic_mapping.json') not loaded. Cannot display reviewer tool.")
        st.stop() 
    topic_mapping_data = st.session_state[TOPIC_MAPPING_STATE_KEY]
    all_topics_list = sorted(topic_mapping_data.keys())

    topic_search_term = st.text_input("Search Topics:", placeholder="Type to filter topics...", key="topic_search")
    topic_search_term_lower = topic_search_term.lower() if topic_search_term else ""
    filtered_topic_list = [
        topic for topic in all_topics_list
        if topic_search_term_lower in topic.lower()
    ] if topic_search_term else all_topics_list

    selected_topics = st.multiselect(
        f"Filter by specific topics ({len(filtered_topic_list)}/{len(all_topics_list)} shown):",
        options=filtered_topic_list,
        default=filtered_topic_list if not topic_search_term else [], # Show all initially, or none if searching
        key="topic_selector",
        help="Select topics to display their phrases in the table below. Leave empty to show all (matching search)."
    )
    topics_to_display = selected_topics if selected_topics else filtered_topic_list

    col1, col2 = st.columns(spec=[1, 2], gap="large")

    with col1:
        st.subheader("Topic Summary")
        df_summary = get_topic_summary(topic_mapping_data)
        df_summary_display = df_summary[df_summary['Topic'].isin(topics_to_display)]
        st.dataframe(df_summary_display, use_container_width=True, hide_index=True, key="summary_table")
        st.caption(f"Showing {len(df_summary_display)}/{len(df_summary)} topics.")

    with col2:
        st.subheader("Topic-Phrase Details")
        if not topics_to_display:
            st.info("Select topics or clear search to view phrases.")
        else:
            data_subset = {topic: topic_mapping_data[topic] for topic in topics_to_display if topic in topic_mapping_data}
            filtered_df_display = get_dataframe(data_subset)

            if filtered_df_display.empty:
                 st.info("No phrases found for the selected topic(s).")
            else:
                try:
                    edited_df = st.data_editor(
                        filtered_df_display,
                        use_container_width=True,
                        hide_index=True,
                        num_rows="dynamic",
                        column_config={
                            "Mismatch": st.column_config.CheckboxColumn("Mismatch?", default=False, help="Mark if this phrase doesn't fit the topic."),
                            "Topic": st.column_config.TextColumn(disabled=True), # Prevent direct editing of Topic/Phrase here
                            "Phrase": st.column_config.TextColumn(disabled=True)
                        },
                        key="phrase_editor"
                    )
                    original_subset_df = filtered_df_display[['Topic', 'Phrase', 'Mismatch']]
                    comparison_df = pd.merge(
                        edited_df[['Topic', 'Phrase', 'Mismatch']],
                        original_subset_df,
                        on=['Topic', 'Phrase'],
                        how='left',
                        suffixes=('_edited', '_original')
                    )
                    comparison_df['Mismatch_original'] = comparison_df['Mismatch_original'].fillna(False)
                    comparison_df['Mismatch_edited'] = comparison_df['Mismatch_edited'].fillna(False) # Ensure bool
                    changed_rows = comparison_df[comparison_df['Mismatch_edited'] != comparison_df['Mismatch_original']]

                    if not changed_rows.empty:
                        current_mismatches = st.session_state.get(MISMATCH_KEY, set()).copy()
                        mismatches_changed = False
                        for _, row in changed_rows.iterrows():
                            original_tuple = (row['Topic'], row['Phrase'])
                            if row['Mismatch_edited']:
                                if original_tuple not in current_mismatches:
                                    current_mismatches.add(original_tuple)
                                    mismatches_changed = True
                            else:
                                if original_tuple in current_mismatches:
                                    current_mismatches.discard(original_tuple)
                                    mismatches_changed = True

                        if mismatches_changed:
                            st.session_state[MISMATCH_KEY] = current_mismatches
                            st.rerun()

                    st.caption(f"Displaying {len(edited_df)} phrases. Use checkboxes for mismatch feedback. Use sidebar for Add/Delete/Move.")

                except Exception as e:
                    st.error(f"Error displaying or processing the data editor: {e}")
                    st.dataframe(filtered_df_display)
