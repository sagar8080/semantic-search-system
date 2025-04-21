from opensearch import OS_CLIENT, PR_META_RAW_IDX, PR_META_VECTOR_IDX

client = OS_CLIENT


def create_vector_index(index_name):
    index_body = {
        "settings": {"index.knn": True},  # Enable k-NN search functionality
        "mappings": {
            "properties": {
                # Embedding field for semantic search
                "embedding": {
                    "type": "knn_vector",
                    "dimension": 256,  # Set dimension based on Amazon Titan model
                    "method": {
                        "name": "hnsw",
                        "space_type": "cosinesimil",
                        "engine": "nmslib",
                    },
                },
                # Metadata fields
                "pr_url": {"type": "keyword"},
                "pr_title": {"type": "text"},
                "summary": {"type": "text"},
                "pr_date": {"type": "date"},
                "pr_content": {"type": "text"},
                # Named entities extracted from content
                "entities": {
                    "type": "nested",
                    "properties": {
                        "text": {"type": "text"},
                        "label": {"type": "keyword"},
                    },
                },
                # Topics identified through topic modeling
                "topics": {
                    "type": "nested",
                    "properties": {
                        "text": {"type": "text"},
                        "label": {"type": "keyword"},
                    },
                },
            }
        },
    }

    try:
        response = client.indices.create(index=index_name, body=index_body)
        print(f"Vector index '{index_name}' created successfully!")
        return response
    except Exception as e:
        print(f"Error creating vector index: {e}")


def create_meta_index(index_name):
    index_body = {"settings": {"index": {"number_of_shards": 2}}}
    try:
        response = client.indices.create(index_name, body=index_body)
        print(f"Metadata index '{index_name}' created successfully!")
        return response
    except Exception as e:
        print(f"Error creating meta index: {e}")


if client.indices.exists(PR_META_RAW_IDX):
    print("Index exists")
else:
    create_meta_index(PR_META_RAW_IDX)

if client.indices.exists(PR_META_RAW_IDX):
    print("Index exists")
else:
    create_meta_index(PR_META_RAW_IDX)

if client.indices.exists(PR_META_VECTOR_IDX):
    # client.indices.delete(VECTOR_INDEX_NAME)
    print("Vector index exists")
else:
    create_vector_index(PR_META_VECTOR_IDX)
