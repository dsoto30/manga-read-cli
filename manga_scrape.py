from bs4 import BeautifulSoup
import requests
import os
import json




def get_manga_list(search_query):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }

    data = {"text": search_query}

    url = "https://weebcentral.com/search/simple?location=main"
    response = requests.post(url, headers=headers, data=data)
    
    soup = BeautifulSoup(response.text, "lxml")

    results = []

    for a in soup.select("a.btn.join-item"):
        title = a.select_one("div.flex-1").get_text(strip=True)
        href = a.get("href")

        series_uuid = href.split("/series/")[-1].split("/")[0]

        source = a.find("source", type="image/webp")
        img = a.find("img")
        img_url = img.get("src") if img else source.get("srcset")
        

        results.append({
            "title": title,
            "series_uuid": series_uuid,
            "img_url": img_url,
            "series_url": href,
        })

    return results


def download_covers(results, folder="search_covers"):
    os.makedirs(folder, exist_ok=True)
    headers = {"User-Agent": "Mozilla/5.0"}

    for item in results:
        safe_title = item["title"].replace(" ", "_").replace("/", "-")
        ext = "webp" if "webp" in item["img_url"] else "jpg"
        filename = f"{folder}/{safe_title}.{ext}"

        img_response = requests.get(item["img_url"], headers=headers)
        if img_response.status_code == 200:
            with open(filename, "wb") as f:
                f.write(img_response.content)
            print(f"✓ {item['title']}")
        else:
            print(f"✗ Failed: {item['title']}")

def get_manga_series(series_uuid):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }

    full_chapter_list_url = f"https://weebcentral.com/series/{series_uuid}/full-chapter-list"

    response = requests.get(full_chapter_list_url, headers=headers)
    soup = BeautifulSoup(response.text, "lxml")

    for chapter in soup.find_all("div"):
        parent_span = chapter.select_one("span.grow.flex")
        if parent_span:
            chapter_title = parent_span.find("span", class_="").get_text(strip=True)
            print(chapter_title)
    


if __name__ == "__main__":
    search_query = input("Enter manga name to search: ")
    results = get_manga_list(search_query)
    # print(json.dumps(results, indent=4))
    # download_covers(results, folder="search_covers")
    for i, result in enumerate(results):
        print(f"{i+1}. {result['title']}")

    if len(results) == 0:
        print("No results found.")
        exit()

    while True:
        choice = input(f"Enter the number of the manga to download ({1}-{len(results)}) or 'q' to quit: ")
        if choice == "q":
            break
        if choice.isdigit() and 1 <= int(choice) <= len(results):
            selected_result = results[int(choice) - 1]
            print(f"Sending GET request to {selected_result['series_url']}...")
            get_manga_series(selected_result['series_uuid'])
            
            # download_covers([selected_result], folder="search_covers")
            break
        print("Invalid input. Please enter a valid number or 'q' to quit.")