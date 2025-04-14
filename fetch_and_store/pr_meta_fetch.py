import requests
from bs4 import BeautifulSoup
import concurrent.futures
import os
from datetime import datetime
import json
import os


def writeToJSONFile(path, fileName, data):
    # Ensure the directory exists
    if not os.path.exists(path):
        os.makedirs(path)
    filePathNameWExt = os.path.join(path, f"{fileName}.json")
    with open(filePathNameWExt, "w+") as fp:
        json.dump(data, fp, indent=4)


def fetch_links(url):
    root_path = "https://larson.house.gov"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")
        linkset = set()
        for a in soup.find_all("a", href=True):
            if a["href"].startswith("/media-center/press-releases/"):
                url = root_path + a["href"]
                linkset.add(url)
        return list(linkset)
    except requests.exceptions.RequestException as e:
        print(f"Request error for {url}: {e}")
        return []
    except Exception as e:
        print(f"An error occurred for {url}: {e}")
        return []


def fetch_press_release_info(url):
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")

        # Extract title
        title = soup.find("h1").text.strip() if soup.find("h1") else "No Title Found"

        # Extract date
        date_span = (
            soup.find("div", class_="page__content evo-page-content")
            .contents[0]
            .find("div", class_="col-auto")
        )
        date = date_span.text.strip() if date_span else "No Date Found"
        try:
            date_obj = datetime.strptime(date, "%B %d, %Y")
            date = date_obj.strftime("%Y-%m-%d")
        except ValueError:
            pass

        return {"pr_url": url, "pr_title": title, "pr_date": date}
    except requests.exceptions.RequestException as e:
        print(f"Request error for {url}: {e}")
        return None
    except Exception as e:
        print(f"An error occurred for {url}: {e}")
        return None


def fetch_all_links(base_url, max_pages=326):
    all_links = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_url = {
            executor.submit(fetch_links, f"{base_url}?page={page}"): page
            for page in range(1, max_pages + 1)
        }
        for future in concurrent.futures.as_completed(future_to_url):
            links = future.result()
            if links:
                all_links.extend(links)
            else:
                break 
    return all_links


if __name__ == "__main__":
    base_url = "https://larson.house.gov/media-center/press-releases"
    all_links = fetch_all_links(base_url)
    data = list()
    if all_links:
        print("Press Releases found:")
        for link in all_links:
            info = fetch_press_release_info(link)
            if info:
                data.append(info)
        print("Writing to JSON file...")
        writeToJSONFile("./", "press_releases", data)
    else:
        print("No links found or an error occurred.")
