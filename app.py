import streamlit as st
from datetime import date
from service import simple_search, advanced_search, pro_search
import time 

def render_document(doc: dict, show_content: bool = True):
    st.write(f"**Title:** {doc.get('pr_title', 'Untitled')}")

    # CSS for bubble styling (ensure this is defined once, perhaps outside the function if called often)
    bubble_css = """
    <style>
        .bubble-container { display: flex; gap: 8px; flex-wrap: wrap; margin: 10px 0; }
        .entity-bubble { background: #e3f2fd; border-radius: 15px; padding: 6px 12px; font-size: 0.9em; color: #1976d2; }
        .topic-bubble { background: #e8f5e9; border-radius: 15px; padding: 6px 12px; font-size: 0.9em; color: #2e7d32; }
    </style>
    """
    st.markdown(bubble_css, unsafe_allow_html=True)

    # Entities display
    if entities := doc.get("entities"):
        st.write("**Key Entities:**")
        entities_html = '<div class="bubble-container">'
        for entity in entities:
            text = entity.get("text", "").replace("'", "&#39;")
            entities_html += f'<div class="entity-bubble">{text}</div>'
        entities_html += "</div>"
        st.markdown(entities_html, unsafe_allow_html=True)

    # Topics display
    if topics := doc.get("topics"):
        st.write("**Related Topics:**")
        topics_html = '<div class="bubble-container">'
        for topic in topics:
            text = topic.get("text", "").replace("'", "&#39;")
            topics_html += f'<div class="topic-bubble">{text}</div>'
        topics_html += "</div>"
        st.markdown(topics_html, unsafe_allow_html=True)

    # Rest of the document rendering...
    st.write(f"**URL:** {doc.get('pr_url', 'No URL available')}")
    st.write(f"**Date:** {doc.get('pr_date', 'Unknown date')}")

    if show_content:
        st.write("**Content Preview:**")
        preview_text = doc.get("pr_content", "Content not available")
        st.text(preview_text[:1000] + "..." if len(preview_text) > 1000 else preview_text)


# NOTE: Removing caching for perform_search as parameters change frequently
# If search is slow and parameters stable, consider adding caching back carefully.
# @st.cache_data # Consider caching if search is slow and inputs don't change constantly
def perform_search(query, mode, k, fuzziness, start_date, end_date):
    """Calls the appropriate search function based on the mode."""
    start_date_str = str(start_date) if start_date else None
    end_date_str = str(end_date) if end_date else None
    results = []
    print(f"Performing search: Mode={mode}, Query='{query}', K={k}, Fuzz={fuzziness}, Start={start_date_str}, End={end_date_str}") # Debug print
    try:
        if mode == "Simple":
            results = simple_search(query, k, fuzziness, start_date_str, end_date_str)
        elif mode == "⚡ Advanced":
            results = advanced_search(query, k, fuzziness, start_date_str, end_date_str)
        elif mode == "🚀 Pro":
            results = pro_search(query, k, fuzziness, start_date_str, end_date_str)
    except Exception as e:
        st.error(f"An error occurred during search: {e}")
        print(f"Search Error: {e}") # Debug print
        results = [] # Ensure results is always a list
    return results if results else [] # Ensure return is always a list


# --- Streamlit App Layout ---
if "messages" not in st.session_state:
    st.session_state.messages = []

# ---- Header ----
st.markdown(
    """
    <style>
        .header {
            color: white;
            padding: 10px;
            text-align: center;
            font-size: 2em;
            font-weight: normal;
            border-radius: 100px;
            margin-bottom: 30px;
        }
        .stRadio [role=radiogroup]{
            padding: 15px;
            align-items: left; 
            justify-content: left; 
            text-align: left; 
            margin-left: auto; 
            margin-right: auto; 
            font-size: 1em;
        }
    </style>
    <div class="header">
        <h1>Proximity</h1>
        <h5>Intelligent Document Search</h5>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---- Search Mode Selection (Main Area) ----
search_mode = st.radio(
    'Available Search options',
    options=["Simple", "⚡ Advanced", "🚀 Pro"],
    horizontal=False, # Changed back to False as horizontal with captions can be wide
    captions=['Topic/Entity focus', 'Title/Summary focus', 'Full Content focus (Hybrid)'],
    key='search_mode_radio' # Added a key
)

# ---- Sidebar ----
with st.sidebar:
    # Instructions
    with st.expander("Search Guide", expanded=True, icon="🔥"):
         st.markdown(
            """
            ## Choose the appropriate search mode:
            ---                    
            - **Simple Search**: Find documents primarily by **topics** or **entities**. Good for category searches. (Uses Lexical/Fuzzy on specific fields)
            ---
            - **⚡ Advanced Search**: Focuses on **titles** and **summaries**. Good for finding specific headlines. (Uses Semantic + Lexical on title/summary)
            --- 
            - **🚀 Pro Search**: Deep **full content** search using a **hybrid** approach (Semantic + Lexical on multiple fields). Best for detailed information retrieval.
            """
        )

    # Date Range Filter
    st.header("📅 Date Range")
    col_date1, col_date2 = st.columns(2)
    with col_date1:
        start_date = st.date_input("Start date", value=date(2000, 1, 1), key='start_date')
    with col_date2:
        end_date = st.date_input("End date", value=date.today(), key='end_date') # Use today's date

    # Mode-Specific Parameters
    st.header("⚙️ Search Parameters")
    # Use columns within the expander for better layout if needed
    with st.expander("Adjust Parameters", expanded=True):
        # Define k and fuzziness vars outside the ifs first
        k_value = 10
        fuzziness_value = 1

        if search_mode == "Simple":
            # Simple search might not need fuzziness, or a fixed low value
            fuzziness_value = 0 # Typically exact match for topics/entities
            k_value = st.slider("Max Results", 1, 20, 5, key='k_simple')
            st.caption(f"Fuzziness fixed at {fuzziness_value} for Simple Search.")

        elif search_mode == "⚡ Advanced":
            k_value = st.slider("Max Results", 1, 50, 10, key='k_advanced')
            fuzziness_value = st.slider("Fuzziness", 0, 3, 1, help="Allows for spelling variations (0=exact)", key='fuzz_advanced')

        elif search_mode == "🚀 Pro":
            k_value = st.slider("Max Results", 1, 50, 10, key='k_pro')
            fuzziness_value = st.slider("Fuzziness", 0, 3, 1, help="Allows for spelling variations (0=exact)", key='fuzz_pro')

    # Content Preview Toggle
    content_preview = st.checkbox("Show content preview in results", False, key='content_preview_toggle')

# ---- Chat Interface ----
chat_display_container = st.container()
with chat_display_container:
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            # Check if the content is text or search results
            if isinstance(message["content"], str):
                st.markdown(message["content"])
            elif isinstance(message["content"], dict) and message["content"].get("type") == "search_results":
                # Render the stored search results
                st.markdown(message["content"]["intro_text"]) # Display the intro text like "Found X results"
                results_data = message["content"]["data"]
                query_context = message["content"]["query"] # Get the query associated with these results
                mode_context = message["content"]["mode"] # Get the mode associated with these results
                # Render each document using the helper function within an expander
                if not results_data:
                     st.markdown("No documents found for this query.")
                else:
                    for idx, doc in enumerate(results_data):
                         # Use query_context and idx for unique expander keys
                         with st.expander(f"📄 {doc.get('pr_title', 'Untitled')} (Score: {doc.get('score', 0.0)*100:.2f}%)"):
                             render_document(doc, st.session_state.get('content_preview_toggle', False)) # Use state for preview toggle


# React to user input
if chat_query := st.chat_input("Search Press releases from Rep. Larson ..."):
    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": chat_query})

    # Display user message immediately
    with st.chat_message("user"):
        st.markdown(chat_query)

    # Prepare and display "thinking" message for the assistant
    with st.chat_message("assistant"):
        with st.spinner(f"Searching with {search_mode} mode..."):
            # Perform the search using the *current* state of UI elements
            search_results = perform_search(
                query=chat_query,
                mode=search_mode,
                k=k_value, # Use the value determined in the sidebar logic
                fuzziness=fuzziness_value, # Use the value determined in the sidebar logic
                start_date=start_date,
                end_date=end_date
            )

            # --- Process and Store Results ---
            results_count = len(search_results)
            intro_text = f"Found {results_count} relevant document(s) using {search_mode} mode for '{chat_query}':" if results_count > 0 else f"No matching documents found using {search_mode} mode for '{chat_query}'."

            # Store the results (or lack thereof) in the session state
            # We store the raw data, not the rendered components
            st.session_state.messages.append({
                "role": "assistant",
                "content": {
                    "type": "search_results",
                    "intro_text": intro_text,
                    "data": search_results, # Store the list of document dicts
                    "query": chat_query, # Store context
                    "mode": search_mode   # Store context
                }
            })

    # Rerun the app immediately after adding the assistant message.
    # The loop at the beginning will then render the new message, including results.
    st.rerun()


# ---- Footer Implementation ----
st.markdown(
    """
<style>
    .footer {
        position: relative;
        left: 0;
        bottom: 0;
        width: 100%;
        color: #ffffff;
        text-align: center;
        padding: 5px 0;
        border-top: 0.5px solid #1b1f22;
    }
</style>
<div class="footer">
    <p>© 2025 Proximity | Team Larson - UMD MIM Capstone Program</p>
</div>
""",
    unsafe_allow_html=True,
)
