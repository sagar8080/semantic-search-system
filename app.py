import os
import hashlib
import chainlit as cl
import boto3
from opensearchpy import OpenSearch, RequestsHttpConnection, helpers, exceptions as opensearch_exceptions
from duckduckgo_search import DDGS
from langchain_docling.loader import DoclingLoader
import re
import json
from utils.opensearch import get_os_client
from utils.constants import *
from utils.bedrock import generate_embeddings
from utils.search_service import *


def clean_text(text: str) -> str:
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def bedrock_qa_completion(user_prompt: str, retrieved_documents: list, mode='web'):
    """Generates an answer using Bedrock LLM with provided documents as context."""
    if mode == 'web': # for web based
        cohere_documents = []
        for i, doc in enumerate(retrieved_documents):
            if doc.get("text"): # Ensure document has text
                cohere_documents.append({
                    "id": f"doc_{i}", # A unique ID for the document snippet for Cohere
                    "title": doc.get("source_url", f"Source {i+1} from {doc.get('origin', 'N/A')}"), # Use URL as title
                    "text": doc.get("text")
                })
    elif mode == 'kb' and retrieved_documents: # for knowledge base
        cohere_documents = []
        for i, doc in enumerate(retrieved_documents):
            cohere_documents.append({
                "id": f"doc_{i}",
                "summary": doc.get("summary"),
                "content" : doc.get("pr_content")
            })

    if not cohere_documents:
        print("WARN: No documents provided to Bedrock for QA. Answering based on prompt only (general knowledge).")
        
    try:
        request_body = {
            "message": user_prompt,
            "documents": cohere_documents, 
            "max_tokens": 2048,
            "temperature": 0.3, 
            "prompt_truncation": "AUTO_PRESERVE_ORDER",
        }
        body = json.dumps(request_body)
        response = bedrock_client.invoke_model(
            modelId=BASE_MODEL_ID, body=body,
            accept="application/json", contentType="application/json"
        )
        response_body = json.loads(response.get('body').read())
        if 'text' in response_body:
            return response_body['text']
        else:
            print(f"ERROR: Unexpected response structure from Bedrock LLM: {response_body}")
            return "Sorry, I couldn't parse the response from the model."
    except Exception as e:
        print(f"ERROR: Bedrock LLM completion failed: {e}")
        if hasattr(e, 'response') and 'Error' in e.response:
            print(f"Bedrock Error details: {e.response['Error']}")
        return "Sorry, I encountered an error while generating a response."

@cl.on_chat_start
async def start_chat():
    """Initializes the Chainlit chat application."""
    try:
        opensearch_client = get_os_client()
        if not opensearch_client.ping():
            raise ConnectionError("Failed to connect to OpenSearch. Knowledge Base will be unavailable.")
        cl.user_session.set("opensearch_client", opensearch_client)
        await cl.Message(content="Ask me anything! I'll check my knowledge base first, then the web if needed.").send()
    except Exception as e:
        print(f"FATAL: Error during Chainlit startup: {e}")
        await cl.ErrorMessage(content=f"Failed to initialize the application: {e}. Please check server logs.").send()


@cl.on_message
async def main(message: cl.Message):
    user_query = message.content.strip()
    if not user_query:
        await cl.Message(content="Please enter a query.").send()
        return

    opensearch_client = cl.user_session.get("opensearch_client")
    if not opensearch_client:
        await cl.ErrorMessage(content="OpenSearch client not available. Cannot access knowledge base.").send()
        return

    final_answer = ""
    sources_for_display = []
    documents_for_llm_context = []
    retrieved_documents_for_kg_and_sources = []

    llm_status_msg = None
    kb_status_msg = await cl.Message(content="Searching knowledge base...", author="Retriever").send()
    relevant_kb_docs = search_kb(user_query, k=5, use_llm_expansion=False, use_reranker=False)
    
    num_kb_docs = len(relevant_kb_docs) if relevant_kb_docs else 0
    
    if relevant_kb_docs:
        retrieved_documents_for_kg_and_sources.extend(relevant_kb_docs)
        documents_for_llm_context.extend(relevant_kb_docs)
        sources_for_display.extend(list(set([
            f"- {doc.get('pr_url', doc.get('source_url', 'KB Source'))} (Knowledge Base)"
            for doc in relevant_kb_docs if doc.get('pr_url', doc.get('source_url'))
        ])))
    if num_kb_docs < 3:
        if num_kb_docs > 0:
            kb_status_msg.content = f"Found {num_kb_docs} item(s) in knowledge base. Augmenting with web search..."
        else:
            kb_status_msg.content = "No specific information found in the knowledge base. Searching the internet..."
        await kb_status_msg.update()

        search_urls = []
        web_search_status_msg = await cl.Message(content="Searching the web...", author="SearchBot").send()
        fetched_web_documents_for_llm_temp = [] # Temp list for newly fetched web docs

        try:
            max_web_results_to_fetch = max(0, 3 - num_kb_docs)
            if max_web_results_to_fetch == 0 and num_kb_docs > 0: 
                max_web_results_to_fetch = 2
            
            if num_kb_docs == 0:
                max_web_results_to_fetch = 3

            if max_web_results_to_fetch > 0:
                with DDGS() as ddgs:
                    search_results_raw = ddgs.text(user_query, max_results=max_web_results_to_fetch + 1, region="us-en")
                    search_urls = [result['href'] for result in search_results_raw if 'href' in result][:max_web_results_to_fetch]

            if not search_urls:
                web_search_status_msg.content = "Could not find relevant pages on the internet to augment."
                await web_search_status_msg.update()
                if not documents_for_llm_context: # If KB was also empty
                    sources_for_display.append("- No specific sources found from web or knowledge base.")
            else:
                web_search_status_msg.content = f"Found {len(search_urls)} web pages. Fetching and processing..."
                await web_search_status_msg.update()
        except Exception as e:
            logging.error(f"ERROR: Web search using DuckDuckGo failed: {e}", exc_info=True)
            web_search_status_msg.content = f"Web search failed: {e}."
            await web_search_status_msg.update()
            if not documents_for_llm_context:
                sources_for_display.append("- Web search encountered an issue.")

        if search_urls:
            new_web_content_parsed_count = 0
            parsing_status_msg = web_search_status_msg

            for url_to_fetch in search_urls:
                if len(documents_for_llm_context) >= 5: # Limit total context for LLM to ~5 docs
                    break
                await parsing_status_msg.stream_token(f"\nFetching & Parsing: {url_to_fetch[:70]}...")
                try:
                    loader = DoclingLoader(file_path=[url_to_fetch])
                    docs_from_url = loader.load()
                    for doc_content_obj in docs_from_url:
                        page_text = getattr(doc_content_obj, 'page_content', str(doc_content_obj))
                        clean_content = clean_text(page_text)
                        if clean_content and len(clean_content) > 200:
                            web_doc = {
                                "text": clean_content,
                                "pr_title": f"Web: {clean_text(getattr(doc_content_obj, 'title', url_to_fetch[:50]))}", # For KG title
                                "pr_content": clean_content,
                                "source_url": url_to_fetch,
                                "origin": "Web"
                            }
                            fetched_web_documents_for_llm_temp.append(web_doc)
                            new_web_content_parsed_count += 1
                            break 
                except Exception as e:
                    logging.error(f"ERROR: Failed to parse web content from {url_to_fetch}: {e}", exc_info=True)
                    await parsing_status_msg.stream_token(f"\nFailed to parse: {url_to_fetch[:70]}...({e})")
            
            parsing_status_msg.content = f"Web content processing complete: {new_web_content_parsed_count} sections prepared."
            await parsing_status_msg.update()

            if fetched_web_documents_for_llm_temp:
                documents_for_llm_context.extend(fetched_web_documents_for_llm_temp)
                retrieved_documents_for_kg_and_sources.extend(fetched_web_documents_for_llm_temp)
                sources_for_display.extend(list(set([
                    f"- {doc['source_url']} (Web)"
                    for doc in fetched_web_documents_for_llm_temp if doc.get('source_url')
                ])))
            elif not documents_for_llm_context:
                sources_for_display.append("- Unable to process relevant web content.")

        sources_for_display = list(set(sources_for_display))

    else:
        kb_status_msg.content = f"Found {num_kb_docs} relevant items in the knowledge base."
        await kb_status_msg.update()
    final_context_for_llm = documents_for_llm_context[:5]

    if final_context_for_llm:
        llm_status_msg = await cl.Message(content="Synthesizing information to answer your query...", author="LLM").send()
        prepared_docs_for_qa = []
        for doc in final_context_for_llm:
            text_content = ""
            title = ""
            if doc.get("origin") == "Web":
                text_content = doc.get("text", "")
                title = doc.get("source_url", "Web Source")
            else:
                text_content = doc.get("pr_content", doc.get("summary", ""))
                title = doc.get("pr_title", "KB Document")
            
            if text_content:
                prepared_docs_for_qa.append({
                    "id": doc.get("id", hashlib.md5(text_content[:100].encode()).hexdigest()),
                    "title": title,
                    "text": text_content
                })
        final_answer = bedrock_qa_completion(user_query, prepared_docs_for_qa, mode='web')
    else:
        if kb_status_msg: await kb_status_msg.remove() 
        if 'web_search_status_msg' in locals() and web_search_status_msg: await web_search_status_msg.remove()

        await cl.Message(content="No relevant information found in knowledge base or on the web to answer your query.", author="System").send()
        final_answer = bedrock_qa_completion(user_query, []) 
        if not sources_for_display: sources_for_display.append("- No specific sources consulted.")


    if llm_status_msg:
        await llm_status_msg.remove()
    unique_sources = sorted(list(set(sources_for_display)))
    source_list_md = "\n".join(unique_sources[:10])
    if len(unique_sources) > 10:
        source_list_md += f"\n- ...and {len(unique_sources) - 10} more sources."
    
    if not final_answer:
        final_answer = "I'm sorry, I couldn't find a specific answer to your query at this time based on the available information."
    if not unique_sources and "- No specific sources consulted." not in final_answer :
         source_list_md = "- No specific sources consulted."

    await cl.Message(content=f"{final_answer}\n\n**Sources:**\n{source_list_md}").send()