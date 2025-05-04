import streamlit as st
from datetime import date
from .search_service import simple_search, advanced_search, pro_search, pro_search_enhanced
import time

def render_document(doc: dict, show_content: bool = True):
    st.write(f"**Title:** {doc.get('pr_title', 'Untitled')}")
    bubble_css = """
    <style>
        .bubble-container { display: flex; gap: 8px; flex-wrap: wrap; margin: 10px 0; }
        .entity-bubble { background: #e3f2fd; border-radius: 15px; padding: 6px 12px; font-size: 0.9em; color: #1976d2; }
        .topic-bubble { background: #e8f5e9; border-radius: 15px; padding: 6px 12px; font-size: 0.9em; color: #2e7d32; }
    </style>
    """
    st.markdown(bubble_css, unsafe_allow_html=True)
    if entities := doc.get("entities"):
        st.write("**Key Entities:**")
        entities_html = '<div class="bubble-container">'
        for entity in entities:
            text = entity.get("text", "").replace("'", "&#39;")
            entities_html += f'<div class="entity-bubble">{text}</div>'
        entities_html += "</div>"
        st.markdown(entities_html, unsafe_allow_html=True)
    if topics := doc.get("topics"):
        st.write("**Related Topics:**")
        topics_html = '<div class="bubble-container">'
        for topic in topics:
            text = topic.get("text", "").replace("'", "&#39;")
            topics_html += f'<div class="topic-bubble">{text}</div>'
        topics_html += "</div>"
        st.markdown(topics_html, unsafe_allow_html=True)
    st.write(f"**URL:** {doc.get('pr_url', 'No URL available')}")
    st.write(f"**Date:** {doc.get('pr_date', 'Unknown date')}")
    st.write(f"**Summary:** {doc.get('summary', '----')}")

    if show_content:
        st.write("**Content Preview:**")
        preview_text = doc.get("pr_content", "Content not available")
        st.text(preview_text[:1000] + "..." if len(preview_text) > 1000 else preview_text)

def perform_search(query, mode, k, fuzziness, start_date, end_date):
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
            results = pro_search_enhanced(query, k, fuzziness, start_date_str, end_date_str)
    except Exception as e:
        st.error(f"An error occurred during search: {e}")
        print(f"Search Error: {e}")
        results = []
    return results if results else []