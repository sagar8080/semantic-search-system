import streamlit as st
import json
from opensearchpy import OpenSearch, RequestsHttpConnection
from opensearchpy.exceptions import NotFoundError, RequestError
import boto3
import logging
from datetime import date
from utils import *


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

client = get_os_client()
bedrock_client = boto3.client("bedrock-runtime", region_name="us-east-1")


def generate_embeddings(text, model_id=EMBEDDING_MODEL_ID):
    try:
        response = bedrock_client.invoke_model(
            modelId=model_id,
            contentType="application/json",
            accept="application/json",
            body=json.dumps({"inputText": text, "normalize": True, "dimensions": 256}),
        )
        embedding = json.loads(response["body"].read().decode("utf-8"))
        return embedding[
            "embedding"
        ]  # List of floats representing the embedding vector
    except Exception as e:
        print(f"Error generating embeddings with Titan: {e}")
        return None


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


def search_documents(
    query: str,
    k: int = 10,
    fuzziness: int = 2,
    start_date: str = None,
    end_date: str = None,
):
    if not query:
        logging.warning("Search query is empty.")
        return []

    try:
        query_embedding = generate_embeddings(query)
        if not query_embedding:
            logging.error(
                "Failed to generate query embedding. Cannot perform hybrid search."
            )
            return []
        date_filter = {}
        if start_date or end_date:
            date_filter = {
                "range": {
                    "pr_date": {
                        **({"gte": start_date} if start_date else {}),
                        **({"lte": end_date} if end_date else {}),
                    }
                }
            }
        semantic_k = max(k * 5, 50)
        semantic_sub_query = {
            "knn": {"embedding": {"vector": query_embedding, "k": semantic_k}}
        }

        lexical_sub_query = {
            "bool": {
                "should": [
                    {
                        "multi_match": {
                            "query": query,
                            "fields": [
                                "pr_title^2",
                                "pr_content^3",
                            ],  # Boost title & summary
                            "type": "best_fields",
                        }
                    },
                    # Boosted Fuzzy matches
                    {
                        "match": {
                            "pr_title": {
                                "query": query,
                                "fuzziness": fuzziness,
                                "boost": 2.0,
                            }
                        }
                    },
                    {
                        "match": {
                            "pr_content": {
                                "query": query,
                                "fuzziness": fuzziness,
                                "boost": 1.5,
                            }
                        }
                    },
                    {
                        "nested": {
                            "path": "entities",
                            "query": {
                                "match": {
                                    "entities.text": {
                                        "query": query,
                                        "fuzziness": fuzziness,
                                        "boost": 1.5,
                                    }
                                }
                            },
                        }
                    },
                    {
                        "nested": {
                            "path": "topics",
                            "query": {
                                "match": {
                                    "topics.text": {
                                        "query": query,
                                        "fuzziness": fuzziness,
                                        "boost": 1.5,
                                    }
                                }
                            },
                        }
                    },
                ],
                "filter": [date_filter] if date_filter else [],
                "minimum_should_match": 1,
            }
        }

        hybrid_query_body = {
            "query": {"hybrid": {"queries": [lexical_sub_query, semantic_sub_query]}},
            "size": k,
            "_source": True,
        }
        logging.info(f"Executing hybrid search for query: '{query}'")
        response = client.search(
            index=VECTOR_INDEX_NAME,
            body=hybrid_query_body,
            # No 'search_pipeline' param needed here IF it's set as default
        )
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

        return results

    except RequestError as re:
        logging.error(
            f"OpenSearch RequestError during search: {re.info}", exc_info=True
        )
        return []
    except Exception as e:
        logging.error(
            f"Unexpected error during search for query '{query}': {e}", exc_info=True
        )
        return []


PIPELINE_DEFINITION = {
    "description": "Pipeline for normalizing and combining lexical/semantic scores",
    "phase_results_processors": [
        {
            "normalization-processor": {
                "normalization": {"technique": "min_max"},
                "combination": {"technique": "arithmetic_mean"},
            }
        }
    ],
}


def create_search_pipeline(os_client, pipeline_name, pipeline_body):
    logging.info(f"Attempting to create/update search pipeline '{pipeline_name}'...")
    try:
        response = os_client.transport.perform_request(
            "PUT", f"/_search/pipeline/{pipeline_name}", body=pipeline_body
        )
        logging.info(
            f"Pipeline '{pipeline_name}' created/updated successfully: {response}"
        )
        return True
    except Exception as e:
        logging.error(
            f"Failed to create/update pipeline '{pipeline_name}': {e}", exc_info=True
        )
        return False


def set_default_search_pipeline(os_client, index_name, pipeline_name):
    logging.info(
        f"Attempting to set '{pipeline_name}' as default search pipeline for index '{index_name}'..."
    )
    try:
        response = os_client.indices.put_settings(
            index=index_name,
            body={"index.search.default_pipeline": pipeline_name},
        )
        if response.get("acknowledged"):
            logging.info(
                f"Successfully set default search pipeline for index '{index_name}'."
            )
            return True
        else:
            logging.warning(
                f"Setting default pipeline for '{index_name}' may not have been acknowledged: {response}"
            )
            return False
    except NotFoundError:
        logging.error(f"Index '{index_name}' not found. Cannot set default pipeline.")
        return False
    except Exception as e:
        logging.error(
            f"Failed to set default search pipeline for index '{index_name}': {e}",
            exc_info=True,
        )
        return False


logging.info("--- Running One-Time Setup ---")
pipeline_created = create_search_pipeline(client, PIPELINE_NAME, PIPELINE_DEFINITION)

if pipeline_created:
    default_set = set_default_search_pipeline(client, VECTOR_INDEX_NAME, PIPELINE_NAME)
    if not default_set:
        logging.error(
            "Failed to set the pipeline as default. Searches might not use the pipeline unless specified explicitly."
        )
else:
    logging.error("Pipeline creation failed. Cannot set it as default.")

logging.info("--- Setup Complete ---")


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
        response = client.search(index=VECTOR_INDEX_NAME, body=query_body)

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


def simple_search(
    query: str,
    k: int = 10,
    fuzziness: int = 2,
    start_date: str = None,
    end_date: str = None,
):
    """Focus on topics/entities with lexical+fuzzy search"""
    query_body = {
        "query": {
            "bool": {
                "should": [
                    {
                        "nested": {
                            "path": "topics",
                            "query": {
                                "bool": {
                                    "should": [
                                        {
                                            "match": {
                                                "topics.text": {
                                                    "query": query,
                                                    "fuzziness": fuzziness,
                                                }
                                            }
                                        },
                                        {
                                            "term": {
                                                "topics.text.keyword": {
                                                    "value": query,
                                                    "case_insensitive": True,
                                                }
                                            }
                                        },
                                    ]
                                }
                            },
                        }
                    },
                    {
                        "nested": {
                            "path": "entities",
                            "query": {
                                "bool": {
                                    "should": [
                                        {
                                            "match": {
                                                "entities.text": {
                                                    "query": query,
                                                    "fuzziness": fuzziness,
                                                }
                                            }
                                        },
                                        {
                                            "term": {
                                                "entities.text.keyword": {
                                                    "value": query,
                                                    "case_insensitive": True,
                                                }
                                            }
                                        },
                                    ]
                                }
                            },
                        }
                    },
                ],
                "filter": build_date_filter(start_date, end_date),
                "minimum_should_match": 1,
            }
        },
        "size": k,
    }
    return execute_search(query_body)


def advanced_search(
    query: str,
    k: int = 10,
    fuzziness: int = 2,
    start_date: str = None,
    end_date: str = None,
):
    query_embedding = generate_embeddings(query)
    if not query_embedding:
        logging.error(
            "Failed to generate query embedding. Cannot perform semantic search."
        )
        return []

    query_body = {
        "query": {
            "bool": {
                "should": [
                    {
                        "multi_match": {
                            "query": query,
                            "fields": ["pr_title^3", "summary^2"],
                            "fuzziness": fuzziness,
                        }
                    },
                    {"knn": {"embedding": {"vector": query_embedding, "k": k * 3}}},
                ],
                "filter": build_date_filter(start_date, end_date),
            }
        },
        "size": k,
    }
    return execute_search(query_body)


def pro_search(
    query: str,
    k: int = 10,
    fuzziness: int = 2,
    start_date: str = None,
    end_date: str = None,
):
    if not query:
        logging.warning("Search query is empty.")
        return []

    query_embedding = generate_embeddings(query)
    if not query_embedding:
        logging.error(
            "Failed to generate query embedding. Cannot perform hybrid search."
        )
        return []
    date_filter = {}
    if start_date or end_date:
        date_filter = {
            "range": {
                "pr_date": {
                    **({"gte": start_date} if start_date else {}),
                    **({"lte": end_date} if end_date else {}),
                }
            }
        }
    # b. Define Semantic Sub-Query (k-NN)
    semantic_k = max(k * 5, 50)
    semantic_sub_query = {
        "knn": {"embedding": {"vector": query_embedding, "k": semantic_k}}
    }
    lexical_sub_query = {
        "bool": {
            "should": [
                {
                    "multi_match": {
                        "query": query,
                        "fields": ["pr_summary^2", "pr_content^3"],
                        "type": "best_fields",
                    }
                },
                # Boosted Fuzzy matches
                {
                    "match": {
                        "pr_title": {
                            "query": query,
                            "fuzziness": fuzziness,
                            "boost": 2.0,
                        }
                    }
                },
                {
                    "match": {
                        "pr_content": {
                            "query": query,
                            "fuzziness": fuzziness,
                            "boost": 1.5,
                        }
                    }
                },
                {
                    "nested": {
                        "path": "entities",
                        "query": {
                            "match": {
                                "entities.text": {
                                    "query": query,
                                    "fuzziness": fuzziness,
                                    "boost": 1.5,
                                }
                            }
                        },
                    }
                },
                {
                    "nested": {
                        "path": "topics",
                        "query": {
                            "match": {
                                "topics.text": {
                                    "query": query,
                                    "fuzziness": fuzziness,
                                    "boost": 1.5,
                                }
                            }
                        },
                    }
                },
            ],
            "filter": [date_filter] if date_filter else [],
            "minimum_should_match": 2,
        }
    }

    hybrid_query_body = {
        "query": {"hybrid": {"queries": [lexical_sub_query, semantic_sub_query]}},
        "size": k,
        "_source": True,
    }

    return execute_search(hybrid_query_body)
