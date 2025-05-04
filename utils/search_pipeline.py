import json
import logging
import os
import boto3
import time
from opensearchpy.exceptions import RequestError
from .constants import BASE_MODEL_ID, CROSS_ENCODER_MODEL_NAME
from .bedrock import *
from .opensearch import get_os_client

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

    
client = get_os_client()


def expand_query_with_llm(query: str):
    prompt = f"""
    Given the following search query, generate 3-5 alternative queries or relevant keywords that capture the user's potential intent. 
    Focus on variations in phrasing, related concepts relevant to policy documents or technical topics. 
    Output each alternative query or keyword on a new line. Do not include the original query in the output.
    Original Query: "{query}"
    **NOTE**: Do not add line number in the query output.
    """
    expanded_queries = [query]
    response = engage_llm(prompt)
    alternatives = [q.strip()[3:] for q in response.split('\n') if q.strip()]
    if alternatives:
        expanded_queries.extend(alternatives)
    return expanded_queries

def normalize_scores_to_100(results):
    if not results:
        return []

    valid_scores = [
        res.get("score")
        for res in results
        if isinstance(res.get("score"), (int, float))
    ]

    if not valid_scores:
        for res in results:
            res["normalized_score_100"] = 1.0
        return results

    min_score = min(valid_scores)
    max_score = max(valid_scores)

    for res in results:
        score = res.get("score")
        if not isinstance(score, (int, float)):
            res["normalized_score_100"] = 1.0
        elif max_score == min_score:
            res["normalized_score_100"] = 100.0 if max_score > 0 else 1.0
        else:
            normalized_val = 1 + ((score - min_score) / (max_score - min_score)) * 99
            res["normalized_score_100"] = max(
                1.0, min(100.0, normalized_val)
            )

    return results


def rerank_with_bedrock(query: str, documents: list, top_n: int = 10):
    bedrock_agent_runtime_client = boto3.client('bedrock-agent-runtime', region_name='us-west-2')

    if not documents:
        logging.warning("No documents provided for reranking.")
        return []

    source_texts = []
    original_indices_map = {}
    valid_doc_count = 0
    for i, doc in enumerate(documents):
        doc_text = f"{doc.get('pr_title', '')} {doc.get('pr_summary', doc.get('pr_content', ''))}".strip()
        if doc_text:
             source_texts.append(doc_text)
             original_indices_map[valid_doc_count] = i
             valid_doc_count += 1
        else:
             logging.debug(f"Document at original index {i} skipped due to empty text fields.")

    if not source_texts:
        logging.warning("No valid documents with text found for reranking.")
        return documents[:top_n]

    logging.info(f"Reranking {len(source_texts)} documents for query '{query}' using Bedrock Reranker...")

    try:
        start_time = time.time()

        rerank_request = {
            "queries": [
                {
                    "type": "TEXT",
                    "textQuery": {
                        "text": query
                    }
                }
            ],
            "sources": [
                {
                    "type": "INLINE",
                    "inlineDocumentSource": {
                        "textDocument": { "text": text },
                        "type": "TEXT"
                    }
                } for text in source_texts
            ],
            "rerankingConfiguration": {
                "bedrockRerankingConfiguration": {
                    "modelConfiguration": {
                        "modelArn": BEDROCK_RERANKER_MODEL_ARN
                    },
                    "numberOfResults": top_n
                },
                "type": "BEDROCK_RERANKING_MODEL"
            }
        }
        bedrock_agent_runtime_client
        response = bedrock_agent_runtime_client.rerank(**rerank_request)
        rerank_time = time.time() - start_time
        logging.info(f"Bedrock rerank call took {rerank_time:.2f} seconds.")

        reranked_docs = []
        if 'results' in response:
            for result in response['results']:
                original_doc_index = original_indices_map.get(result['index'])
                if original_doc_index is not None:
                    doc = documents[original_doc_index].copy()
                    # Bedrock relevance score is 0-1
                    doc['bedrock_relevance_score'] = float(result['relevanceScore'])
                    reranked_docs.append(doc)
                else:
                    logging.warning(f"Could not map Bedrock result index {result['index']} back to original document.")

            logging.info(f"Returning {len(reranked_docs)} documents reranked by Bedrock.")
            return reranked_docs
        else:
            logging.warning("Bedrock rerank response did not contain 'results'. Returning original top N.")
            return documents[:top_n]

    except ClientError as e:
        logging.error(f"Bedrock API ClientError during reranking: {e}", exc_info=True)
        return documents[:top_n]
    except Exception as e:
        logging.error(f"Unexpected error during Bedrock reranking: {e}", exc_info=True)
        return documents[:top_n]

def build_date_filter(start_date=None, end_date=None):
    """Build date range filter for OpenSearch queries"""
    if not start_date and not end_date:
        return []

    date_filter = {
        "range": {
            "pr_date": {
                **({"gte": start_date} if start_date else {}),
                **({"lte": end_date} if end_date else {}),
            }
        }
    }
    return [date_filter]


def execute_search(query_body):
    """Execute search against OpenSearch index and process results"""
    try:
        response = client.search(index=PR_META_VECTOR_IDX, body=query_body)

        results = []
        if response and "hits" in response and "hits" in response["hits"]:
            for hit in response["hits"]["hits"]:
                if hit.get("_source"):
                    doc = hit["_source"]
                    doc["score"] = hit.get("_score", 0.0)
                    results.append(doc)
                else:
                    logging.warning(f"Hit {hit.get('_id')} missing _source field.")
            logging.info(f"Found {len(results)} results.")
        else:
            logging.info("No hits found.")

        return normalize_scores_to_100(results)

    except RequestError as re:
        logging.error(
            f"OpenSearch RequestError during search: {re.info}", exc_info=True
        )
        return []
    except Exception as e:
        logging.error(f"Unexpected error during search: {e}", exc_info=True)
        return []