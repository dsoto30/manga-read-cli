from bs4 import BeautifulSoup
import httpx
import os
import re
from urllib.parse import urljoin, urlparse
import img2pdf


def get_manga_list(client, search_query):
    url = "https://weebcentral.com/search/simple?location=main"
    response = client.post(url, data={"text": search_query})

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


def download_covers(client, results, folder="search_covers"):
    os.makedirs(folder, exist_ok=True)

    for item in results:
        safe_title = item["title"].replace(" ", "_").replace("/", "-")
        ext = "webp" if "webp" in item["img_url"] else "jpg"
        filename = f"{folder}/{safe_title}.{ext}"

        img_response = client.get(item["img_url"])
        if img_response.status_code == 200:
            with open(filename, "wb") as f:
                f.write(img_response.content)
            print(f"✓ {item['title']}")
        else:
            print(f"✗ Failed: {item['title']}")


def get_manga_series(client, series_uuid):
    url = f"https://weebcentral.com/series/{series_uuid}/full-chapter-list"
    response = client.get(url)
    soup = BeautifulSoup(response.text, "lxml")

    chapters = []
    for chapter in soup.find_all("div"):
        chapter_link = chapter.select_one("a").get("href")
        parent_span = chapter.select_one("span.grow.flex")
        if parent_span:
            chapter_title = parent_span.find("span", class_="").get_text(strip=True)
            chapters.append({
                "chapter_link": chapter_link,
                "chapter_title": chapter_title,
            })

    return chapters


def safe_filename(name):
    parts = [part.strip() for part in name.split("|") if part.strip()]
    parts = [part for part in parts if part.lower() != "weeb central"]
    name = " ".join(parts)
    name = "".join(char if char.isalnum() or char in " _-" else "_" for char in name)
    return re.sub(r"\s+", "_", name).strip("_")


def get_image_extension(image_url, response):
    path_extension = os.path.splitext(urlparse(image_url).path)[1]
    if path_extension:
        return path_extension

    content_type = response.headers.get("Content-Type", "").split(";")[0]
    return {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }.get(content_type, ".jpg")


def download_chapter(client, chapter_link, folder="downloads"):
    response = client.get(chapter_link)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "lxml")

    image_section = soup.select_one("section[hx-get*='/images']")
    if not image_section:
        print("No image loader found on this chapter page.")
        return

    images_url = urljoin(chapter_link, image_section.get("hx-get"))
    images_response = client.get(
        images_url,
        params={"reading_style": "long_strip"},
        headers={"Referer": chapter_link, "HX-Request": "true"},
    )
    images_response.raise_for_status()

    images_soup = BeautifulSoup(images_response.text, "lxml")
    image_urls = [
        urljoin(images_url, img.get("src"))
        for img in images_soup.find_all("img")
        if img.get("src")
    ]

    if not image_urls:
        print("No chapter images found.")
        return

    title = soup.select_one("title")
    chapter_folder_name = safe_filename(title.get_text(" ", strip=True) if title else "chapter")
    chapter_folder = os.path.join(folder, chapter_folder_name)
    os.makedirs(chapter_folder, exist_ok=True)

    downloaded_files = []
    for index, image_url in enumerate(image_urls, start=1):
        image_response = client.get(image_url, headers={"Referer": chapter_link})
        image_response.raise_for_status()

        extension = get_image_extension(image_url, image_response)
        filename = os.path.join(chapter_folder, f"{index:03}{extension}")
        with open(filename, "wb") as file:
            file.write(image_response.content)

        downloaded_files.append(filename)
        print(f"✓ Page {index}/{len(image_urls)}")

    create_pdf_from_images(downloaded_files, os.path.join(chapter_folder, f"{chapter_folder_name}.pdf"))

    for file in downloaded_files:
        os.remove(file)


def create_pdf_from_images(image_files, output_path):
    with open(output_path, "wb") as f:
        f.write(img2pdf.convert(image_files))


if __name__ == "__main__":
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    with httpx.Client(headers=headers) as client:
        while True:
            search_query = input("Enter manga name to search: ")
            results = get_manga_list(client, search_query)

            if not results:
                print("No results found.")
                continue

            for i, result in enumerate(results, start=1):
                print(f"{i}. {result['title']}")

            choice = input(f"\nEnter the number of the manga to download (1-{len(results)}): ")
            if not (choice.isdigit() and 1 <= int(choice) <= len(results)):
                print("Invalid input. Please enter a valid number.")
                continue

            selected_result = results[int(choice) - 1]
            print(f"\nFetching chapters for {selected_result['title']}...\n")
            chapters = get_manga_series(client, selected_result["series_uuid"])
            chapters.reverse()

            for i, chapter in enumerate(chapters, start=1):
                print(f"{i}. {chapter['chapter_title']}")

            choice = input(f"\nEnter the number of the chapter to download (1-{len(chapters)}): ")
            if not (choice.isdigit() and 1 <= int(choice) <= len(chapters)):
                print("Invalid input. Please enter a valid number.")
                continue

            selected_chapter = chapters[int(choice) - 1]
            print(f"\nDownloading {selected_chapter['chapter_title']}...\n")
            download_chapter(client, selected_chapter["chapter_link"])
