from knowledge_graph.utils import *

# --- Streamlit UI ---
st.set_page_config(layout="wide", page_title=APP_TITLE)
st.title(f"🔎 {APP_TITLE}")

# --- Initialize Connection ---
driver = get_neo4j_driver()

# --- Sidebar for Filters ---
st.sidebar.header("Filters")
all_topics = fetch_topics(driver)
if not all_topics: st.sidebar.warning("Could not fetch topics."); st.warning("Could not fetch topics."); st.stop()

# Filter for Document Finder
st.sidebar.subheader("Document Finder")
selected_topic_single = st.sidebar.selectbox("Select a Topic:", options=[""] + all_topics, index=0, key="doc_filter_topic")

# Filter for Graph Explorer
st.sidebar.subheader("Graph Explorer")
selected_topics_multi = st.sidebar.multiselect("Select Topics for Graph:", options=all_topics, default=[], key="graph_filter_topics")

# --- Main Area with Tabs ---
tab1, tab2 = st.tabs(["📄 Document Finder", "🕸️ Graph Explorer"])

# --- Tab 1: Document Finder ---
with tab1:
    st.header(f"Documents Related to Topic: '{selected_topic_single or 'None Selected'}'")
    if not selected_topic_single: st.info("Select a topic from the sidebar.")
    else:
        documents = fetch_documents_for_topic(driver, selected_topic_single)
        if documents:
            st.write(f"Found {len(documents)} documents:")
            df_docs = pd.DataFrame(documents)
            st.dataframe(df_docs, use_container_width=True, hide_index=True,
                column_config={"doc_id": "ID", "title": "Title", "url": st.column_config.LinkColumn("URL", display_text="Visit 🔗")},
                key="doc_finder_table")
        else: st.info(f"No documents found for '{selected_topic_single}'.")

# --- Tab 2: Graph Explorer ---
with tab2:
    st.header("Topic-Document Linkage Graph")
    if not selected_topics_multi: st.info("Select one or more topics from the sidebar to visualize.")
    else:
        st.write(f"Displaying subgraph for topics: {', '.join(selected_topics_multi)}")
        subgraph_data = fetch_subgraph_data(driver, selected_topics_multi)
        graph_html = generate_pyvis_html_from_neo4j_data(subgraph_data)
        # Set scrolling=True if graph becomes very wide/tall and needs scrolling within the iframe
        components.html(graph_html, height=750, scrolling=False)

# --- Footer (Optional) ---
st.sidebar.markdown("---")
st.sidebar.caption("Neo4j Graph Explorer App")
