import json
import boto3
import logging
from datetime import date
from .constants import *
from .opensearch import get_os_client
from .search_pipeline import *
from .bedrock import generate_embeddings

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
    
client = get_os_client()

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

def pro_search_enhanced(
    query: str,
    k: int = 10,
    fuzziness: int = 2,
    start_date: str = None,
    end_date: str = None,
    use_topic_expansion: bool = False,
    use_llm_expansion: bool = True,
    use_reranker: bool = True,
    rerank_window_factor: int = 5
    ):
    if not query:
        logging.warning("Search query is empty.")
        return []

    search_terms = [query]

    if use_llm_expansion:
        llm_expanded_terms = expand_query_with_llm(query)
        search_terms.extend(llm_expanded_terms)
        search_terms = list(set(search_terms))

    logging.info(f"Using search terms after expansion: {search_terms}")
    original_query_embedding = generate_embeddings(query)
    if not original_query_embedding:
        logging.error("Failed to generate query embedding. Cannot perform hybrid search.")
        return []

    initial_retrieve_k = k * rerank_window_factor if use_reranker else k
    semantic_k = max(initial_retrieve_k, 50)

    semantic_sub_query = {
        "knn": {"embedding": {"vector": original_query_embedding, "k": semantic_k}}
    }
    lexical_should_clauses = []
    for i, term in enumerate(search_terms):
        boost_factor = 1.0 if term.lower() == query.lower() else 0.5 # Boost original query higher
        lexical_should_clauses.extend([
            {"match": {"pr_title": {"query": term, "fuzziness": fuzziness, "boost": 2.0 * boost_factor}}},
            {"match": {"pr_content": {"query": term, "fuzziness": fuzziness, "boost": 1.5 * boost_factor}}},
            {"match": {"pr_summary": {"query": term, "fuzziness": fuzziness, "boost": 2.0 * boost_factor}}},
            {"nested": {"path": "entities", "query": {"match": {"entities.text": {"query": term, "fuzziness": fuzziness, "boost": 1.5 * boost_factor}}}}},
            {"nested": {"path": "topics", "query": {"match": {"topics.text": {"query": term, "fuzziness": fuzziness, "boost": 1.5 * boost_factor}}}}},
        ])

    lexical_sub_query = {
        "bool": {
            "should": lexical_should_clauses,
            "filter": build_date_filter(start_date, end_date),
            "minimum_should_match": 1, # Needs at least one clause to match
        }
    }

    hybrid_query_body = {
        "query": {"hybrid": {"queries": [lexical_sub_query, semantic_sub_query]}},
        "size": initial_retrieve_k,
        "_source": True,
    }

    logging.info(f"Executing initial retrieval for query: '{query}' (expanded terms used)")
    initial_results = execute_search(hybrid_query_body)

    if not initial_results:
        return []
    if use_reranker:
        logging.info(f"Passing {len(initial_results)} documents to reranker.")
        final_results = rerank_with_bedrock(query, initial_results, top_n=k)
    else:
        final_results = normalize_scores_to_100(initial_results[:k])
    return final_results

def search_kb(
    query: str,
    k: int = 5,
    fuzziness: int = 2,
    start_date: str = None,
    end_date: str = None,
    use_llm_expansion: bool = True,
    use_reranker: bool = True,
    rerank_window_factor: int = 5
):
    if not query:
        logging.warning("Search query is empty.")
        return []

    search_terms = [query]

    if use_llm_expansion:
        # Assuming expand_query_with_llm returns a list of strings
        llm_expanded_terms = expand_query_with_llm(query) 
        if llm_expanded_terms: # Check if expansion returned any terms
            search_terms.extend(llm_expanded_terms)
        search_terms = list(set(search_terms)) # Deduplicate

    logging.info(f"Using search terms after expansion: {search_terms}")
    
    original_query_embedding = generate_embeddings(query)
    if not original_query_embedding:
        logging.error("Failed to generate query embedding. Cannot perform hybrid search.")
        return []

    initial_retrieve_k = rerank_window_factor if use_reranker else k
    semantic_k = min(max(1, initial_retrieve_k), 10) 

    semantic_sub_query = {
        "knn": {"embedding": {"vector": original_query_embedding, "k": semantic_k}}
    }
    
    lexical_should_clauses = []
    for i, term in enumerate(search_terms):
        boost_factor = 1.0 if term.lower() == query.lower() else 0.5 
        lexical_should_clauses.extend([
            {"match": {"pr_title": {"query": term, "fuzziness": fuzziness, "boost": 2.0 * boost_factor}}},
            {"match": {"pr_content": {"query": term, "fuzziness": fuzziness, "boost": 1.5 * boost_factor}}},
            {"match": {"pr_summary": {"query": term, "fuzziness": fuzziness, "boost": 2.0 * boost_factor}}},
        ])

    lexical_sub_query = {
        "bool": {
            "should": lexical_should_clauses,
            "filter": build_date_filter(start_date, end_date) if build_date_filter(start_date, end_date) else [], 
            "minimum_should_match": 1,
        }
    }

    hybrid_query_body = {
        "query": {"hybrid": {"queries": [lexical_sub_query, semantic_sub_query]}},
        "size": initial_retrieve_k,
        "_source": True,
    }

    logging.info(f"Executing initial retrieval for query: '{query}'")
    pre_filtered_results = execute_search(hybrid_query_body)

    if not pre_filtered_results:
        logging.info("No initial results from OpenSearch.")
        return []
    final_results_meeting_threshold = None
    if use_reranker:
        logging.info(f"Passing {len(pre_filtered_results)} documents to reranker.")
        # Assume rerank_with_bedrock takes the list and returns top_n results with a 'relevance_score' (0-1)
        reranked_results = rerank_with_bedrock(query, pre_filtered_results, top_n=k) 
        final_results_meeting_threshold = [
            doc for doc in reranked_results if doc.get('bedrock_relevance_score', 0.0) >= 0.60
        ]
        if not final_results_meeting_threshold:
             logging.info("No documents met the 60 percent reranking score threshold after initial OS filter.")

    else: # Not using reranker
        # Assume normalize_scores_to_100 processes the list and adds a 'normalized_score' (0-100)
        normalized_results = normalize_scores_to_100(pre_filtered_results) 

        confidently_normalized_results = [
            doc for doc in normalized_results if doc.get('score', 0.0) >= 0.70
        ]

        if not confidently_normalized_results:
            logging.info("No documents met the 70% normalized score threshold after initial OS filter.")
        else:
            # Sort by normalized_score and take top k from those meeting the threshold
            confidently_normalized_results.sort(key=lambda x: x.get('normalized_score_100', 0.0), reverse=True)
            final_results_meeting_threshold = confidently_normalized_results[:k]            
    return final_results_meeting_threshold