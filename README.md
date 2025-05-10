# Problem Context
* Congressman Larson's office seeks to design a system architecture for processing and organizing digital documents to enable intelligent indexing and search by keyword and topic. 
* Traditional document management approaches lack the sophistication to meet the evolving information needs of the Congressman, his staff, and constituents. 
* This project aims to augment those approaches by incorporating natural language processing (NLP) techniques for intelligent records management. 

---
# Solution Proposal

### A Semantic Document Processing and Intelligent Search System

In today’s digital world, organizations often have vast amounts of documents—emails, reports, memos, scanned files—scattered across different locations and formats. Searching through them to find the right information can be like finding a needle in a haystack. Congressman Larson's office, like many others, faces this challenge and is seeking a smarter way to manage and access important documents.

Our solution is to build an **intelligent document processing system**. 

This system won’t just store files—it will understand them. By using natural language processing (NLP), we can automatically read documents, tag them with meaningful topics, and make them easily searchable by keyword, theme, or even people and places mentioned. Think of it as giving the Congressman's office a digital assistant that can read and organize files intelligently.

This document explains the inner workings of the Semantic Document Processing and Intelligent Search System. It describes how the system collects, understands, organizes, and retrieves information from press releases, using straightforward language to make the process clear. The aim is to provide a detailed guide for anyone who might work on or use this system in the future.

## Architecture Diagram
![Alt text](./diagram/architecture_diagram.svg)
---

## I. Gathering the Raw Materials: Collecting and Storing Press Releases

The first job of the system is to gather all the press release documents. This is like collecting all the books and papers needed for a research project. This process happens in a few automated steps:

**A. Initial Collection: Fetching Basic Information (URLs, Titles, Dates)**
The system needs to know where to find each press release and some basic details about it.

*   **How it works (`pr_meta_fetch.py` script)**:
    1.  This script automatically visits the "larson.house.gov" website.
    2.  It looks through all the pages listing press releases to find the web address (URL) for each one.
    3.  For every press release URL it finds, it also collects the title and the date it was published.
    4.  All this basic information (URL, title, date) for every press release is saved into a computer file named `press_releases.json` on the local system.

**B. Preparing for Full Content Retrieval: Staging Basic Information**
Before fetching the full text, this basic information is organized and stored in a preliminary database.

*   **How it works (`pr_meta_store_from_local.py` script)**:
    1.  This script takes the `press_releases.json` file (created in the previous step).
    2.  It reads each press release entry from this file.
    3.  For each entry, it adds a note: `"processed": false`. This note means the system hasn't yet fetched the full content of this press release.
    4.  It then saves these entries, each with a unique ID number, into a special section (an "index" called `PR_META_URL_IDX`) within the OpenSearch database. This section acts like a to-do list for fetching the full content.

**C. Getting the Full Story: Fetching and Storing Complete Press Release Content**
Now the system goes back to get the full text of each press release.

*   **How it works (`pr_meta_store.py` script)**:
    1.  This script looks at the to-do list (`PR_META_URL_IDX`) and finds entries marked as `"processed": false`. It often does this in batches, for example, by year and month, to handle a large number of documents efficiently.
    2.  For each press release on the to-do list, it uses the saved URL to visit the webpage.
    3.  It then carefully extracts all the text from the press release.
    4.  This extracted text is cleaned up (for instance, by removing unusual characters or extra spaces).
    5.  The clean text, along with the URL, title, and date, is saved in another section (an index called `PR_META_RAW_IDX`) of the OpenSearch database. It uses the same unique ID as before to keep things consistent.
    6.  Once the full content is successfully saved, the script updates the to-do list (`PR_META_URL_IDX`) by changing the note for that press release to `"processed": true`. This is often done for many documents at once for speed.
    7.  The script also has a way to check for and process any entries that might have been missed in earlier runs.

**D. The First Storage Bins: Raw Data Organization**
At this stage, the collected information is stored in specific places within the OpenSearch database:
*   **`PR_META_URL_IDX`**: This index holds the initial list of press release web addresses, titles, dates, and a flag indicating whether their full content has been fetched. It's primarily a temporary holding area.
*   **`PR_META_RAW_IDX`**: This index stores the complete, cleaned text of each press release, along with its basic details (title, URL, date). This is the main source of content for the next stage of understanding.

## II. Deeply Understanding Each Document: Extracting Meaning with AI

Simply storing the text isn't enough; the system needs to understand what each document is about. This is where Artificial Intelligence (AI) helps extract deeper meaning.

**A. The Goal: Going Beyond Keywords**
The system aims to understand the topics, key entities (like people or organizations), and the overall message of each document, not just match keywords.

**B. The Process: How Documents are Analyzed (Implied Document Processing Pipeline)**
Although not detailed in a single script, a dedicated process (likely using Python and AWS services) handles this:
1.  **Reading from Raw Storage**: The system takes the cleaned text of press releases from the `PR_META_RAW_IDX` storage.
2.  **Further Text Cleaning (Preprocessing)**: The text is prepared for AI analysis. This might involve breaking down large documents into smaller, more manageable pieces if needed.
3.  **Identifying Key Information (using AWS Bedrock - e.g., Cohere models)**:
    *   **Named Entities**: AI models identify and categorize important names mentioned, such as people, organizations, locations, and dates.
    *   **Main Topics**: The system figures out the main subjects or themes discussed in each document.
    *   **Short Summaries**: A brief summary (e.g., two lines) of each document is automatically generated to give a quick idea of its content.
4.  **Creating "Meaning Fingerprints" (Embeddings using AWS Bedrock - e.g., Titan Text Embeddings model)**:
    *   This is a crucial step. The system converts the text of each document (or its meaningful chunks) into a special numerical code. This code is like a "fingerprint" that represents the semantic meaning of the text.
    *   Documents that talk about similar concepts will have similar "meaning fingerprints," even if they use different words. These fingerprints are essential for smart searching.

**C. Refining Knowledge: Topic Modeling and Human Input**
To make the system's understanding of topics even better:
*   **Topic Modeling**: The system can group documents by common themes.
*   **Human Review**: A special interface (the "Human in the Loop Streamlit UI" mentioned in the architecture) allows people to review and adjust the topics identified by the AI, ensuring accuracy and relevance. This helps fine-tune how documents are categorized.

## III. Organizing for Super-Smart Retrieval: Building the Searchable Knowledge Base

Once documents are understood, their meaning and key information need to be stored in a way that makes searching fast and intelligent.

**A. Storing Enriched Data for Fast Search**
The insights gained from the AI analysis (summaries, entities, topics, and "meaning fingerprints") are stored in a specialized database index.

*   **The Enriched Data Hub (`PR_META_VECTOR_IDX`)**: This is a central storage area in OpenSearch designed for advanced searching.
    *   **Setup (`create_vector_index.py` script)**: This script sets up the `PR_META_VECTOR_IDX`. It defines how the data will be structured, including:
        *   A special field for the "meaning fingerprints" (embeddings), configured for fast similarity searches (k-Nearest Neighbor or k-NN search). It specifies the size of these fingerprints (e.g., 256 numbers from an Amazon Titan model) and how they should be compared (e.g., using cosine similarity).
        *   Fields for standard details like URL, title, summary, date, and the full content.
        *   Structured fields to store the lists of identified entities (text and type) and topics (text and type).
    *   **Content**: This index is populated with the "meaning fingerprints," metadata, extracted entities, and topics for each document, making it ready for complex search queries.

**B. Building a Network of Knowledge: The Knowledge Graph**
Beyond storing individual document details, the system also builds a map of how topics and documents are connected.

*   **Purpose**: The knowledge graph (stored in a Neo4j database) helps users explore relationships between different subjects and see which documents relate to specific broad topics. This provides a deeper, more contextual understanding.
*   **Data Sources**:
    *   `topics/topic_mapping.json`: This file defines broad topics and lists more specific key phrases associated with each.
    *   `topics/topics.json`: This file links those specific key phrases to actual documents (providing document ID, URL, and title).
*   **Construction (`knowledge_graph.py` script)**: This script takes the information from the JSON files and builds the graph in Neo4j:
    1.  **Database Setup**: It connects to the Neo4j database. It can clean up old data and relationships if needed and sets up rules (constraints) to ensure data integrity (e.g., topic names and document IDs are unique).
    2.  **Creating Nodes (Information Points)**:
        *   For each broad topic (from `topic_mapping.json`), it creates a "BroadTopic" point in the graph.
        *   For each document (referenced in `topics.json`), it creates a "Document" point, storing its ID, URL, and title.
    3.  **Creating Relationships (Connections)**: It then connects these points. For every broad topic, it looks at its associated phrases, finds the documents linked to those phrases (from `topics.json`), and creates a "RELATES_TO_DOC" connection between the "BroadTopic" point and each relevant "Document" point.
*   **Managing and Exploring Topic Connections (`explorer_app.py` Streamlit application)**:
    *   **"Taxonomy Reviewer Tool" Tab**: This part of the user interface allows people to look at, edit, and manage the topic-to-phrase mappings in the `topic_mapping.json` file. Changes made here can be saved and used to update the knowledge graph.
    *   **"Knowledge Graph Viewer" Tab**: This tool lets users select topics and see a visual map of how they connect to documents and potentially other topics in the Neo4j graph.

## IV. Searching with Your Words: How the System Processes Your Queries

This part covers how users interact with the system to find information and how the system handles those search requests.

**A. Your Window to the System: The User Interface (Built with Streamlit)**
Users interact with the system through web-based applications.

*   **Main Interface (`main_app.py` script)**: This script sets up the basic framework for the user application. As per the architecture, this could be a "Chat Interface" where users type their questions.
*   **Exploration Tools (`explorer_app.py` script - "Proximity Exploration Tool")**: This application provides more specialized ways to explore information:
    *   It allows users to visually explore the knowledge graph (as mentioned above).
    *   The "Document Finder" tab lets users pick a broad topic and see a list of all documents related to it.
    *   It also includes the "Taxonomy Reviewer Tool" for managing topic definitions.

**B. Behind the Scenes: The Search Engine at Work**
When a user submits a search query, several things happen in the background.

1.  **Understanding Your Query**:
    *   **Generating Query "Meaning Fingerprints" (`search_service.py` using AWS Bedrock)**: Just like documents, the user's search query (whether a few keywords or a full question) is converted into its own "meaning fingerprint" (embedding) using the same AI model (e.g., Amazon Titan).
    *   **Optional: Expanding Your Query with AI (`search_pipeline.py` - `expand_query_with_llm` function)**: To help find more relevant results, the system can use another AI model (e.g., Cohere Command R1 via Bedrock) to suggest alternative ways of phrasing the query or related concepts. These expanded terms can be added to the search.
2.  **Choosing How to Search: Different Strategies (`search_service.py` script)**: The system can use several methods to find documents, depending on the need:
    *   **Simple Keyword Search (`simple_search`)**: Looks for exact or similar words in the topics and entities of documents.
    *   **Advanced Semantic Search (`advanced_search`)**: Combines keyword matching (in titles and summaries) with searching for similar "meaning fingerprints."
    *   **Hybrid Approaches (`pro_search`)**: Blends scores from both keyword matches (across various fields like title, content, summary, entities, topics) and "meaning fingerprint" similarity.
    *   **Enhanced Hybrid Search (`pro_search_enhanced`, `search_kb`)**: A more advanced hybrid search that can also use the AI-powered query expansion and AI-powered result reordering (reranking) for even better accuracy.
3.  **Building the Search Plan: Constructing OpenSearch Queries (`search_service.py` script)**: Based on the chosen strategy and the user's input (including any date filters set via `build_date_filter` from `search_pipeline.py`), this script creates a detailed query instruction for the OpenSearch database. This instruction tells OpenSearch exactly what to look for and how.
4.  **Executing the Search: Fetching Initial Results (`search_pipeline.py` - `execute_search` function)**: The detailed query instruction is sent to OpenSearch, which then searches through the `PR_META_VECTOR_IDX` (the enriched data hub) and returns an initial list of matching documents.

## V. Finding and Presenting the Best Matches: Delivering Results

After the initial search, the system works to refine and clearly present the findings.

**A. Refining the Results for Accuracy**
To ensure the most relevant documents appear at the top:
1.  **Optional: AI-Powered Reranking (`search_pipeline.py` - `rerank_with_bedrock` function)**: The initial list of results can be passed to another AI model (an AWS Bedrock reranking model). This model re-evaluates the documents against the original query and reorders them based on a more nuanced understanding of relevance, pushing the best matches higher up.
2.  **Making Scores Understandable: Score Normalization (`search_pipeline.py` - `normalize_scores_to_100` function)**: Search results often come with technical relevance scores. This function converts these scores into a simple 1-100 scale, making it easier for users to see how relevant each document is.

**B. Displaying the Information Clearly**
The final, refined list of documents is then shown to the user in the application.
*   **How Results are Shown (`utils.py` script - `render_document` function within the Streamlit UI)**: This utility provides a consistent way to display each found document. It typically shows:
    *   The document's title.
    *   Key entities and topics found in it (often highlighted).
    *   The AI-generated summary.
    *   A link to the original document (URL).
    *   The publication date.
    *   The easy-to-understand relevance score.
    *   Optionally, the full content of the press release can be shown if the user wants to see it.

## VI. System Governance (Conceptual)

This area focuses on ensuring the system is used securely and that data is handled appropriately.

**A. Managing Access and Security**
*   **Current State**:
    *   Access to databases (like Neo4j and OpenSearch) and AI services (AWS Bedrock) is controlled by credentials (usernames, passwords, access keys) which are managed separately (e.g., through environment settings or configuration files).
    *   The current scripts do not detail specific user login systems for the application itself or fine-grained access controls for who can see which documents.
*   **Future Considerations**: If stricter security is needed, features like user authentication, role-based access to different parts of the system or specific documents, and detailed audit logs of user actions could be developed. Standard Python logging is used in scripts, providing some operational trail, but not dedicated security audit logs.

This comprehensive process allows the system to transform a large collection of press releases into an intelligently searchable and interconnected knowledge base.