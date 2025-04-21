import streamlit as st
import pandas as pd
from neo4j import GraphDatabase
from dotenv import load_dotenv
import os
from pyvis.network import Network
import streamlit.components.v1 as components
import logging
import re
from utils.get_secrets import get_secret

APP_TITLE = "Graph Explorer"
NEO4J_DRIVER_KEY = "neo4j_driver"


@st.cache_resource(show_spinner="Connecting to Neo4j...")
def get_neo4j_driver():
    """Establishes and caches the Neo4j driver connection."""
    credentials = get_secret()
    uri = credentials.get("NEO4J_URI")
    user = credentials.get("NEO4J_USERNAME")
    password = credentials.get("NEO4J_PASSWORD")
    if not all([uri, user, password]): st.error("Neo4j connection details missing in .env file."); st.stop()
    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
        driver.verify_connectivity()
        logging.info("Neo4j connection successful.")
        return driver
    except Exception as e: st.error(f"Failed to connect to Neo4j: {e}"); logging.error(f"Neo4j connection failed: {e}", exc_info=True); st.stop()

@st.cache_data(show_spinner="Fetching topics...")
def fetch_topics(_driver):
    """Fetches all distinct BroadTopic names from Neo4j."""
    try:
        with _driver.session(database="neo4j") as session:
            result = session.run("MATCH (t:BroadTopic) RETURN t.name AS topic ORDER BY topic")
            return [record["topic"] for record in result]
    except Exception as e: st.error(f"Failed to fetch topics: {e}"); logging.error(f"Error fetching topics: {e}", exc_info=True); return []

@st.cache_data(show_spinner="Fetching documents for topic...")
def fetch_documents_for_topic(_driver, topic_name):
    """Fetches documents directly related to a specific BroadTopic."""
    if not topic_name: return []
    try:
        with _driver.session(database="neo4j") as session:
            query = """
            MATCH (t:BroadTopic {name: $topic_name})-[:RELATES_TO_DOC]->(d:Document)
            RETURN d.docId AS doc_id, d.title AS title, d.url AS url
            ORDER BY d.title LIMIT 500
            """
            result = session.run(query, topic_name=topic_name)
            return [dict(record) for record in result]
    except Exception as e: st.error(f"Failed to fetch documents for '{topic_name}': {e}"); logging.error(f"Error fetching documents for '{topic_name}': {e}", exc_info=True); return []

@st.cache_data(show_spinner="Fetching subgraph data...")
def fetch_subgraph_data(_driver, selected_topics):
    """Fetches nodes (Topics, Documents) and relationships for selected topics, formatting for Pyvis."""
    if not selected_topics: return {"nodes": [], "edges": []}
    try:
        with _driver.session(database="neo4j") as session:
            query = """
            MATCH (t:BroadTopic)-[r:RELATES_TO_DOC]->(d:Document)
            WHERE t.name IN $selected_topics
            RETURN collect(DISTINCT t) AS topics, collect(DISTINCT d) AS documents, collect(DISTINCT r) AS relationships
            """
            result = session.run(query, selected_topics=selected_topics)
            data = result.single()
            nodes, edges = [], []
            if data:
                node_elements_added = set()
                for node in data.get("topics", []):
                    if node.element_id not in node_elements_added:
                        topic_name = node.get("name", "Unknown Topic")
                        hover_title = f"{topic_name}" # HTML for hover
                        nodes.append({
                            "id": node.element_id, "label": topic_name, "title": hover_title,
                            "color": "#ffffff", "size": 50, "type": "BroadTopic" # Store type
                        })
                        node_elements_added.add(node.element_id)
                for node in data.get("documents", []):
                     if node.element_id not in node_elements_added:
                        doc_id = node.get("docId", "N/A"); title = node.get("title", "No Title"); url = node.get("url", None) # Default URL to None if missing
                        # Ensure URL is valid-looking or None
                        if url and not url.startswith(('http://', 'https://')):
                            url = None # Treat invalid URLs as None
                        hover_title = f"Title: {title}" # HTML for hover
                        nodes.append({
                            "id": node.element_id, "label": f"Doc {doc_id}", "title": hover_title,
                            "color": "#7eee23", "size": 30, "type": "Document", # Store type
                            "url": url # Store the actual URL here
                        })
                        node_elements_added.add(node.element_id)
                for rel in data.get("relationships", []):
                    edges.append({"from": rel.start_node.element_id, "to": rel.end_node.element_id})
            logging.info(f"Fetched subgraph: {len(nodes)} nodes, {len(edges)} edges.")
            return {"nodes": nodes, "edges": edges}
    except Exception as e: st.error(f"Failed to fetch subgraph data: {e}"); logging.error(f"Error fetching subgraph: {e}", exc_info=True); return {"nodes": [], "edges": []}

# --- Visualization Function ---

@st.cache_data(show_spinner="Generating graph visualization...")
def generate_pyvis_html_from_neo4j_data(subgraph_data):
    """Generates interactive HTML from fetched Neo4j subgraph data using Pyvis, with transparent background and clickable nodes."""
    nodes = subgraph_data.get("nodes", [])
    edges = subgraph_data.get("edges", [])

    if not nodes: return "<p>No data available to visualize.</p>"

    net = Network(height='700px', width='100%', directed=False, notebook=True, bgcolor="#1b1f22",)

    # Add nodes - PASS THE 'url' ATTRIBUTE FOR DOCUMENT NODES
    for node_data in nodes:
        pyvis_node_attrs = {
            "label": node_data.get("label", node_data["id"]),
            "title": node_data.get("title", node_data["id"]),
            "color": node_data.get("color", "#97C2FC"),
            "size": node_data.get("size", 50),
            "shape": 'dot',
            # Pass type and url directly as node attributes
            "type": node_data.get("type"),
            "url": node_data.get("url")
        }
        # Filter out None values before passing to PyVis
        pyvis_node_attrs_cleaned = {k: v for k, v in pyvis_node_attrs.items() if v is not None}
        net.add_node(node_data["id"], **pyvis_node_attrs_cleaned)

    # Add edges
    for edge_data in edges:
        net.add_edge(edge_data["from"], edge_data["to"], title=edge_data.get("title", ""))

    # Configure physics
    net.options.physics.enabled = True
    net.options.physics.solver = 'forceAtlas2Based'
    net.options.physics.forceAtlas2Based = {"gravitationalConstant": -100, "centralGravity": 0.01, "springLength": 110, "springConstant": 0.06, "damping": 0.5, "avoidOverlap": 0.2}
    net.options.physics.minVelocity = 0.5
    net.options.interaction.hover = True
    net.options.interaction.tooltipDelay = 100
    net.options.interaction.navigationButtons = False

    try:
        # Generate base HTML
        html_content = net.generate_html(notebook=True)
        css_injection = "<style> body { background-color: transparent !important; } </style>"
        html_content = re.sub(r'(</head>)', f'{css_injection}\\1', html_content, flags=re.IGNORECASE, count=1)
        if css_injection not in html_content: html_content = html_content.replace('<head>', f'<head>{css_injection}', 1)
        js_injection = """
        <script type="text/javascript">
          // Wait for the network object to be initialized by Pyvis
          function setupNodeClickListener() {
            if (typeof network !== 'undefined') {
              network.on("click", function (params) {
                // console.log("Click event:", params); // For debugging
                if (params.nodes.length > 0) {
                  var clickedNodeId = params.nodes[0];
                  try {
                    // Access the node data stored by vis.js/pyvis
                    var nodeData = network.body.data.nodes.get(clickedNodeId);
                    // console.log("Clicked node data:", nodeData); // For debugging

                    // Check if it's a document node and has a valid URL
                    if (nodeData && nodeData.type === 'Document' && nodeData.url && nodeData.url !== '#') {
                      // console.log("Opening URL:", nodeData.url); // For debugging
                      window.open(nodeData.url, '_blank'); // Open in new tab
                    }
                  } catch (e) {
                    console.error("Error processing click event:", e);
                  }
                }
              });
              console.log("Pyvis click listener setup complete.");
            } else {
              // If network object isn't ready, try again shortly
              // console.log("Network object not ready, retrying...");
              setTimeout(setupNodeClickListener, 100);
            }
          }
          // Start checking for the network object once the DOM is ready
          document.addEventListener('DOMContentLoaded', setupNodeClickListener);
        </script>
        """
        html_content = re.sub(r'(</body>)', f'{js_injection}\\1', html_content, flags=re.IGNORECASE, count=1)
        if js_injection not in html_content: html_content += js_injection

        logging.info("Injected CSS (transparency) and JS (clickable nodes) into Pyvis HTML.")
        return html_content

    except Exception as e:
        st.error(f"Error generating Pyvis HTML: {e}")
        logging.error(f"Error generating Pyvis HTML: {e}", exc_info=True)
        return f"<p>Error generating graph visualization: {e}</p>"