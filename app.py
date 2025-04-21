import streamlit as st
from datetime import date
from utils.search_service import simple_search, advanced_search, pro_search
from utils.utils import *

APP_TITLE = "Proximity"

st.set_page_config(layout="wide")

if "messages" not in st.session_state:
    st.session_state.messages = []

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

search_mode = st.radio(
    'Available Search options',
    options=["Simple", "⚡ Advanced", "🚀 Pro"],
    horizontal=False, # Changed back to False as horizontal with captions can be wide
    captions=['Topic/Entity focus', 'Title/Summary focus', 'Full Content focus (Hybrid)'],
    key='search_mode_radio' # Added a key
)

# ---- Sidebar ----
with st.sidebar:
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

            results_count = len(search_results)
            intro_text = f"Found {results_count} relevant document(s) using {search_mode} mode for '{chat_query}':" if results_count > 0 else f"No matching documents found using {search_mode} mode for '{chat_query}'."
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
    st.rerun()

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
