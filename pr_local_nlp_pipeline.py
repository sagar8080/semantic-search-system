import re
from collections import Counter
import spacy
import nltk
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.decomposition import LatentDirichletAllocation
from summa import keywords
from transformers import pipeline
import cohere
from opensearchpy import OpenSearch
from utils import *

# nltk.download('punkt')
# nltk.download('stopwords')
# nltk.download('wordnet')

# Load NLP models
nlp = spacy.load("en_core_web_sm")  # For NER
summarizer = pipeline("summarization", model="facebook/bart-large-cnn")
client = get_os_client()


# Preprocessing function
def preprocess_text(text):
    # Noise removal
    text = re.sub(r"[^a-zA-Z0-9\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()

    # Lowercase conversion
    text = text.lower()

    # Tokenization
    tokens = word_tokenize(text)

    # Stopword removal
    stop_words = set(stopwords.words("english"))
    tokens = [word for word in tokens if word not in stop_words]

    # Lemmatization
    lemmatizer = WordNetLemmatizer()
    tokens = [lemmatizer.lemmatize(token) for token in tokens]

    return " ".join(tokens)


# Topic modeling using BERTopic
def perform_topic_modeling(text, num_topics=3):
    try:
        vectorizer = CountVectorizer(stop_words="english")
        count_matrix = vectorizer.fit_transform([text])

        lda_model = LatentDirichletAllocation(n_components=num_topics, random_state=42)
        lda_topics = lda_model.fit_transform(count_matrix)

        feature_names = vectorizer.get_feature_names_out()
        topics = []

        for topic_idx, topic in enumerate(lda_model.components_):
            top_words = [feature_names[i] for i in topic.argsort()[: -10 - 1 : -1]]
            topics.append(f"Topic {topic_idx}: {', '.join(top_words)}")

        return topics
    except Exception as e:
        print(f"Error performing LDA topic modeling: {e}")
        return None


# Named Entity Recognition (NER)
def extract_entities(text, top_n=5):
    # Process the text using Spacy
    doc = nlp(text)

    # Extract all entities
    all_entities = [ent.text for ent in doc.ents]

    # Count entity frequencies
    entity_counter = Counter(all_entities)

    # Get the top N entities by frequency
    top_entities = entity_counter.most_common(top_n)

    # Format the output with labels
    formatted_entities = [
        {
            "text": entity,
            "label": [ent.label_ for ent in doc.ents if ent.text == entity][0],
            "frequency": freq,
        }
        for entity, freq in top_entities
    ]

    return formatted_entities


# Keyword extraction using TextRank
def extract_keywords(text):
    return keywords.keywords(text).split("\n")


# Summarization using BART model
def generate_summary(text):
    summary = summarizer(text, max_length=150, min_length=50, do_sample=False)
    return summary[0]["summary_text"]


# Main NLP pipeline function
def process_and_store_document(info):
    raw_text = info["content"]
    pr_url = info["pr_url"]
    pr_title = info["pr_title"]
    pr_date = info["pr_date"]

    # Step 1: Preprocessing
    # cleaned_text = preprocess_text(raw_text)

    # Step 2: Topic Modeling (optional for single input but included for demonstration)
    topics = perform_topic_modeling(raw_text)

    # Step 3: Named Entity Recognition (NER)
    entities = extract_entities(raw_text)

    # Step 4: Keyword Extraction
    keywords_list = extract_keywords(raw_text)

    # Step 5: Summarization
    summary = generate_summary(raw_text)

    # Prepare document for storage in OpenSearch vector index
    document = {
        "pr_url": pr_url,  
        "pr_date": pr_date,
        "pr_title": pr_title,
        "content": raw_text,
        "summary": summary,
        "topics": topics,
        "entities": entities,
        # "embedding": embedding,
        "processed": True,
    }
    return document


def search_content_by_date_range(
    start_year, start_month, end_year, end_month, index_name=PR_META_RAW_IDX
):
    # Construct the date range dynamically
    start_date = f"{start_year}-{start_month:02d}-01"
    # Calculate the end date as the first day of the next month
    if end_month == 12:
        end_date = f"{end_year + 1}-01-01"
    else:
        end_date = f"{end_year}-{end_month + 1:02d}-01"

    query = {
        "bool": {
            "filter": [
                {
                    "range": {"pr_date": {"gte": start_date, "lt": end_date}}
                }  # Filter by date range
            ]
        }
    }

    try:
        response = client.search(
            index=index_name,
            body={
                "query": query,
                "_source": [
                    "pr_url",
                    "pr_title",
                    "pr_date",
                    "content",
                ],  # Specify fields to return
                "size": 10000,  # Fetch up to 10,000 results
            },
        )
        return response["hits"]["hits"]
    except Exception as e:
        print(f"Error searching entries by date range: {e}")
        return []


if __name__ == "__main__":
    info = search_content_by_date_range(2006, 5, 2006, 6)
    text_for_topic_modeling = list()
    for i in info:
        data = i["_source"]
        result = process_and_store_document(data)
        print(result)
        break
