from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
import httpx
import os
from PIL import Image
import re
import shutil
import tempfile
from urllib.parse import urljoin, urlparse
import img2pdf
import questionary
import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.prompt import Prompt
from rich.table import Table

console = Console()
app = typer.Typer(add_completion=False)


# ── scraping ──────────────────────────────────────────────────────────────────

def get_manga_list(client, search_query):
    url = "https://weebcentral.com/search/simple?location=main"
    response = client.post(url, data={"text": search_query})
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "lxml")
    results = []
    for a in soup.select("a.btn.join-item"):
        title = a.select_one("div.flex-1").get_text(strip=True)
        href = a.get("href")
        series_uuid = href.split("/series/")[-1].split("/")[0]
        source = a.find("source", type="image/webp")
        img = a.find("img")
        img_url = (img.get("src") if img else None) or (source.get("srcset") if source else None) or ""
        results.append({"title": title, "series_uuid": series_uuid, "img_url": img_url, "series_url": href})
    return results


def get_manga_series(client, series_uuid):
    url = f"https://weebcentral.com/series/{series_uuid}/full-chapter-list"
    response = client.get(url)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "lxml")
    chapters = []
    for chapter in soup.find_all("div"):
        a_tag = chapter.select_one("a")
        if not a_tag:
            continue
        chapter_link = a_tag.get("href")
        parent_span = chapter.select_one("span.grow.flex")
        if parent_span:
            chapter_title = parent_span.find("span", class_="").get_text(strip=True)
            chapters.append({"chapter_link": chapter_link, "chapter_title": chapter_title})
    return chapters


# ── helpers ───────────────────────────────────────────────────────────────────

def safe_filename(name):
    parts = [part.strip() for part in name.split("|") if part.strip()]
    parts = [part for part in parts if part.lower() != "weeb central"]
    name = " ".join(parts)
    name = "".join(char if char.isalnum() or char in " _-" else "_" for char in name)
    return re.sub(r"\s+", "_", name).strip("_")


def chapter_pdf_name(chapter_title):
    match = re.search(r"(?:chapter|ch\.?)\s*(\d+(?:\.\d+)?)", chapter_title, re.I)
    if not match:
        match = re.search(r"\b(\d+(?:\.\d+)?)\b", chapter_title)
    if match:
        return f"chapter-{match.group(1).replace('.', '_')}"
    return safe_filename(chapter_title)


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


def _download_image(client, index, image_url, dest_dir, chapter_link):
    image_response = client.get(image_url, headers={"Referer": chapter_link})
    image_response.raise_for_status()
    extension = get_image_extension(image_url, image_response)
    filename = os.path.join(dest_dir, f"{index:03}{extension}")
    with open(filename, "wb") as file:
        file.write(image_response.content)
    return index, filename


def _fetch_image_urls(client, chapter_link):
    response = client.get(chapter_link)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "lxml")

    image_section = soup.select_one("section[hx-get*='/images']")
    if not image_section:
        return []

    images_url = urljoin(chapter_link, image_section.get("hx-get"))
    images_response = client.get(
        images_url,
        params={"reading_style": "long_strip"},
        headers={"Referer": chapter_link, "HX-Request": "true"},
    )
    images_response.raise_for_status()

    images_soup = BeautifulSoup(images_response.text, "lxml")
    return [
        (urljoin(images_url, img.get("src")), chapter_link)
        for img in images_soup.find_all("img")
        if img.get("src")
    ]


def _parallel_download(client, image_urls, dest_dir):
    index_to_file = {}
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Downloading pages...", total=len(image_urls))
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {
                executor.submit(_download_image, client, i, url, dest_dir, referer): i
                for i, (url, referer) in enumerate(image_urls, start=1)
            }
            for future in as_completed(futures):
                try:
                    index, filename = future.result()
                    index_to_file[index] = filename
                except Exception as e:
                    console.print(f"\n[red]Failed to download image: {e}[/red]")
                progress.advance(task)

    return [index_to_file[i] for i in sorted(index_to_file)]


def create_pdf_from_images(image_files, output_path):
    converted = []
    for path in image_files:
        if path.lower().endswith(".webp"):
            jpg_path = path[:-5] + ".jpg"
            Image.open(path).convert("RGB").save(jpg_path, "JPEG", quality=95)
            converted.append(jpg_path)
        else:
            converted.append(path)
    with open(output_path, "wb") as f:
        f.write(img2pdf.convert(converted))


# ── actions ───────────────────────────────────────────────────────────────────

def download_chapter(client, chapter_link, manga_title, chapter_title, folder="downloads"):
    manga_folder = os.path.join(folder, safe_filename(manga_title))
    pdf_path = os.path.join(manga_folder, f"{chapter_pdf_name(chapter_title)}.pdf")

    if os.path.exists(pdf_path):
        if not typer.confirm(f"{pdf_path} already exists. Overwrite?", default=False):
            console.print("[yellow]Skipped.[/yellow]")
            return

    with console.status("Fetching page list..."):
        image_urls = _fetch_image_urls(client, chapter_link)

    if not image_urls:
        console.print("[red]No images found on this chapter page.[/red]")
        return

    os.makedirs(manga_folder, exist_ok=True)
    temp_dir = tempfile.mkdtemp()
    try:
        files = _parallel_download(client, image_urls, temp_dir)
        create_pdf_from_images(files, pdf_path)
        console.print(f"[green]Saved:[/green] {pdf_path}")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def read_chapter(client, chapter_link, chapter_title):
    try:
        from term_image.image import from_file
    except ImportError:
        console.print("[red]term-image not found.[/red] Run: venv/bin/pip install term-image")
        return

    import readchar

    with console.status("Fetching page list..."):
        image_urls = _fetch_image_urls(client, chapter_link)

    if not image_urls:
        console.print("[red]No images found on this chapter page.[/red]")
        return

    temp_dir = tempfile.mkdtemp()
    try:
        files = _parallel_download(client, image_urls, temp_dir)

        current = 0
        while True:
            console.clear()
            console.print(Panel(
                f"[bold]{chapter_title}[/bold]  —  Page {current + 1} of {len(files)}\n"
                "[dim]← · prev    → · next    Enter · quit[/dim]",
                border_style="cyan",
            ))
            try:
                from_file(files[current]).draw()
            except Exception as e:
                console.print(f"[red]Could not render image:[/red] {e}")
                console.print("[dim]Your terminal may not support inline images. Try iTerm2 or Kitty.[/dim]")

            key = readchar.readkey()
            if key == readchar.key.ENTER:
                break
            elif key == readchar.key.LEFT and current > 0:
                current -= 1
            elif key == readchar.key.RIGHT and current < len(files) - 1:
                current += 1
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ── TUI ───────────────────────────────────────────────────────────────────────

_BACK = object()


def _pick(items, label_key, title, default=None):
    choices = [questionary.Choice(title=item[label_key], value=item) for item in items]
    choices.append(questionary.Choice(title="← Back", value=_BACK))
    result = questionary.select(title, choices=choices, use_shortcuts=False, default=default).ask()
    if result is None or result is _BACK:
        return None
    return result


@app.command()
def main():
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    transport = httpx.HTTPTransport(retries=3)

    with httpx.Client(
        headers=headers,
        timeout=httpx.Timeout(30.0, connect=10.0),
        transport=transport,
        http2=True,
    ) as client:
        while True:
            console.print(Panel("[bold cyan]Manga Reader[/bold cyan]", border_style="cyan", expand=False))

            search_query = Prompt.ask("[cyan]Search[/cyan]")
            with console.status("Searching..."):
                try:
                    results = get_manga_list(client, search_query)
                except Exception as e:
                    console.print(f"[red]Search failed:[/red] {e}")
                    continue

            if not results:
                console.print("[yellow]No results found.[/yellow]")
                continue

            selected_manga = _pick(results, "title", "Search Results")
            if not selected_manga:
                continue

            with console.status(f"Fetching chapters for [bold]{selected_manga['title']}[/bold]..."):
                try:
                    chapters = get_manga_series(client, selected_manga["series_uuid"])
                    chapters.reverse()
                except Exception as e:
                    console.print(f"[red]Failed to fetch chapters:[/red] {e}")
                    continue

            if not chapters:
                console.print("[yellow]No chapters found.[/yellow]")
                continue

            last_chapter = None
            while True:
                selected_chapter = _pick(chapters, "chapter_title", selected_manga["title"], default=last_chapter)
                if not selected_chapter:
                    break
                last_chapter = selected_chapter

                mode = questionary.select(
                    "What do you want to do?",
                    choices=["download", "read"],
                ).ask()

                if mode is None:
                    continue
                elif mode == "download":
                    download_chapter(
                        client,
                        selected_chapter["chapter_link"],
                        selected_manga["title"],
                        selected_chapter["chapter_title"],
                    )
                else:
                    read_chapter(
                        client,
                        selected_chapter["chapter_link"],
                        selected_chapter["chapter_title"],
                    )


def cli():
    app()


if __name__ == "__main__":
    cli()
