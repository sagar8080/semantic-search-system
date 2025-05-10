## I. Conceptual System Architecture and Modules

The system is designed for semantic document processing and intelligent search, leveraging tools like Streamlit for the UI, OpenSearch for data storage and search, Neo4j for knowledge graph capabilities, and AWS Bedrock for LLM-powered features like query expansion and reranking.

### 1. Document Ingestion Layer

**Purpose**: This layer is responsible for acquiring press release documents, extracting their content and initial metadata, and preparing them for further processing and storage.

**Associated Scripts**:
*   `pr_meta_fetch.py`
*   `pr_meta_store_from_local.py`
*   `pr_meta_store.py`

**Step-by-Step Functionality**:
1.  **Initial Metadata Fetching**:
    *   The `pr_meta_fetch.py` script initiates the process by scraping press release URLs, titles, and publication dates from the "larson.house.gov" website.
    *   It paginates through the press release listings to gather a comprehensive list of links.
    *   For each link, it fetches the individual press release page to extract the title and date.
    *   This collected metadata (URL, title, date) is then saved into a local JSON file, `press_releases.json`.
2.  **Storing Initial Metadata to OpenSearch**:
    *   The `pr_meta_store_from_local.py` script takes the `press_releases.json` file as input.
    *   It reads the press release entries from this file.
    *   For each entry, it adds a `"processed": false` flag, indicating that the full content has not yet been fetched and stored.
    *   It then stores these entries (including an auto-incremented ID) into a dedicated OpenSearch index, `PR_META_URL_IDX`. This index acts as a queue for further processing.
3.  **Fetching and Storing Full Document Content**:
    *   The `pr_meta_store.py` script processes the entries in `PR_META_URL_IDX` that are marked as `"processed": false`.
    *   It fetches entries in batches, often filtered by year and month, to manage the workload.
    *   For each unprocessed entry (identified by its URL), it visits the press release URL to scrape the full textual content of the press release.
    *   The extracted text is cleaned (e.g., removing special characters, normalizing whitespace).
    *   The cleaned content, along with the existing metadata (URL, title, date), is then stored in a separate OpenSearch index, `PR_META_RAW_IDX`. The document ID from `PR_META_URL_IDX` is reused for consistency.
    *   After successfully storing the full content, the script updates the corresponding entry in `PR_META_URL_IDX` by setting its `"processed"` flag to `true`. This is done in bulk for efficiency.
    *   The script includes logic to process entries that might have been skipped previously.

### 2. Data Lake / Storage Layer

**Purpose**: This layer provides robust and scalable storage for all data, including raw document content, processed text, metadata, semantic embeddings, and knowledge graph relationships. OpenSearch and Neo4j are the primary storage technologies.

**Associated Scripts/Components**:
*   `create_vector_index.py` (Defines OpenSearch index structures)
*   OpenSearch Indexes: `PR_META_URL_IDX`, `PR_META_RAW_IDX`, `PR_META_VECTOR_IDX`
*   `knowledge_graph.py` (Manages Neo4j storage)
*   Neo4j Database
*   Local JSON files: `topics/topic_mapping.json`, `topics/topics.json`

**Step-by-Step Functionality**:
1.  **OpenSearch Index Setup**:
    *   The `create_vector_index.py` script is responsible for defining and creating the necessary OpenSearch indexes if they don't already exist.
    *   **`PR_META_URL_IDX`**: Stores initial press release metadata (URL, title, date) and a `processed` flag. Used as a staging area for content fetching. The creation logic for this specific index is implied by its usage in `pr_meta_store_from_local.py` and `pr_meta_store.py`, potentially using `create_meta_index` from `create_vector_index.py`.
    *   **`PR_META_RAW_IDX`**: Stores the full, cleaned textual content of press releases along with their basic metadata. This serves as the source for semantic processing. It's created using `create_meta_index`.
    *   **`PR_META_VECTOR_IDX`**: This is a crucial index for semantic search. Its mapping, defined in `create_vector_index.py`, includes:
        *   `embedding`: A `knn_vector` field to store document embeddings (e.g., from Amazon Titan, dimension 256) for k-Nearest Neighbor (k-NN) search.
        *   Metadata fields: `pr_url`, `pr_title`, `summary`, `pr_date`, `pr_content`.
        *   `entities`: A nested field to store extracted named entities (text and label).
        *   `topics`: A nested field to store identified topics (text and label).
2.  **Neo4j Graph Database Setup**:
    *   The `knowledge_graph.py` script manages the Neo4j database which stores relationships between topics and documents.
    *   It establishes a connection to the Neo4j instance using credentials.
    *   It includes functions to clean up the database by deleting existing nodes and relationships, and to drop and create constraints (e.g., uniqueness for `BroadTopic` names and `Document` IDs).
3.  **Data Population**:
    *   **OpenSearch**: Populated by `pr_meta_store_from_local.py` and `pr_meta_store.py` as described in the Document Ingestion Layer. The `PR_META_VECTOR_IDX` would be populated by a separate semantic processing pipeline (not fully detailed in the provided scripts but implied) that generates embeddings, extracts entities, and identifies topics from `PR_META_RAW_IDX`.
    *   **Neo4j**: Populated by `knowledge_graph.py` using data from `topics/topic_mapping.json` (mapping broad topics to phrases) and `topics/topics.json` (mapping phrases to document details). It creates `BroadTopic` nodes, `Document` nodes (with `docId`, `url`, `title`), and `RELATES_TO_DOC` relationships between them.
    *   **Local JSON Files**: `topics/topic_mapping.json` and `topics/topics.json` act as a source for the knowledge graph and are also used by the `explorer_app.py` for taxonomy management and document finding.

### 3. Semantic Processing Layer

**Purpose**: This layer enriches the raw data by applying Natural Language Processing (NLP) techniques to extract meaning, generate semantic representations (embeddings), and identify key information like entities and topics. These enrichments power intelligent search and analysis.

**Associated Scripts/Components**:
*   `create_vector_index.py` (Defines where semantic information is stored)
*   `search_pipeline.py` (Query-side semantic processing: expansion, reranking)
*   `search_service.py` (Utilizes embeddings for search)
*   AWS Bedrock (for LLM functionalities like embedding generation, query expansion, reranking)
*   (Implied) Document processing pipeline: A pipeline (not explicitly shown in these scripts) would be responsible for:
    *   Reading documents from `PR_META_RAW_IDX`.
    *   Performing text chunking if necessary.
    *   Generating embeddings for document content/chunks using a model like Amazon Titan.
    *   Performing Named Entity Recognition (NER).
    *   Performing Topic Modeling.
    *   Storing these enrichments (embeddings, entities, topics) into `PR_META_VECTOR_IDX`.

**Step-by-Step Functionality (Focus on Query-Time and Implied Document-Time Processing)**:
1.  **(Implied) Document-Side Semantic Enrichment (Populating `PR_META_VECTOR_IDX`)**:
    *   Text from `PR_META_RAW_IDX` is processed.
    *   Embeddings are generated for the content (or relevant chunks) using a model like Amazon Titan (dimension 256 as specified in `create_vector_index.py`).
    *   NLP models are used to extract named entities (e.g., persons, organizations, locations) and their types.
    *   Topic modeling techniques are applied to identify key topics within documents.
    *   This structured semantic information (embeddings, entities, topics) is then indexed into `PR_META_VECTOR_IDX` alongside document metadata.
2.  **Query-Side Semantic Processing**:
    *   **Query Embedding Generation**: When a user performs a semantic or hybrid search, the input query text is converted into a numerical embedding vector using the same model that was used for document embeddings (e.g., Amazon Titan, via `generate_embeddings` likely calling Bedrock).
    *   **Query Expansion (Optional)**: The `search_pipeline.py` includes `expand_query_with_llm()`. This function can take the user's original query and use an LLM (via `engage_llm` from `bedrock.py`) to generate alternative queries or relevant keywords, aiming to capture a broader user intent. These expanded terms can be used in lexical search components.
    *   **Reranking (Optional)**: After initial retrieval from OpenSearch, the `search_pipeline.py` provides `rerank_with_bedrock()`. This function takes a list of candidate documents and the original query, sends them to an AWS Bedrock reranking model, and reorders the documents based on semantic relevance scores provided by the reranker. This helps improve the precision of the top search results.

### 4. Knowledge Graph Module

**Purpose**: This module constructs and utilizes a knowledge graph to represent and explore relationships between entities, primarily between defined topics and the documents associated with them. This enables a more contextual understanding and navigation of the information.

**Associated Scripts**:
*   `knowledge_graph.py`
*   `explorer_app.py` (specifically the "Knowledge Graph Viewer" and "Taxonomy Reviewer Tool" tabs)
*   Input files: `topics/topic_mapping.json`, `topics/topics.json`

**Step-by-Step Functionality**:
1.  **Data Source Preparation**:
    *   `topics/topic_mapping.json`: Defines a hierarchy or mapping where broad topics are associated with a list of more specific key phrases.
    *   `topics/topics.json`: Maps these key phrases to actual documents, including document ID, URL, and title.
2.  **Knowledge Graph Construction (in Neo4j)**:
    *   The `knowledge_graph.py` script orchestrates loading this topical data into Neo4j.
    *   **Database Initialization**: It can optionally clean the entire Neo4j database (delete all nodes and relationships) and set up constraints (e.g., `BroadTopic.name` and `Document.docId` must be unique).
    *   **Node Creation**:
        *   For each broad topic found in `topic_mapping.json`, a `:BroadTopic` node is created in Neo4j (or merged if it already exists).
        *   For each document referenced in `topics.json` (linked via phrases), a `:Document` node is created/merged, storing its `docId`, `url`, and `title`.
    *   **Relationship Creation**:
        *   The script iterates through the `topic_mapping_data`. For each broad topic and its associated phrases, it looks up these phrases in `topics_data` to find linked documents.
        *   A `RELATES_TO_DOC` relationship is created in Neo4j directly connecting the `:BroadTopic` node to the corresponding `:Document` node. Keys are normalized (stripped, lowercased) during this process to ensure consistency.
3.  **Knowledge Graph Exploration and Management**:
    *   The `explorer_app.py` Streamlit application provides a "Knowledge Graph Viewer" tab.
    *   Users can select topics, and the application is intended to fetch subgraph data (function `fetch_subgraph_data` is mentioned, likely querying Neo4j or processing the loaded JSONs) and visualize the connections using PyVis.
    *   The "Taxonomy Reviewer Tool" tab in `explorer_app.py` allows users to view, manage, and edit the `topic_mapping.json` data (topics and their phrases). Changes made here can be saved and would subsequently affect the data loaded into Neo4j on the next run of `knowledge_graph.py`.

### 5. Search and Query Interface

**Purpose**: This layer provides the user interface and backend services for users to search, discover, and interact with the documents and the knowledge within the system.

**Associated Scripts**:
*   `main_app.py` (Streamlit app entry point)
*   `explorer_app.py` (Streamlit UI for topic exploration, document finding, graph visualization)
*   `search_pipeline.py` (Core search execution and result processing logic)
*   `search_service.py` (Defines different search strategies and OpenSearch query construction)
*   `utils.py` (in `utils` directory) (UI rendering helpers)

**Step-by-Step Functionality**:
1.  **User Interface (Streamlit)**:
    *   `main_app.py` sets up the basic Streamlit page configuration.
    *   `explorer_app.py` provides a multi-tab "Proximity Exploration Tool":
        *   **Knowledge Graph Viewer**: Visualizes topic relationships. Users select topics, and a graph is displayed.
        *   **Document Finder**: Allows users to select a broad topic and view a list of associated documents (ID, title, URL) based on the mappings in `topic_doc_map` (derived from `topics.json` and `topic_mapping.json`).
        *   **Taxonomy Reviewer Tool**: An interface for managing the topic-to-phrase mappings in `topic_mapping.json`. Users can add, rename, delete topics, and add, move, delete phrases. It also allows marking phrases as mismatched with topics.
    *   (Implied) A separate search interface likely exists or is intended, where users can input free-text queries. The `utils.py` script imports search functions and has a `render_document` function, suggesting it's part of a search results display page in a Streamlit app.
2.  **Search Execution Backend**:
    *   **Query Input**: Users submit queries through the UI.
    *   **Search Strategy Selection**: The system can employ different search strategies, defined in `search_service.py`:
        *   `simple_search`: Focuses on lexical/keyword matching within topics and entities using OpenSearch `match` and `term` queries with fuzziness.
        *   `advanced_search`: Combines lexical (`multi_match` on title/summary) with semantic search (k-NN vector search on `embedding` field). Requires query embedding generation.
        *   `pro_search`: Implements a hybrid search by combining scores from lexical queries (across title, content, summary, entities, topics) and a semantic k-NN query using OpenSearch's `hybrid` query type.
        *   `pro_search_enhanced`: An advanced hybrid search that includes optional LLM-based query expansion and reranking via Bedrock. It constructs more complex lexical and semantic queries.
        *   `search_kb`: Similar to `pro_search_enhanced`, tailored for knowledge base searching, including LLM expansion, reranking, and a relevance threshold for reranked results.
    *   **OpenSearch Query Construction**: Functions in `search_service.py` build the appropriate JSON-based query bodies for OpenSearch, incorporating keywords, fuzziness, query embeddings, date filters (via `build_date_filter` from `search_pipeline.py`), and k-NN parameters.
    *   **Search Execution**: The `execute_search` function in `search_pipeline.py` sends the constructed query to the OpenSearch client and retrieves the raw results.
3.  **Results Processing and Presentation**:
    *   **Score Normalization**: `normalize_scores_to_100` in `search_pipeline.py` converts raw OpenSearch scores to a 0-100 scale for easier interpretation.
    *   **Reranking (if enabled)**: `rerank_with_bedrock` in `search_pipeline.py` reorders results based on a Bedrock reranking model.
    *   **Display**: Results are formatted and displayed in the Streamlit UI. `utils.py` contains a `render_document` function that structures the display of each document, including title, entities (with bubble CSS), topics, summary, and optionally the full content.

### 6. Governance, Access Control & Security Module

**Purpose**: This conceptual module would be responsible for managing user access, ensuring data security, and maintaining audit trails.

**Associated Scripts/Components**:
*   Neo4j connection in `knowledge_graph.py` uses credentials from an environment/config file.
*   OpenSearch client (`get_os_client()`) setup might handle AWS authentication (e.g., AWSV4SignerAuth as seen in `pr_meta_store_from_local.py` imports, though its direct use in `get_os_client` isn't shown).

**Step-by-Step Functionality (Current State)**:
*   **Credentials Management**: Database and service credentials (e.g., Neo4j URI, username, password; AWS credentials for Bedrock and OpenSearch) are expected to be managed externally (e.g., environment variables, configuration files).
*   **Explicit User Authentication/RBAC**: The provided scripts do not detail explicit user login systems, role-based access control within the application itself, or fine-grained document-level permissions beyond what OpenSearch or Neo4j might offer natively if configured.
*   **Audit Logging**: Standard Python logging is used in several scripts (e.g., `search_pipeline.py`, `knowledge_graph.py`), which can provide some level of operational audit trail. However, dedicated user activity audit logging for security purposes is not explicitly implemented.

This module is more of a placeholder for future development if stricter security and governance features are required.

## II. Detailed Python Script Documentation

This section provides a step-by-step breakdown of each significant Python script in the repository.

---

### File: `main_app.py`

**Purpose**: This script serves as the main entry point for the Streamlit application, setting up the basic page configuration.

**Key Dependencies/Inputs**:
*   `streamlit`
*   `datetime` (date, datetime)
*   `utils.utils` (custom utility functions, likely including `render_document`)

**Core Functionality (Step-by-Step)**:
1.  **Import Libraries**: Imports necessary modules like `streamlit` and utility functions.
2.  **Set Application Title**: Defines an `APP_TITLE` variable, e.g., "Proximity". While defined, it's not directly used by `st.set_page_config(page_title=...)` in the snippet.
3.  **Configure Page Layout**:
    *   `st.set_page_config(layout="wide")`: Configures the Streamlit page to use a wide layout, utilizing more of the screen width.
4.  **Initialize Session State (if needed)**:
    *   Checks if `"messages"` exists in `st.session_state`. If not, it initializes `st.session_state.messages` as an empty list. This is typical for chatbot-like interfaces but might be used for other status messages here.
5.  **Display Footer**:
    *   `st.markdown(...)`: Displays a footer message, such as copyright information, using Markdown. Example: "© 2025 Team Larson - UMD MIM Capstone Program".

**Outputs/Side Effects**:
*   Renders the basic Streamlit application frame with a wide layout and a footer.
*   Initializes `st.session_state.messages`.

---

### File: `explorer_app.py`

**Purpose**: This script creates a multi-tab Streamlit application called "Proximity Exploration Tool." It allows users to explore and manage topic taxonomies, find documents related to topics, and visualize knowledge graphs.

**Key Dependencies/Inputs**:
*   `streamlit` (st)
*   `pandas` (pd)
*   `json`
*   `networkx` (nx), `pyvis.network` (Network) for graph visualization
*   `os`, `re`, `pathlib`
*   `knowledge_graph.utils` (custom utilities, possibly for Neo4j interaction like `get_neo4j_driver`, `fetch_subgraph_data`, `generate_pyvis_html_from_neo4j_data`)
*   Input JSON files: `topics/topic_mapping.json`, `topics/topics.json`

**Core Functionality (Step-by-Step)**:

1.  **Initialization and Configuration**:
    *   Sets Streamlit page config: `st.set_page_config(layout="wide", page_title="Proximity Exploration Tool")`.
    *   Displays the main title: `st.title("📝 Proximity Exploration Tool")`.
    *   Defines constants for session state keys (e.g., `TOPIC_MAPPING_STATE_KEY`, `TOPICS_JSON_STATE_KEY`) and file paths.

2.  **Data Loading (`load_json_from_path`, `create_direct_topic_to_doc_details_mapping_cached`)**:
    *   `load_json_from_path(file_path, expected_format)`:
        *   Cached function to load data from a JSON file specified by `file_path`.
        *   Performs error checking: file existence, JSON decoding errors, and expected data type (e.g., dict).
        *   Uses `re.sub` to preprocess the JSON string, potentially to fix trailing commas before parsing.
    *   Loads `topic_mapping.json` into `st.session_state[TOPIC_MAPPING_STATE_KEY]` and `topics.json` into `st.session_state[TOPICS_JSON_STATE_KEY]` if not already loaded.
    *   `normalize_key(key_string)`: Helper function to normalize dictionary keys by stripping whitespace and lowercasing.
    *   `create_direct_topic_to_doc_details_mapping_cached(_topic_mapping_data, _topics_data)`:
        *   Cached function to create a mapping from normalized broad topics directly to a unique set of document details (doc_id, url, title).
        *   It iterates through `_topic_mapping_data` (broad topics to phrases) and uses `_topics_data` (phrases to document lists) to build this direct map.
        *   Keys and phrases are normalized using `normalize_key` for consistent matching.
        *   The result is stored in `st.session_state[TOPIC_DOC_MAP_KEY]`.

3.  **Sidebar UI**:
    *   **Reload Button**: A button "🔄 Reload" that clears cached functions (`load_json_from_path.clear()`, etc.) and removes relevant keys from `st.session_state`, then triggers a `st.rerun()` to reload all data.
    *   **Actions Header**:
        *   **Save Button**: If taxonomy data is loaded, a "💾 Save Updated Topic Map" button is shown. On click (implicitly, as `download_data` is called to check condition), it calls `download_data` to save the current `st.session_state[TOPIC_MAPPING_STATE_KEY]` to `topics/updated_topic_mapping_data.json`.
            *   `download_data(topic_data, filename)`: Serializes `topic_data` to a JSON formatted string and writes it to the specified `filename`. Ensures phrases within each topic are unique and sorted.
    *   **Modify Taxonomy Header (CRUD Operations for Topics and Phrases)**:
        *   These operations are available if `taxonomy_data_loaded` is true (i.e., `topic_mapping.json` was loaded).
        *   **Topic Operations (Expander)**:
            *   **Add New Topic**: Text input for new topic name; "Add Topic" button calls `add_topic_state`.
            *   **Rename Topic**: Selectbox for existing topic, text input for new name; "Rename Selected Topic" button calls `rename_topic_state`.
            *   **Delete Topic**: Selectbox for topic to delete; "Delete Selected Topic" button calls `delete_topic_state`. Warns that phrases will also be deleted.
        *   **Phrase Operations (Expander)**:
            *   **Add Phrase to Topic**: Selectbox for topic, text input for new phrase; "Add Phrase" button calls `add_phrase_state`.
            *   **Move Phrase**: Selectboxes/text input for source topic, phrase, and target topic; "Move Selected Phrase" button calls `move_phrase_state`. Allows creating a new target topic.
            *   **Delete Phrase from Topic**: Selectboxes for topic and phrase; "Delete Selected Phrase" button calls `delete_phrase_state`.
    *   **State Modification Functions (`add_topic_state`, `rename_topic_state`, etc.)**: These functions directly modify the `st.session_state[TOPIC_MAPPING_STATE_KEY]` dictionary and also update `st.session_state[MISMATCH_KEY]` if necessary (e.g., when renaming or deleting topics/phrases that were marked as mismatched). They typically end with `st.rerun()` to refresh the UI.

4.  **Mismatch Feedback Section (Expander)**:
    *   Allows viewing phrases marked as mismatched in the "Taxonomy Reviewer Tool".
    *   Displays a DataFrame of currently mismatched (topic, phrase) pairs.
    *   Provides a "Clear All Mismatch Flags" button to reset `st.session_state[MISMATCH_KEY]`.
    *   Includes logic to validate and clean up mismatches if corresponding topics/phrases no longer exist.

5.  **View Filters Header (Sidebar)**:
    *   Enabled if taxonomy data is loaded.
    *   **Document Finder Filter**: A selectbox `selected_topic_single` to choose a single topic for viewing its documents in the "Document Finder" tab. Stored in `st.session_state["doc_filter_topic"]`.
    *   **Graph Explorer Filter**: A multiselect `selected_topics_multi` to choose topics for visualization in the "Knowledge Graph Viewer" tab. Stored in `st.session_state["graph_filter_topics"]`.

6.  **Main Content Area (Tabs)**:
    *   `tab1, tab2, tab3 = st.tabs(["Knowledge Graph Viewer", "Document Finder", "Taxonomy Reviewer Tool"])`.

    *   **Tab 1: Knowledge Graph Viewer**:
        *   Attempts to get a Neo4j driver (`get_neo4j_driver()`, likely from `knowledge_graph.utils`).
        *   If Neo4j connection fails or is not configured, it may fall back to a basic topic graph based on selected filters (implementation of this fallback graph isn't fully detailed but might use `topic_mapping_data`).
        *   If topics are selected via `graph_filter_topics` in the sidebar:
            *   It's intended to `fetch_subgraph_data(driver, selected_topics_multi)` (presumably querying Neo4j) and then `generate_pyvis_html_from_neo4j_data(subgraph_data)` to create an HTML graph visualization.
            *   The HTML is rendered using `components.html(graph_html, height=750, scrolling=False)`.
        *   If no topics are selected, it prompts the user to select them.

    *   **Tab 2: Document Finder**:
        *   Relies on `full_data_loaded` (both `topic_mapping.json` and `topics.json` loaded).
        *   Uses `selected_topic_single` from the sidebar filter.
        *   If a topic is selected:
            *   Retrieves associated documents from `st.session_state[TOPIC_DOC_MAP_KEY]` (which was created by `create_direct_topic_to_doc_details_mapping_cached`) using the normalized selected topic key.
            *   Displays the documents (ID, Title, URL) in a Pandas DataFrame using `st.dataframe`. The URL is configured as a clickable link.
        *   If no topic selected or data not fully loaded, shows appropriate messages.

    *   **Tab 3: Taxonomy Reviewer Tool**:
        *   The primary interface for managing topic-phrase relationships from `topic_mapping.json`.
        *   Requires `topic_mapping_data` to be loaded.
        *   **Filtering**:
            *   Text input `topic_search_term` to filter the list of topics.
            *   Multiselect `selected_topics` to further refine which topics' phrases are displayed in the details table.
        *   **Display Layout (Columns)**:
            *   **Column 1 (Topic Summary)**:
                *   `get_topic_summary(topic_data)`: Creates a DataFrame with columns 'Topic' and 'Phrase Count'.
                *   Displays this summary DataFrame, filtered by `topics_to_display` (derived from search and multiselect filters).
            *   **Column 2 (Topic-Phrase Details)**:
                *   `get_dataframe(topic_data)`: Converts the topic dictionary (subset based on `topics_to_display`) into a long-format DataFrame with 'Topic', 'Phrase', and 'Mismatch' columns. The 'Mismatch' boolean is derived from `st.session_state[MISMATCH_KEY]`.
                *   Displays this detailed DataFrame using `st.data_editor`. This allows users to toggle the "Mismatch" checkbox for each phrase.
                *   **Mismatch Handling**: When the 'Mismatch' checkbox in `st.data_editor` is changed, the code compares the edited DataFrame with the original. If a mismatch status changes for a (Topic, Phrase) pair, `st.session_state[MISMATCH_KEY]` is updated accordingly, and `st.rerun()` is called to reflect the change immediately.
                *   The 'Topic' and 'Phrase' columns in the data editor are disabled to prevent direct editing here (CRUD operations are via sidebar).

**Outputs/Side Effects**:
*   A comprehensive Streamlit UI for exploring and managing topic taxonomies and related documents.
*   Modifies `st.session_state` to store loaded data, user selections, and UI state.
*   Can save updated topic mappings to `topics/updated_topic_mapping_data.json` if the save button is used.
*   Visualizes graphs using PyVis and NetworkX.
*   Interacts with (or is prepared to interact with) a Neo4j database for graph data.

---

### File: `create_vector_index.py`

**Purpose**: This script is responsible for defining and creating OpenSearch indexes, particularly the `PR_META_VECTOR_IDX` which is designed for k-NN (k-Nearest Neighbors) semantic search. It also includes a function to create generic metadata indexes.

**Key Dependencies/Inputs**:
*   `utils.opensearch.get_os_client` (to get an OpenSearch client instance)
*   Constants: `PR_META_RAW_IDX`, `PR_META_VECTOR_IDX` (names for OpenSearch indexes)

**Core Functionality (Step-by-Step)**:

1.  **Initialization**:
    *   Imports necessary constants and the OpenSearch client retrieval function.
    *   `client = get_os_client()`: Initializes the OpenSearch client connection.

2.  **`create_vector_index(index_name)` Function**:
    *   **Purpose**: Creates an OpenSearch index specifically configured for k-NN vector search.
    *   **Index Settings**:
        *   `"index.knn": True`: Enables the k-NN search functionality for this index at the index level.
    *   **Mappings Definition**: Defines the structure and data types for fields within the index:
        *   `embedding`:
            *   `type: "knn_vector"`: Specifies this field will store k-NN vectors.
            *   `dimension: 256`: Defines the dimensionality of the vectors. This must match the output dimension of the embedding model used (e.g., Amazon Titan model as commented).
            *   `method`: Configures the k-NN algorithm parameters:
                *   `name: "hnsw"`: Specifies HNSW (Hierarchical Navigable Small World) as the approximate k-NN algorithm.
                *   `space_type: "cosinesimil"`: Sets cosine similarity as the distance metric for comparing vectors.
                *   `engine: "nmslib"`: Specifies NMSLIB as the k-NN engine library. (Note: OpenSearch has other options like Faiss).
        *   Metadata Fields: Standard fields for document information:
            *   `pr_url`: `type: "keyword"` (for exact matching, faceting)
            *   `pr_title`: `type: "text"` (for full-text search)
            *   `summary`: `type: "text"`
            *   `pr_date`: `type: "date"`
            *   `pr_content`: `type: "text"`
        *   Enrichment Fields (Nested Objects):
            *   `entities`: `type: "nested"`
                *   `text`: `type: "text"` (the entity text)
                *   `label`: `type: "keyword"` (the entity type/label)
            *   `topics`: `type: "nested"`
                *   `text`: `type: "text"` (the topic text/name)
                *   `label`: `type: "keyword"` (the topic type/label, though often the text itself is the primary identifier)
    *   **Index Creation**:
        *   `client.indices.create(index=index_name, body=index_body)`: Sends the request to OpenSearch to create the index with the defined settings and mappings.
        *   Prints success or error messages.

3.  **`create_meta_index(index_name)` Function**:
    *   **Purpose**: Creates a simpler OpenSearch index, primarily for metadata or raw text storage, without k-NN specific settings in its definition.
    *   **Index Settings**:
        *   `"index": {"number_of_shards": 2}`: Example setting, configures the number of primary shards for the index.
    *   **Index Creation**:
        *   `client.indices.create(index_name, body=index_body)`: Creates the index.
        *   Prints success or error messages.

4.  **Main Execution Block (`if __name__ == "__main__":`)** (Implicitly, as this is how the script is structured to run when executed directly, though `if __name__ == "__main__":` is not explicitly in the snippet, the bottom part of the file acts like it):
    *   Checks if `PR_META_RAW_IDX` exists. If not, calls `create_meta_index(PR_META_RAW_IDX)` to create it. (Note: The script has this check duplicated).
    *   Checks if `PR_META_VECTOR_IDX` exists. If not, calls `create_vector_index(PR_META_VECTOR_IDX)` to create it. Includes a commented-out line for deleting the index if it exists, useful for development/resetting.

**Outputs/Side Effects**:
*   Creates OpenSearch indexes (`PR_META_RAW_IDX`, `PR_META_VECTOR_IDX`) with specified settings and mappings if they do not already exist.
*   Prints status messages to the console.

---

### File: `search_pipeline.py`

**Purpose**: This script provides a collection of functions that form the core pipeline for executing searches, processing queries, and refining search results. It includes capabilities like LLM-based query expansion, score normalization, and reranking of results using AWS Bedrock.

**Key Dependencies/Inputs**:
*   `json`, `logging`, `os`, `boto3`, `time`
*   `opensearchpy.exceptions.RequestError`
*   `.constants`: `BASE_MODEL_ID`, `CROSS_ENCODER_MODEL_NAME` (though `BEDROCK_RERANKER_MODEL_ARN` is used directly in `rerank_with_bedrock` and seems more relevant)
*   `.bedrock`: `engage_llm` (function to interact with a Bedrock LLM for tasks like query expansion)
*   `.opensearch`: `get_os_client` (to get an OpenSearch client instance)
*   `PR_META_VECTOR_IDX` (constant for the target OpenSearch index name, used in `execute_search`)
*   AWS SDK (Boto3) for Bedrock interaction.

**Core Functionality (Step-by-Step)**:

1.  **Initialization**:
    *   Sets up basic logging configuration.
    *   `client = get_os_client()`: Initializes the OpenSearch client.

2.  **`expand_query_with_llm(query: str)` Function**:
    *   **Purpose**: Uses a Large Language Model (LLM) via AWS Bedrock to generate alternative queries or relevant keywords based on the user's original query.
    *   **Prompt Engineering**: Constructs a specific prompt asking the LLM to generate 3-5 alternatives, focusing on phrasing variations and related policy/technical concepts. It instructs the LLM not to include the original query and to output each alternative on a new line without numbering.
    *   **LLM Interaction**: Calls `engage_llm(prompt)` (from `.bedrock` module) to get the LLM's response.
    *   **Response Processing**: Parses the LLM's newline-separated response, strips whitespace, and potentially removes prefixes (like " - ") from each generated alternative.
    *   **Output**: Returns a list containing the original query plus the valid alternatives generated by the LLM.

3.  **`normalize_scores_to_100(results: list)` Function**:
    *   **Purpose**: Normalizes the search scores from OpenSearch (or any other source) to a scale of 1 to 100 for more consistent and user-friendly display.
    *   **Input**: A list of result dictionaries, where each dictionary is expected to have a "score" key.
    *   **Score Handling**:
        *   Filters out results with invalid scores (non-numeric).
        *   If no valid scores are found, assigns a default normalized score of 1.0 to all results.
        *   Calculates the minimum and maximum scores from the valid scores.
        *   If `max_score == min_score` (all valid scores are the same), assigns 100.0 if the score is positive, else 1.0.
        *   Otherwise, applies min-max normalization: `normalized_val = 1 + ((score - min_score) / (max_score - min_score)) * 99`. This maps the original score range to a 1-100 range.
        *   Ensures the final normalized score is capped between 1.0 and 100.0.
    *   **Output**: Returns the input list of results with an added key `"normalized_score_100"` in each result dictionary.

4.  **`rerank_with_bedrock(query: str, documents: list, top_n: int = 10)` Function**:
    *   **Purpose**: Uses an AWS Bedrock reranking model to reorder a list of documents based on their relevance to a given query. This is typically used to improve the precision of the top N results from an initial retrieval stage.
    *   **AWS Bedrock Client**: Initializes a `bedrock-agent-runtime` Boto3 client.
    *   **Input Preparation**:
        *   Takes the original `query` and a `list` of `documents` (dictionaries) from the initial search.
        *   Extracts text from each document for reranking. It prioritizes `pr_title` and `pr_summary`, falling back to `pr_content`. Documents with no text are skipped.
        *   Maintains an `original_indices_map` to map the index of documents sent to Bedrock back to their original index in the input list.
    *   **Bedrock Rerank API Call**:
        *   Constructs a `rerank_request` dictionary containing:
            *   `queries`: The user's query.
            *   `sources`: The list of document texts to be reranked.
            *   `rerankingConfiguration`: Specifies the Bedrock reranking model ARN (`BEDROCK_RERANKER_MODEL_ARN`) and the desired `numberOfResults` (`top_n`).
        *   Calls `bedrock_agent_runtime_client.rerank(**rerank_request)`.
    *   **Response Processing**:
        *   Parses the Bedrock API response.
        *   For each result from Bedrock, it uses the `original_indices_map` to retrieve the full original document.
        *   Adds a `bedrock_relevance_score` (0-1 scale) from the Bedrock response to the document dictionary.
    *   **Error Handling**: Includes try-except blocks to catch `ClientError` from Boto3 and other exceptions during the reranking process, logging errors and returning the original top N documents as a fallback.
    *   **Output**: Returns a new list containing the top N reranked documents, each with the added `bedrock_relevance_score`.

5.  **`build_date_filter(start_date=None, end_date=None)` Function**:
    *   **Purpose**: Constructs a date range filter clause for OpenSearch queries.
    *   **Input**: Optional `start_date` and `end_date` (strings, presumably in 'YYYY-MM-DD' format).
    *   **Logic**: If either `start_date` or `end_date` is provided, it creates an OpenSearch `range` query object for the `pr_date` field, using `gte` (greater than or equal to) for `start_date` and `lte` (less than or equal to) for `end_date`.
    *   **Output**: Returns a list containing the date filter dictionary, or an empty list if no dates are provided. This list is intended to be used in the `filter` part of an OpenSearch boolean query.

6.  **`execute_search(query_body)` Function**:
    *   **Purpose**: Executes a given search query against the specified OpenSearch index (`PR_META_VECTOR_IDX`) and processes the hits.
    *   **Input**: `query_body` (a dictionary representing the OpenSearch query DSL).
    *   **OpenSearch Call**: Uses `client.search(index=PR_META_VECTOR_IDX, body=query_body)` to perform the search.
    *   **Results Extraction**:
        *   Iterates through `response["hits"]["hits"]`.
        *   For each hit, extracts the document from `_source` and the relevance score from `_score` (defaulting to 0.0 if not present).
        *   Appends the extracted document (with its score) to a `results` list.
        *   Logs warnings if a hit is missing the `_source` field.
    *   **Post-processing**: Calls `normalize_scores_to_100(results)` to add normalized scores to the results.
    *   **Error Handling**: Catches `RequestError` from OpenSearch and other exceptions, logs them, and returns an empty list in case of failure.
    *   **Output**: Returns a list of processed search result documents, each including raw and normalized scores.

**Outputs/Side Effects**:
*   Functions in this module interact with AWS Bedrock (for LLM tasks) and OpenSearch (for search execution).
*   Logs various stages of the search pipeline.
*   Modifies search results by adding normalized scores or reranking them.

---

### File: `search_service.py`

**Purpose**: This script defines various search functions that implement different search strategies (simple lexical, advanced semantic, hybrid, enhanced with LLM features). It constructs OpenSearch query bodies and utilizes `search_pipeline.py` to execute them and process results.

**Key Dependencies/Inputs**:
*   `json`, `boto3`, `logging`, `datetime.date`
*   `.constants`: Various constants (not explicitly detailed but implied by `*`)
*   `.opensearch.get_os_client`
*   `.search_pipeline`: `execute_search`, `build_date_filter`, `expand_query_with_llm`, `rerank_with_bedrock`, `normalize_scores_to_100`
*   `.bedrock.generate_embeddings` (function to get query embeddings)
*   OpenSearch client instance.

**Core Functionality (Step-by-Step)**:

1.  **Initialization**:
    *   Sets up logging.
    *   `client = get_os_client()`: Initializes the OpenSearch client.

2.  **Search Functions**: Each function typically takes a `query` string, `k` (number of results), `fuzziness`, `start_date`, and `end_date` as parameters.

    *   **`simple_search(...)`**:
        *   **Focus**: Lexical search targeting topics and entities with fuzziness.
        *   **Query Body**: Constructs an OpenSearch `bool` query with `should` clauses targeting nested `topics.text` and `entities.text` fields. Uses `match` (for fuzzy search) and `term` (for exact keyword match on `.keyword` subfield) queries.
        *   Includes date filtering using `build_date_filter`.
        *   `minimum_should_match: 1` ensures at least one clause matches.
        *   Calls `execute_search` with the constructed query body.

    *   **`advanced_search(...)`**:
        *   **Focus**: Combines lexical search with semantic vector search.
        *   **Query Embedding**: Calls `generate_embeddings(query)` to get the vector for the input query. If embedding generation fails, returns an empty list.
        *   **Query Body**:
            *   `bool` query with `should` clauses:
                *   `multi_match` on `pr_title^3` (boosted) and `summary^2` with fuzziness for lexical matching.
                *   `knn` semantic search clause on the `embedding` field, using the `query_embedding` and retrieving `k*3` initial candidates (to provide more items for potential reranking stages not explicit in this specific function but common in pipelines).
            *   Includes date filtering.
        *   Calls `execute_search`.

    *   **`pro_search(...)`**:
        *   **Focus**: Hybrid search leveraging OpenSearch's `hybrid` query type, combining lexical and semantic scores.
        *   **Query Embedding**: Generates query embedding. Returns empty if fails.
        *   **Query Body**:
            *   `hybrid` query with two sub-queries:
                *   **Lexical Sub-Query**: `bool` query with `should` clauses using `multi_match` on `pr_summary^2`, `pr_content^3`, and `match` queries on `pr_title`, `entities.text`, `topics.text`, all with fuzziness and boosting. Requires `minimum_should_match: 2`. Includes date filter.
                *   **Semantic Sub-Query**: `knn` search on `embedding` field, retrieving a larger number of candidates (`semantic_k = max(k * 5, 50)`).
            *   `size: k` for the final number of results.
        *   Calls `execute_search`.

    *   **`pro_search_enhanced(...)`**:
        *   **Focus**: Advanced hybrid search with optional LLM query expansion and Bedrock reranking.
        *   **Query Expansion (Optional)**: If `use_llm_expansion` is true, calls `expand_query_with_llm(query)` to get more search terms. The original query and expanded terms are combined and deduplicated.
        *   **Query Embedding**: Generates embedding for the *original* query.
        *   **Initial Retrieval Size**: `initial_retrieve_k` is set higher if `use_reranker` is true (`k * rerank_window_factor`) to provide more candidates to the reranker.
        *   **Query Body (`hybrid`)**:
            *   **Lexical Sub-Query**: `bool` query. Iterates through all `search_terms` (original + expanded). For each term, adds multiple `match` clauses for `pr_title`, `pr_content`, `pr_summary`, and nested `entities.text`, `topics.text`. The original query term gets a higher boost. Includes date filter. `minimum_should_match: 1`.
            *   **Semantic Sub-Query**: `knn` search using the `original_query_embedding`, retrieving `semantic_k` (derived from `initial_retrieve_k`) candidates.
        *   **Initial Retrieval**: Calls `execute_search` with `initial_retrieve_k`.
        *   **Reranking (Optional)**: If `use_reranker` is true, passes `initial_results` to `rerank_with_bedrock(query, initial_results, top_n=k)`.
        *   **Normalization**: If not reranking, normalizes scores of the top `k` initial results.
        *   Returns `final_results`.

    *   **`search_kb(...)`**: (Knowledge Base Search)
        *   **Focus**: Similar to `pro_search_enhanced` but potentially tuned for knowledge base style queries, including a relevance score threshold after reranking.
        *   **Query Expansion & Embedding**: Same as `pro_search_enhanced`.
        *   **Semantic K**: `semantic_k` is capped (e.g., `min(max(1, initial_retrieve_k), 10)`) perhaps for performance with dense KB data or specific embedding types.
        *   **Lexical Clauses**: Focuses on `pr_title`, `pr_content`, `pr_summary` for lexical matches.
        *   **Query Body & Initial Retrieval**: Similar hybrid structure to `pro_search_enhanced`.
        *   **Post-processing (Reranking/Normalization with Thresholding)**:
            *   If `use_reranker`: Calls `rerank_with_bedrock`. Then filters these reranked results to keep only those with `bedrock_relevance_score >= 0.60`.
            *   If not reranking: Normalizes scores of `pre_filtered_results`. Filters these to keep documents with `score >= 0.60` (note: this seems to use the raw OpenSearch score before normalization for thresholding, then sorts by `normalized_score_100` and takes top `k`).
        *   Returns `final_results_meeting_threshold`.

**Outputs/Side Effects**:
*   Executes various types of search queries against OpenSearch.
*   Interacts with AWS Bedrock for embeddings, query expansion, and reranking.
*   Returns lists of search result documents, processed according to the chosen search strategy.
*   Logs information about the search process.

---

### File: `utils.py` (from `utils/utils.py` context)

**Purpose**: This script appears to provide utility functions, primarily for rendering search results in a Streamlit application and initiating searches.

**Key Dependencies/Inputs**:
*   `streamlit` (st)
*   `datetime.date`
*   `.search_service`: `simple_search`, `advanced_search`, `pro_search`, `pro_search_enhanced` (search functions)
*   `time`

**Core Functionality (Step-by-Step)**:

1.  **Import necessary modules**: `streamlit`, date utilities, and search functions from `search_service`.

2.  **`render_document(doc: dict, show_content: bool = True)` Function**:
    *   **Purpose**: Formats and displays a single search result document within a Streamlit UI.
    *   **Input**: `doc` (a dictionary representing a search result document) and an optional `show_content` flag.
    *   **Display Logic**:
        *   Displays the document title (`doc.get('pr_title', 'Untitled')`) in bold.
        *   Defines `bubble_css` for styling entities/topics. This CSS is applied using `st.markdown(bubble_css, unsafe_allow_html=True)`.
        *   **Key Entities**: If `doc.get("entities")` exists, it writes a "**Key Entities:**" subheader. It then constructs an HTML string to display each entity text in a styled "bubble" (span with class `entity-bubble`). This HTML is rendered with `st.markdown`.
        *   **Key Topics**: Similar to entities, if `doc.get("topics")` exists, it displays them in styled bubbles.
        *   **Summary**: If `doc.get("summary")` exists, it displays it under a "**Summary:**" subheader.
        *   **URL**: Displays the document URL (`doc.get('pr_url')`) as a clickable link.
        *   **Date**: Displays the publication date (`doc.get('pr_date')`).
        *   **Score**: Displays the normalized score (`doc.get('normalized_score_100', 'N/A')`).
        *   **Content (Optional)**: If `show_content` is true and `doc.get("pr_content")` exists, it displays the full content within an expander (`st.expander("Show Content")`).

3.  **Search Execution Helper Functions (Example Structure - not fully shown but inferred from imports)**:
    *   The script imports various search functions (`simple_search`, `advanced_search`, etc.) from `search_service.py`.
    *   It's common for such `utils.py` files in Streamlit apps to wrap these search calls, perhaps handling UI elements for query input, date pickers, and then calling `render_document` for each result.
    *   Example (hypothetical based on typical usage):
        ```python
        # query = st.text_input("Enter your search query:")
        # start_date = st.date_input("Start date")
        # end_date = st.date_input("End date")
        # if st.button("Search"):
        #     results = pro_search_enhanced(query, start_date=str(start_date), end_date=str(end_date))
        #     if results:
        #         st.write(f"Found {len(results)} documents:")
        #         for res in results:
        #             render_document(res)
        #     else:
        #         st.write("No results found.")
        ```

**Outputs/Side Effects**:
*   Provides a standardized way to render document details in the Streamlit UI.
*   Likely facilitates the connection between the search UI components and the backend search services.

---

### File: `knowledge_graph.py` (from `knowledge_graph/knowledge_graph.py`)

**Purpose**: This script is dedicated to managing a Neo4j knowledge graph. It handles connecting to the Neo4j database, cleaning existing data, creating schema constraints, and loading data from JSON files (`topic_mapping.json`, `topics.json`) to build a graph of topics and their related documents.

**Key Dependencies/Inputs**:
*   `json`, `os`, `re`, `logging`, `time`
*   `collections.defaultdict`
*   `neo4j.GraphDatabase`, `neo4j.unit_of_work`
*   `utils.constants` (specifically `credentials` dictionary for Neo4j URI, username, password)
*   Input JSON files: `topic_mapping.json`, `topics.json` (expected in a `topics` subdirectory relative to the script's parent directory).

**Core Functionality (Step-by-Step)**:

1.  **Initialization and Configuration**:
    *   Sets up logging.
    *   Retrieves Neo4j connection details (`NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`) from `utils.constants.credentials`. Exits if not found.

2.  **JSON Data Loading (`read_topics_json`, `load_json_safe`)**:
    *   `read_topics_json(filename)`: Constructs the full path to the JSON file (e.g., `../topics/filename`) and reads its content.
    *   `load_json_safe(filepath)`: A wrapper around `read_topics_json` that parses the JSON content. It includes error handling for `JSONDecodeError`, invalid structure (expects a dictionary), and other exceptions. Logs success or errors.

3.  **Key Normalization (`normalize_key`)**:
    *   `normalize_key(key_string)`: Converts a key to string, strips leading/trailing whitespace, and converts to lowercase. Used for consistent matching of topic and phrase names.

4.  **Neo4j Database Management**:
    *   **`cleanup_neo4j_database(tx, batch_size=10000)`**:
        *   A `@unit_of_work` transactional function to delete all nodes and relationships from the database in batches to avoid memory issues with large datasets.
        *   It repeatedly executes `MATCH (n) WITH n LIMIT $batch_size DETACH DELETE n RETURN count(n)` until no more nodes are deleted.
        *   Logs progress and total deleted count.
        *   **Important**: This function *does not* delete constraints or indexes.
    *   **Constraint Dropping (Part of cleanup logic in `__main__`)**: Before loading new data (if full reset is chosen), the script iterates through existing constraints (shown by `SHOW CONSTRAINTS YIELD name`) and drops them using `DROP CONSTRAINT $name IF EXISTS`. This is separate from `cleanup_neo4j_database`.
    *   **`create_constraints(tx)`**:
        *   A transactional function to create uniqueness constraints on Neo4j node properties if they don't already exist.
        *   `CREATE CONSTRAINT topic_name_unique IF NOT EXISTS FOR (n:BroadTopic) REQUIRE n.name IS UNIQUE;`
        *   `CREATE CONSTRAINT doc_id_unique IF NOT EXISTS FOR (n:Document) REQUIRE n.docId IS UNIQUE;`

5.  **Data Loading into Neo4j (`_create_direct_topic_doc_link_tx`, `load_data_to_neo4j_direct`)**:
    *   **`_create_direct_topic_doc_link_tx(tx, broad_topic_name_norm, doc_id_str, url, title)`**:
        *   A transactional function that performs the core Cypher query to link a broad topic to a document.
        *   `MERGE (bt:BroadTopic {name: $topic_name})`: Creates or matches a `BroadTopic` node.
        *   `MERGE (d:Document {docId: $doc_id})`: Creates or matches a `Document` node.
        *   `ON CREATE SET d.url = $url, d.title = $title, d.firstSeen = timestamp()`: Sets properties if the document node is newly created.
        *   `ON MATCH SET d.url = $url, d.title = $title, d.lastSeen = timestamp()`: Updates properties if the document node already exists.
        *   `MERGE (bt)-[:RELATES_TO_DOC]->(d)`: Creates or matches a `RELATES_TO_DOC` relationship from the topic to the document.
    *   **`load_data_to_neo4j_direct(driver, topic_mapping_data, topics_data)`**:
        *   Orchestrates the data loading process.
        *   Normalizes keys in `topic_mapping_data` and `topics_data` using `normalize_key`.
        *   Calls `session.execute_write(create_constraints)` to ensure schema constraints are in place.
        *   Iterates through each normalized broad topic (`broad_topic_norm`) and its list of phrases from `normalized_topic_mapping`.
        *   For each phrase, it normalizes the phrase (`phrase_norm`) and looks it up in `normalized_topics` to get the list of associated document entries.
        *   For each document entry (expected to be a dict like `{doc_id: {url: ..., title: ...}}`):
            *   Extracts `doc_id`, `url`, and `title`.
            *   Calls `session.execute_write(_create_direct_topic_doc_link_tx, ...)` to create the nodes and relationship in Neo4j.
            *   Keeps track of `processed_docs_for_topic` to avoid creating duplicate relationships for the same document under the same broad topic within a single run.
        *   Includes logging for progress, skipped items due to format issues, and errors during transaction execution.

6.  **Main Execution Block (`if __name__ == "__main__":`)**:
    *   Connects to Neo4j using `GraphDatabase.driver(...)` and verifies connectivity.
    *   **Database Cleanup**: Prompts the user with a warning: "WARNING: This will delete ALL nodes and relationships from the database. Proceed? (yes/no):".
        *   If "yes", it first drops all existing constraints, then calls `session.execute_write(cleanup_neo4j_database)` to delete data.
    *   **Data Loading**:
        *   Loads `topic_mapping.json` and `topics.json` using `load_json_safe`.
        *   Calls `load_data_to_neo4j_direct` to populate Neo4j with the data from the JSON files.
    *   Logs timing for cleanup and data loading.
    *   Ensures the Neo4j driver is closed in a `finally` block.

**Outputs/Side Effects**:
*   Modifies the Neo4j database:
    *   Potentially deletes all existing data and constraints.
    *   Creates new constraints.
    *   Creates `:BroadTopic` nodes, `:Document` nodes.
    *   Creates `[:RELATES_TO_DOC]` relationships between them.
*   Loads data from `topic_mapping.json` and `topics.json`.
*   Extensive logging to the console about the process.

---

### File: `pr_meta_fetch.py`

**Purpose**: This script is designed to scrape press release metadata (URLs, titles, and dates) from the "larson.house.gov" website and save this information to a local JSON file.

**Key Dependencies/Inputs**:
*   `requests` (for HTTP requests)
*   `bs4` (BeautifulSoup, for HTML parsing)
*   `concurrent.futures` (for parallel fetching of links)
*   `os`, `json`, `datetime`

**Core Functionality (Step-by-Step)**:

1.  **Helper Function `writeToJSONFile(path, fileName, data)`**:
    *   Takes a directory `path`, `fileName` (without extension), and `data` (Python list/dict).
    *   Ensures the directory `path` exists, creating it if necessary.
    *   Constructs the full file path with a `.json` extension.
    *   Writes the `data` to the JSON file with an indent of 4 for readability using `json.dump()`.

2.  **`fetch_links(url)` Function**:
    *   **Purpose**: Fetches all press release links from a single paginated page of the website.
    *   `root_path = "https://larson.house.gov"`: Defines the base URL for constructing full links.
    *   Sends an HTTP GET request to the given `url` (e.g., a specific page of press release listings).
    *   Parses the HTML response using BeautifulSoup.
    *   Finds all `` tags where the `href` attribute starts with `/media-center/press-releases/`.
    *   Constructs the absolute URL for each found link and adds it to a `linkset` (to ensure uniqueness).
    *   Includes error handling for request exceptions.
    *   Returns a list of unique press release URLs found on that page.

3.  **`fetch_press_release_info(url)` Function**:
    *   **Purpose**: Fetches detailed information (title and date) for a single press release URL.
    *   Sends an HTTP GET request to the individual press release `url`.
    *   Parses the HTML response.
    *   Extracts the title: Finds the `` tag and gets its text.
    *   Extracts the date: Locates a specific `` structure (`div.page__content evo-page-content` -> `div.col-auto`) expected to contain the date string.
    *   Date Formatting: Attempts to parse the extracted date string (e.g., "Month DD, YYYY") into a `datetime` object and then reformats it to "YYYY-MM-DD" format. If parsing fails, uses the original date string.
    *   Includes error handling.
    *   Returns a dictionary `{"pr_url": url, "pr_title": title, "pr_date": date}` or `None` on error.

4.  **`fetch_all_links(base_url, max_pages=326)` Function**:
    *   **Purpose**: Orchestrates fetching links from all specified pages concurrently.
    *   `base_url`: The base URL for press release listings (without the page query parameter).
    *   `max_pages`: The maximum number of pages to attempt to scrape.
    *   Uses `concurrent.futures.ThreadPoolExecutor` to make requests to multiple pages in parallel (up to 10 workers).
    *   Submits `fetch_links` tasks for each page number from 1 to `max_pages` (e.g., `f"{base_url}?page={page}"`).
    *   As futures complete, extends `all_links` with the results. If a page fetch returns no links (or an error leads to empty result), it can `break` early (though the current logic adds to `all_links` and continues processing other futures).
    *   Returns a flat list of all unique press release URLs gathered from all pages.

5.  **Main Execution Block (`if __name__ == "__main__":`)**:
    *   Sets `base_url = "https://larson.house.gov/media-center/press-releases"`.
    *   Calls `fetch_all_links(base_url)` to get all press release URLs.
    *   Initializes an empty list `data`.
    *   If links were found:
        *   Iterates through each `link` in `all_links`.
        *   Calls `fetch_press_release_info(link)` to get the title and date for that link.
        *   If `info` is successfully retrieved, appends it to the `data` list.
        *   After processing all links, calls `writeToJSONFile("./", "press_releases", data)` to save the collected data to `./press_releases.json`.
    *   Prints status messages to the console.

**Outputs/Side Effects**:
*   Creates/overwrites a JSON file named `press_releases.json` in the current directory, containing a list of dictionaries, where each dictionary holds the `pr_url`, `pr_title`, and `pr_date` for a press release.
*   Makes numerous HTTP requests to "larson.house.gov".
*   Prints progress and error messages to the console.

---

### File: `pr_meta_store.py`

**Purpose**: This script processes press release entries that have been initially logged (e.g., by `pr_meta_store_from_local.py` into `PR_META_URL_IDX`). For each unprocessed entry, it fetches the full press release content from the web, cleans it, and stores it along with metadata into a "raw" OpenSearch index (`PR_META_RAW_IDX`). It then marks the entry as processed in the original index.

**Key Dependencies/Inputs**:
*   `opensearchpy.helpers` (for bulk operations)
*   `boto3` (though not directly used in snippet, implies AWS environment for OpenSearch usually)
*   `datetime`, `requests`, `bs4`, `re`, `time`
*   `utils.opensearch`: `OS_CLIENT` (OpenSearch client), `PR_META_RAW_IDX`, `PR_META_URL_IDX` (index names)

**Core Functionality (Step-by-Step)**:

1.  **Initialization**:
    *   `client = OS_CLIENT`: Gets the OpenSearch client instance.
    *   `region = "us-east-1"`: Defines AWS region, usually for Boto3 services.

2.  **Index Management Helper Functions**:
    *   `check_index_exists(index_name)`: Checks if an OpenSearch index exists.
    *   `create_index(index_name)`: Creates a basic OpenSearch index with 2 shards (if it doesn't exist).

3.  **Text Cleaning (`clean_text(text)`)**:
    *   Removes characters that are not alphanumeric or whitespace using `re.sub(r"[^a-zA-Z0-9\s]", "", text)`.
    *   Replaces multiple whitespace characters with a single space and strips leading/trailing whitespace.

4.  **Content Fetching (`fetch_press_release_info(url)`)**:
    *   **Purpose**: Fetches and extracts the main textual content of a press release from its URL.
    *   Sends an HTTP GET request to the `url`.
    *   Parses the HTML response using BeautifulSoup.
    *   Extracts the title (though not returned by this function, the parsing logic for it is present: `soup.find("h1").text.strip()`).
    *   Extracts the main body content: Locates a specific `div` (`class_="evo-press-release__body"`) and gets its text.
    *   Calls `clean_text()` on the extracted content.
    *   Returns the cleaned content string or `None` on error.

5.  **Searching for Unprocessed Entries**:
    *   `search_unprocessed_entries(index_name=PR_META_URL_IDX)`: Searches `PR_META_URL_IDX` for up to 10,000 entries where `processed: false`.
    *   `search_unprocessed_entries_by_date(year=None, month=None, index_name=PR_META_URL_IDX)`:
        *   Similar to `search_unprocessed_entries` but adds a date range filter to the query if `year` (and optionally `month`) is provided.
        *   This allows processing entries in chronological batches.

6.  **Storing Data and Updating Flags**:
    *   `store_in_opensearch(identifier, data, index_name)`: (Note: This function seems less used in the main flow compared to bulk operations. The main flow uses `helpers.bulk`.) Indexes a single document `data` into `index_name` with the given `identifier` as the document ID. Adds an `id` field to the `data` object itself.
    *   `update_processed_flag(identifier, index_name=PR_META_URL_IDX)`: Updates a single document in `index_name` with `id=identifier` to set `processed: true`.
    *   `bulk_update_processed_flags(ids, index_name=PR_META_URL_IDX)`:
        *   Takes a list of document `ids`.
        *   Constructs a list of bulk update actions, each specifying `_op_type: "update"`, `_index`, `_id`, and the update `doc: {"processed": True}`.
        *   Uses `opensearchpy.helpers.bulk(client, bulk_actions, stats_only=True)` to perform the updates efficiently.
        *   Prints success/failure statistics for the bulk operation.

7.  **Main Processing Logic**:
    *   **`process_skipped_entries()`**:
        *   Calls `search_unprocessed_entries()` to find any entries that might have been missed by the date-batched processing.
        *   Iterates through these entries. For each entry:
            *   Extracts `pr_id` (OpenSearch document ID), `pr_url`, `pr_date`, `pr_title`.
            *   Calls `fetch_press_release_info(pr_url)` to get the full content.
            *   If content is fetched successfully, prepares `raw_data` for `PR_META_RAW_IDX`.
            *   Adds an action to `bulk_raw_actions` for indexing this `raw_data` into `PR_META_RAW_IDX` with `_id = pr_id`.
            *   Adds `pr_id` to `processed_ids` list.
        *   After iterating, if `bulk_raw_actions` is not empty, performs a bulk insert into `PR_META_RAW_IDX`.
        *   If the bulk insert is successful (at least one document succeeded), calls `bulk_update_processed_flags(processed_ids)` to mark these entries as processed in `PR_META_URL_IDX`.
    *   **`process_entries()`**:
        *   The main processing loop, iterating by year and month.
        *   Defines `ym_tuple` for years 2000-2024 and months 1-12.
        *   Checks if `PR_META_RAW_IDX` exists, creates it if not.
        *   For each `(year, month)`:
            *   Calls `search_unprocessed_entries_by_date(year=year, month=month)`.
            *   The rest of the logic within the loop is identical to `process_skipped_entries()`: fetch content, prepare bulk actions for `PR_META_RAW_IDX`, perform bulk insert, and if successful, bulk update processed flags in `PR_META_URL_IDX`.
            *   Prints progress messages for each year-month batch.
    *   **Script Execution Order**: When run directly, `process_entries()` is called first, followed by `process_skipped_entries()` to catch any remaining items. Finally, the OpenSearch client connection is closed.

**Outputs/Side Effects**:
*   Reads from `PR_META_URL_IDX` in OpenSearch.
*   Writes new documents (full press release content and metadata) to `PR_META_RAW_IDX` in OpenSearch.
*   Updates documents in `PR_META_URL_IDX` by setting the `processed` flag to `true`.
*   Makes HTTP requests to fetch press release content.
*   Prints detailed logs and progress to the console.

---

### File: `pr_meta_store_from_local.py`

**Purpose**: This script reads press release metadata from a local JSON file (presumably created by `pr_meta_fetch.py`), adds a "processed" flag to each entry, and stores these entries into an OpenSearch index (`PR_META_URL_IDX`). It assigns an auto-incrementing ID to each new entry in OpenSearch.

**Key Dependencies/Inputs**:
*   `json`, `os`, `boto3`, `datetime`, `time`
*   `opensearchpy.OpenSearch`, `RequestsHttpConnection`, `AWSV4SignerAuth` (though client is obtained via `OS_CLIENT`)
*   `utils.opensearch.OS_CLIENT`, `PR_META_URL_IDX`
*   Input JSON file: `press_releases.json` (hardcoded in `__main__`).

**Core Functionality (Step-by-Step)**:

1.  **Initialization**:
    *   `client = OS_CLIENT`: Gets the OpenSearch client instance.
    *   `PR_META_URL_IDX` constant is defined/imported.

2.  **`add_processed_flag(data)` Function**:
    *   Takes a list of press release `data` (dictionaries).
    *   Iterates through each `entry` in the list and adds a new key-value pair: `entry["processed"] = False`.
    *   Returns the modified list of data.

3.  **`store_in_opensearch(data, index_name=PR_META_URL_IDX)` Function**:
    *   **Purpose**: Stores a list of data entries into the specified OpenSearch index, assigning auto-incrementing IDs.
    *   **Get Next ID**:
        *   Attempts to find the last (highest) existing `id` in the `index_name` by searching for one document sorted by `id` in descending order.
        *   If a last ID is found, `next_id` is set to `last_id + 1`.
        *   If the index is empty or an error occurs, `next_id` defaults to 1.
        *   Includes a `time.sleep(3)` which might be a crude way to wait for index consistency, though not generally recommended.
    *   **Store Entries**:
        *   Iterates through each `entry` in the input `data` list.
        *   Assigns the current `next_id` to `entry["id"]`.
        *   Uses `client.index(index=index_name, id=next_id, body=entry)` to store the entry in OpenSearch, using `next_id` as the document's `_id`.
        *   Prints a success message with the stored ID or an error message if storage fails.
        *   Increments `next_id` for the next entry.

4.  **`process_json_file(file_path, index_name=PR_META_URL_IDX)` Function**:
    *   Checks if the `file_path` exists; returns if not.
    *   Opens and reads the JSON `file_path` using `json.load()`.
    *   Calls `add_processed_flag(data)` to add the `processed: false` field to each entry.
    *   Calls `store_in_opensearch(updated_data, index_name)` to store the modified data into OpenSearch.

5.  **Main Execution Block (`if __name__ == "__main__":`)**:
    *   Sets `file_path = "press_releases.json"`.
    *   Defines a basic `index_body` for index settings (number of shards).
    *   Attempts to create the `PR_META_URL_IDX` using `client.indices.create(PR_META_URL_IDX, body=index_body)`. Includes basic error handling if index creation fails (e.g., if it already exists).
    *   Calls `process_json_file(file_path)` to process and store the data from the specified JSON file.

**Outputs/Side Effects**:
*   Reads data from `press_releases.json`.
*   Potentially creates the `PR_META_URL_IDX` in OpenSearch if it doesn't exist.
*   Stores new documents (with an added `processed: false` flag and an auto-incremented `id`) into `PR_META_URL_IDX`.
*   Prints status and error messages to the console.