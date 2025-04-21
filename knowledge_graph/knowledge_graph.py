import json
import os
import re
from utils.get_secrets import get_secrets
from collections import defaultdict
from neo4j import GraphDatabase, unit_of_work
import logging
import time


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
secrets = get_secrets()
NEO4J_URI = secrets.get("NEO4J_URI")
NEO4J_USERNAME = secrets.get("NEO4J_USERNAME")
NEO4J_PASSWORD = secrets.get("NEO4J_PASSWORD")

if not all([NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD]):
    logging.error("Neo4j credentials (URI, USERNAME, PASSWORD) not found in .env file. Exiting.")
    exit(1)

def load_json_safe(filepath):
    """Loads a JSON file safely, handling potential errors and basic cleaning."""
    if not os.path.exists(filepath):
        logging.error(f"File not found at {filepath}")
        raise FileNotFoundError(f"Error: File not found at {filepath}")
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            content = re.sub(r',\s*(\]|\})', r'\1', content) # Basic cleaning
            data = json.loads(content)
        if not isinstance(data, dict):
            logging.error(f"Invalid JSON structure in {filepath}. Expected a dictionary.")
            raise ValueError(f"Error: Invalid JSON structure in {filepath}.")
        logging.info(f"Successfully loaded and parsed {filepath}")
        return data
    except json.JSONDecodeError as e:
        logging.error(f"Error decoding JSON from {filepath} near line {e.lineno}, col {e.colno}: {e.msg}")
        raise ValueError(f"JSON decoding failed for {filepath}. Check file structure.") from e
    except Exception as e:
        logging.error(f"An unexpected error occurred while loading {filepath}: {e}")
        raise RuntimeError(f"Unexpected error loading {filepath}") from e

def normalize_key(key_string):
    """Normalizes keys by stripping whitespace and lowercasing."""
    if not isinstance(key_string, str):
        key_string = str(key_string)
    return key_string.strip().lower()

# Updated cleanup function using batching
@unit_of_work(timeout=300) # Set a timeout for potentially long operations
def cleanup_neo4j_database(tx, batch_size=10000):
    """
    Deletes all nodes and relationships in the database in batches.
    Constraints and Indexes are NOT deleted by this method.
    """
    logging.info(f"Starting database cleanup (deleting nodes and relationships) in batches of {batch_size}...")
    total_deleted = 0
    while True:
        # This query finds nodes, detaches and deletes them in batches within a single transaction context provided by execute_write
        # Using LIMIT within the subquery passed to CALL ensures we process batches.
        result = tx.run("""
            MATCH (n)
            CALL {
                WITH n
                DETACH DELETE n
                RETURN count(n) AS deleted_count
            }
            RETURN sum(deleted_count) AS total_deleted_in_batch
        """, parameters_={"batch_limit": batch_size}) 
        result = tx.run("""
            MATCH (n)
            WITH n LIMIT $batch_size
            DETACH DELETE n
            RETURN count(n) as deleted_count
        """, batch_size=batch_size)

        count = result.single()["deleted_count"]
        total_deleted += count
        logging.info(f"Deleted {count} nodes in this batch. Total deleted so far: {total_deleted}")
        if count == 0:
            # No more nodes found to delete in a batch of this size
            logging.info("Cleanup finished: No more nodes found to delete.")
            break 
        time.sleep(0.1)

    logging.info(f"Database cleanup complete. Total nodes deleted: {total_deleted}")
    return total_deleted


# Keep constraint creation function
def create_constraints(tx):
    logging.info("Applying constraints (if they don't exist)...")
    tx.run("CREATE CONSTRAINT topic_name_unique IF NOT EXISTS FOR (n:BroadTopic) REQUIRE n.name IS UNIQUE;")
    tx.run("CREATE CONSTRAINT doc_id_unique IF NOT EXISTS FOR (n:Document) REQUIRE n.docId IS UNIQUE;")
    logging.info("Constraints applied or already exist.")

# Keep direct link creation function
def _create_direct_topic_doc_link_tx(tx, broad_topic_name_norm, doc_id_str, url, title):
    query = (
        "MERGE (bt:BroadTopic {name: $topic_name}) "
        "MERGE (d:Document {docId: $doc_id}) "
        "ON CREATE SET d.url = $url, d.title = $title, d.firstSeen = timestamp() "
        "ON MATCH SET d.url = $url, d.title = $title, d.lastSeen = timestamp() "
        "MERGE (bt)-[:RELATES_TO_DOC]->(d)"
    )
    tx.run(query, topic_name=broad_topic_name_norm, doc_id=doc_id_str, url=url, title=title)


def load_data_to_neo4j_direct(driver, topic_mapping_data, topics_data):
    """
    Loads data, creating direct links from Broad Topics to Documents in Neo4j.
    (Function content remains the same as in the previous 'direct link' script)
    """
    topic_doc_link_errors = defaultdict(list)
    processed_docs_for_topic = defaultdict(set)
    skipped_topic_formats, skipped_phrase_formats, skipped_doc_formats = 0, 0, 0

    normalized_topic_mapping = {normalize_key(k): v for k, v in topic_mapping_data.items()}
    normalized_topics = {normalize_key(k): v for k, v in topics_data.items()}

    total_topics = len(normalized_topic_mapping)
    logging.info(f"Starting direct data load for {total_topics} broad topics...")

    with driver.session(database="neo4j") as session:
        try:
            session.execute_write(create_constraints)
        except Exception as e:
            logging.warning(f"Could not apply constraints: {e}")

        topic_count = 0
        for broad_topic_norm, phrases in normalized_topic_mapping.items():
            topic_count += 1
            if not isinstance(phrases, list):
                skipped_topic_formats += 1; continue

            if topic_count % 50 == 0: logging.info(f"Processing topic {topic_count}/{total_topics}: {broad_topic_norm}")

            for phrase_raw in phrases:
                phrase_norm = normalize_key(phrase_raw)
                if phrase_norm in normalized_topics:
                    document_list = normalized_topics[phrase_norm]
                    if not isinstance(document_list, list):
                        skipped_phrase_formats += 1; continue

                    for doc_entry in document_list:
                        if isinstance(doc_entry, dict) and len(doc_entry) == 1:
                            doc_id, doc_details = list(doc_entry.items())[0]
                            doc_id_str = str(doc_id)

                            if doc_id_str in processed_docs_for_topic[broad_topic_norm]: continue

                            if isinstance(doc_details, dict) and 'url' in doc_details and 'title' in doc_details:
                                url = doc_details.get('url', 'N/A')
                                title = doc_details.get('title', 'No Title')
                                try:
                                    session.execute_write(_create_direct_topic_doc_link_tx, broad_topic_norm, doc_id_str, url, title)
                                    processed_docs_for_topic[broad_topic_norm].add(doc_id_str)
                                except Exception as e:
                                    err_msg = f"Failed tx ({broad_topic_norm} -> {doc_id_str}): {e}"
                                    logging.error(err_msg)
                                    topic_doc_link_errors[broad_topic_norm].append(err_msg)
                            else:
                                skipped_doc_formats += 1
                                if doc_id_str not in processed_docs_for_topic[broad_topic_norm]:
                                     logging.warning(f"Skipping malformed doc details for doc_id '{doc_id_str}' under topic '{broad_topic_norm}'.")
                                     processed_docs_for_topic[broad_topic_norm].add(doc_id_str)
                        else:
                            skipped_doc_formats += 1
                            logging.warning(f"Skipping unexpected doc entry format under phrase '{phrase_norm}'. Entry: {doc_entry}")

    logging.info("Finished processing all topics for direct linking.")
    logging.info(f"Skipped {skipped_topic_formats} topics (bad format).")
    logging.info(f"Skipped docs for {skipped_phrase_formats} phrases (bad format).")
    logging.info(f"Skipped {skipped_doc_formats} doc entries (bad format).")
    if topic_doc_link_errors:
        logging.warning("Errors during direct topic-document link creation:")


if __name__ == "__main__":
    TOPIC_MAPPING_FILE = 'topic_mapping.json'
    TOPICS_FILE = 'topics.json'

    logging.info("--- Starting Neo4j RESET and Load Script ---")

    driver = None
    try:
        logging.info("--- Connecting to Neo4j ---")
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))
        driver.verify_connectivity()
        logging.info("Neo4j connection successful.")
        logging.info("--- Cleaning Up Existing Data ---")
        confirm = input("WARNING: This will delete ALL nodes and relationships from the database. Proceed? (yes/no): ")
        if confirm.lower() == 'yes':
            start_time = time.time()
            with driver.session(database="neo4j") as session:
                 session.execute_write(cleanup_neo4j_database)
            end_time = time.time()
            logging.info(f"Cleanup took {end_time - start_time:.2f} seconds.")
        else:
            logging.info("Cleanup aborted by user.")
            exit() 
        logging.info("--- Loading JSON Files ---")
        topic_mapping_data = load_json_safe(TOPIC_MAPPING_FILE)
        topics_data = load_json_safe(TOPICS_FILE)
        logging.info("--- Reloading Data into Neo4j (Direct Links) ---")
        start_time = time.time()
        load_data_to_neo4j_direct(driver, topic_mapping_data, topics_data)
        end_time = time.time()
        logging.info(f"Data loading took {end_time - start_time:.2f} seconds.")
        logging.info("--- Reset and Load Process Complete ---")

    except FileNotFoundError as e:
        logging.error(f"Critical Error: Input file not found. {e}")
    except (ValueError, RuntimeError) as e:
        logging.error(f"Critical Error during setup or loading: {e}")
    except Exception as e:
        logging.error(f"An unexpected critical error occurred: {e}", exc_info=True)
    finally:
        if driver:
            logging.info("--- Closing Neo4j Connection ---")
            driver.close()
            logging.info("Connection closed.")

