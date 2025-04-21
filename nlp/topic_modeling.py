import re
import json
from sentence_transformers import SentenceTransformer
import numpy as np
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import pdist, squareform, cosine
from collections import defaultdict
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import normalize
from collections import defaultdict

def clean_text(text):
    if not isinstance(text, str): return ""
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

words_phrases = json.load(open('topics.json', 'r'))['uniqueTermWords']
processed_phrases = list(set(clean_text(p) for p in words_phrases if clean_text(p)))
print(f"Processing {len(processed_phrases)} unique non-empty phrases.")
print("Loading embedding model...")
model = SentenceTransformer('all-mpnet-base-v2')
device = 'cuda'
print("Generating embeddings...")
embeddings = model.encode(processed_phrases, show_progress_bar=True, device=device)
embeddings = normalize(embeddings)
print(f"Generated {embeddings.shape[0]} embeddings of dimension {embeddings.shape[1]}.")

print("Performing hierarchical clustering...")
linked = linkage(embeddings, method='complete', metric='cosine')
print("Clustering complete.")

num_topics = 80
topic_labels = fcluster(linked, t=num_topics, criterion='maxclust')

print(f"Assigned {max(topic_labels)} broad topics.")
topic_map = defaultdict(list)
phrase_idx_assignments = {}

for i, phrase in enumerate(processed_phrases):
    topic_id = topic_labels[i]
    topic_map[topic_id].append(i)
    phrase_idx_assignments[i] = {'topic_id': topic_id}


def get_cluster_label_by_centroid(cluster_indices, all_embeddings, all_phrases):
    if not cluster_indices:
        return "Unknown"
    cluster_embeddings = all_embeddings[cluster_indices]

    if cluster_embeddings.shape[0] == 1:
        return all_phrases[cluster_indices[0]]

    centroid = np.mean(cluster_embeddings, axis=0)
    similarities = cosine_similarity(centroid.reshape(1, -1), cluster_embeddings)[0]
    closest_idx_in_cluster = np.argmax(similarities)
    original_index = cluster_indices[closest_idx_in_cluster]
    return all_phrases[original_index]

print("Determining Topic Labels...")
topic_labels_named = {
    tid: get_cluster_label_by_centroid(indices, embeddings, processed_phrases)
    for tid, indices in topic_map.items()
}


final_phrase_hierarchy = {}
for i, phrase in enumerate(processed_phrases):
    assignment = phrase_idx_assignments[i]
    topic_id = assignment['topic_id']
    final_phrase_hierarchy[phrase] = {
        'topic_id': topic_id,
        'topic_label': topic_labels_named.get(topic_id, "Unknown Topic")
    }


count = 0
mapping = defaultdict(list)
for phrase, assignment in final_phrase_hierarchy.items():
    mapping[assignment['topic_label']].append(phrase)

with open('topic_mapping2.json', 'w') as fp:
    json.dump(mapping, fp, indent=4)