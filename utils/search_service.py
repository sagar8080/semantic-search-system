import json
from opensearchpy.exceptions import RequestError
import boto3
import logging
from datetime import date
from utils.opensearch import *

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

client = OS_CLIENT
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
        ]
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
                            ],
                            "type": "best_fields",
                        }
                    },
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
            index=PR_META_VECTOR_IDX,
            body=hybrid_query_body
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
