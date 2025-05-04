import streamlit as st
from datetime import date, datetime
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
            align-items: center;
            justify-content: center;
            text-align: center;
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
    label = "---",
    options=["Simple", "⚡ Advanced", "🚀 Pro"],
    horizontal=True,
    captions=['Topic/Entity focus', 'Title/Summary focus', 'Full Content focus (Hybrid)'],
    key='search_mode_radio'
)

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
        end_date = st.date_input("End date", value=date.today(), key='end_date')

    # Mode-Specific Parameters & Sorting
    st.header("⚙️ Parameters & Display")
    with st.expander("Adjust Parameters", expanded=True):
        k_value = 10
        fuzziness_value = 1

        if search_mode == "Simple":
            fuzziness_value = 0
            k_value = st.slider("Max Results", 1, 20, 5, key='k_simple')
            st.caption(f"Fuzziness fixed at {fuzziness_value} for Simple Search.")
        elif search_mode == "⚡ Advanced":
            k_value = st.slider("Max Results", 1, 50, 10, key='k_advanced')
            fuzziness_value = st.slider("Fuzziness", 0, 3, 1, help="Allows spelling variations (0=exact)", key='fuzz_advanced')
        elif search_mode == "🚀 Pro":
            k_value = st.slider("Max Results", 1, 50, 10, key='k_pro')
            fuzziness_value = st.slider("Fuzziness", 0, 3, 1, help="Allows spelling variations (0=exact)", key='fuzz_pro')

        sort_by_option = st.selectbox(
            "Sort Results By",
            options=["Relevance Score", "Date (Newest First)"],
            key='sort_by_select',
            index=0
        )
    content_preview = st.checkbox("Show content preview in results", False, key='content_preview_toggle')

chat_display_container = st.container()
with chat_display_container:
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            if isinstance(message["content"], str):
                st.markdown(message["content"])
            elif isinstance(message["content"], dict) and message["content"].get("type") == "search_results":
                st.markdown(message["content"]["intro_text"])
                results_data = message["content"]["data"]
                query_context = message["content"]["query"]
                mode_context = message["content"]["mode"]
                show_preview = st.session_state.get('content_preview_toggle', False)

                if not results_data:
                     st.markdown("No documents found for this query.")
                else:
                    score_key = 'cross_encoder_score' if 'cross_encoder_score' in results_data[0] else 'score'
                    if score_key not in results_data[0] and 'normalized_score_100' in results_data[0]:
                        score_key = 'normalized_score_100'

                    for idx, doc in enumerate(results_data):
                         display_score = doc.get(score_key, 0.0)
                         score_display_text = f"{display_score:.2f}%" if score_key == 'normalized_score_100' else f"{display_score:.4f}"

                         with st.expander(f"📄 {doc.get('pr_title', 'Untitled')} (Score: {score_display_text}) | Date: {doc.get('pr_date', 'N/A')}"):
                             render_document(doc, show_preview)


# React to user input
if chat_query := st.chat_input("Search Press releases from Rep. Larson ..."):
    st.session_state.messages.append({"role": "user", "content": chat_query})
    with st.chat_message("user"):
        st.markdown(chat_query)
    with st.chat_message("assistant"):
        with st.spinner(f"Searching with {search_mode} mode..."):
            start_date_str = start_date.strftime('%Y-%m-%d') if start_date else None
            end_date_str = end_date.strftime('%Y-%m-%d') if end_date else None
            search_results = perform_search(
                query=chat_query,
                mode=search_mode, 
                k=k_value,
                fuzziness=fuzziness_value,
                start_date=start_date_str,
                end_date=end_date_str
            )
            sorted_results = search_results
            if search_results:
                current_sort_option = st.session_state.get('sort_by_select', "Relevance Score")
                st.write(f"Sorting by: {current_sort_option}")
                score_key = 'cross_encoder_score' if 'cross_encoder_score' in search_results[0] else 'score'
                if score_key not in search_results[0] and 'normalized_score_100' in search_results[0]:
                    score_key = 'normalized_score_100'

                if current_sort_option == "Date (Newest First)":
                    try:
                        sorted_results = sorted(search_results,
                                                key=lambda doc: datetime.strptime(doc.get('pr_date', '1900-01-01'), '%Y-%m-%d'),
                                                reverse=True)
                    except ValueError:
                         st.warning("Date parsing failed for some results, falling back to string sort for date.")
                         sorted_results = sorted(search_results,
                                                 key=lambda doc: doc.get('pr_date', '0000-00-00'),
                                                 reverse=True)

                elif current_sort_option == "Relevance Score":
                     sorted_results = sorted(search_results,
                                             key=lambda doc: doc.get(score_key, 0.0),
                                             reverse=True)

            results_count = len(sorted_results)
            intro_text = f"Found {results_count} relevant document(s) using {search_mode} mode for '{chat_query}':" if results_count > 0 else f"No matching documents found using {search_mode} mode for '{chat_query}'."
            st.session_state.messages.append({
                "role": "assistant",
                "content": {
                    "type": "search_results",
                    "intro_text": intro_text,
                    "data": sorted_results,
                    "query": chat_query,
                    "mode": search_mode
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
    <p>© 2025 Team Larson - UMD MIM Capstone Program</p>
</div>
""",
    unsafe_allow_html=True,
)
