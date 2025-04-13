import streamlit as st
from datetime import date
from service import simple_search, advanced_search, pro_search


def render_document(doc: dict, show_content: bool = True):
    st.write(f"**Title:** {doc.get('pr_title', 'Untitled')}")

    # CSS for bubble styling
    bubble_css = """
    <style>
        .bubble-container {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
            margin: 10px 0;
        }
        .entity-bubble {
            background: #e3f2fd;
            border-radius: 15px;
            padding: 6px 12px;
            font-size: 0.9em;
            color: #1976d2;
        }
        .topic-bubble {
            background: #e8f5e9;
            border-radius: 15px;
            padding: 6px 12px;
            font-size: 0.9em;
            color: #2e7d32;
        }
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
        st.text(doc.get("pr_content", "Content not available")[:1000] + "...")


# ---- Header Implementation ----
st.markdown(
    """
<style>
    .header {
        background-color: #1b1f22;
        color: white;
        padding: 30px;
        text-align: center;
        font-size: 3em;
        font-weight: bold;
        border-radius: 5px;
        margin-bottom: 20px;
    }
</style>
<div class="header">
    <h1>DeepSearch Pro</h1>
    <h5>Intelligent Document Search</h5>
</div>
""",
    unsafe_allow_html=True,
)

# ---- Sidebar Improvements ----
with st.sidebar:
    # Expanded instructions
    with st.expander("Search Guide", expanded=True, icon="🔥"):
        st.markdown(
            """
        ## Choose the appropriate search mode:
        ---                    
        - 🔍 **Simple Search**
          - Find documents by topics or entities
          - Best for: Category-based search, finding related concepts
        ---
        - ⚡ **Advanced Search**
          - Search titles and summaries
          - Best for: Finding specific press releases by headline
        --- 
        - 🚀 **Pro Search**
          - Deep content search
          - Best for: Finding detailed information within document text
        """
        )

    # Search mode selector
    st.header("Search Mode")
    search_mode = st.radio(
        "Select search type:", ["🔍 Simple", "⚡ Advanced", "🚀 Pro"], horizontal=True
    )

    # Date range filter
    st.header("📅 Date Range")
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("Start date", value=date(2000, 1, 1))
    with col2:
        end_date = st.date_input("End date", value=date(2025, 4, 2))

    # Mode-specific parameters
    with st.expander("⚙️ Search Parameters", expanded=True):
        if search_mode == "🔍 Simple":
            fuzziness = st.slider(
                "Fuzzy matching",
                0,
                5,
                2,
                help="Higher values match more spelling variations",
            )
            k = st.slider("Results per page", 5, 50, 10)

        elif search_mode == "⚡ Advanced":
            col1, col2 = st.columns(2)
            with col1:
                k = st.slider("Results", 5, 50, 10)
            with col2:
                fuzziness = st.slider("Fuzzy", 0, 5, 2)

        elif search_mode == "🚀 Pro":
            k = st.slider("Results per page", 5, 50, 10)
            fuzziness = st.slider("Fuzzy matching", 0, 5, 2)

    # Content preview toggle
    content_preview = st.checkbox("Show content preview", True)

# ---- Main Interface ----
st.subheader("Enter your search query")
query = st.text_input(
    "Search for: ",
    placeholder="Search for topics, entities, or content...",
    label_visibility="collapsed",
)

# Search button with mode-specific label
button_label = {
    "🔍 Simple": "🔍 Search Keywords, Topics, & Entities",
    "⚡ Advanced": "⚡ Dive into full Titles & Summaries",
    "🚀 Pro": "🚀 Search Full Content, Summaries, Topics, & Entities",
}

if st.button(button_label[search_mode], type="primary", use_container_width=True):
    if query:
        with st.spinner(f" Running {search_mode} search..."):
            # Convert date objects to strings
            start_date_str = str(start_date) if start_date else None
            end_date_str = str(end_date) if end_date else None

            # Execute appropriate search based on mode
            if search_mode == "🔍 Simple":
                results = simple_search(
                    query, k, fuzziness, start_date_str, end_date_str
                )
                # Display results
                if results:
                    st.success(f"Found {len(results)} relevant documents")
                    for doc in results:
                        with st.expander(
                            f"📄 {doc.get('pr_title', 'Untitled')} - Normalized Match Score: {doc['score']*100:.2f}"
                        ):
                            render_document(doc, content_preview)
                else:
                    st.warning(
                        "No matching documents found. Try broadening your search."
                    )
            elif search_mode == "⚡ Advanced":
                results = advanced_search(
                    query, k, fuzziness, start_date_str, end_date_str
                )
                # Display results
                if results:
                    st.success(f"Found {len(results)} relevant documents")
                    for doc in results:
                        with st.expander(
                            f"📄 {doc.get('pr_title', 'Untitled')} - Normalized Match Score: {doc['score']*100:.2f}"
                        ):
                            render_document(doc, content_preview)
                else:
                    st.warning(
                        "No matching documents found. Try broadening your search."
                    )
            elif search_mode == "🚀 Pro":
                results = pro_search(query, k, fuzziness, start_date_str, end_date_str)
                # Display results
                if results:
                    st.success(f"Found {len(results)} relevant documents")
                    for doc in results:
                        with st.expander(
                            f"📄 {doc.get('pr_title', 'Untitled')} - Normalized Match Score: {doc['score']*100:.2f}"
                        ):
                            render_document(doc, content_preview)
                else:
                    st.warning(
                        "No matching documents found. Try broadening your search."
                    )


st.markdown(
    """
<style>
    .footer {
        position: fixed;
        left: 0;
        bottom: 0;
        width: 100%;
        background-color: #1b1f22;
        color: #ffffff;
        text-align: center;
        padding: 10px 0;
        border-top: 1px solid #1b1f22;
    }
</style>
<div class="footer">
    <p>© 2025 DeepSearch Pro | Team Larson - UMD MIM Capstone Program</p>
</div>
""",
    unsafe_allow_html=True,
)
