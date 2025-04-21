from utils.opensearch import OS_CLIENT, VECTOR_INDEX_NAME
import json
from collections import defaultdict

client = OS_CLIENT

def execute_search(query_body):

    response = client.search(index=VECTOR_INDEX_NAME, body=query_body)

    results = {}
    if response and "hits" in response and "hits" in response["hits"]:
        for hit in response["hits"]["hits"]:
            if hit.get("_source"):
                entities = hit["_source"]['entities']
                topics = hit["_source"]['topics']
                _id = hit['_id']
                topic_list = []
                entity_list = []
                for t in topics:
                  topic_list.append(t.get('text'))
                for e in entities:
                  entity_list.append(e.get('text'))
                results[_id] = {
                    'topics': topic_list,
                    'entities': entity_list,
                    'url': hit["_source"]["pr_url"],
                    'release_date': hit["_source"]["pr_date"],
                    'title': hit["_source"]["pr_title"]
                  }
    return results
                
        
def search():
    query_body = {
        "query": {
            "bool": {
                "should": [],
                "minimum_should_match": 0,
            }
        },
        "size": 4000,
    }
    return execute_search(query_body)

# results = search()
# with open("results.json", "w") as f:
#    json.dump(results, f)

results = json.load(open('results.json'))
topic_dict = defaultdict(list)
for k, v in results.items():
  print(k, v)
  for ik, iv in v.items():
    if ik == 'topics':
      for t in iv:
        doc = {
           k:{
            "url": v['url'],
           "title": v["title"],
           }
        }
        topic_dict[t].append(doc)

# words = list(topicset)
# topic_dict['uniqueTermWords'] = words
result = dict(sorted(topic_dict.items()))
with open('topics.json', 'w') as fp:
  json.dump(result, fp, indent=4)