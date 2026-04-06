import asyncio
import os
import aiohttp
from api import SnapsoraFetcher
from download_core import VideoArchive

# Config
INPUT_FILE = "input_urls.txt"
DOWNLOAD_DIR = "downloads"
CONCURRENT_LIMIT = 3

async def fetch_and_display(session, url, index):
    """
    Mimics the website's 'Fetch' action.
    """
    print(f"[*] Fetching Video {index} details...")
    mp4_url, video_data = await SnapsoraFetcher.get_direct_link(session, url)
    
    if mp4_url and video_data:
        title = video_data.get('title', f"video_{index:03d}")
        print(f"    [OK] Title: {title[:60]}...")
        return {"url": mp4_url, "title": title, "id": index}
    else:
        print(f"    [FAIL] Could not fetch data for: {url}")
        return None

async def main():
    if not os.path.exists(INPUT_FILE):
        with open(INPUT_FILE, "w") as f: pass
        print(f"(!) Please paste Sora URLs in '{INPUT_FILE}'.")
        return

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    with open(INPUT_FILE, "r") as f:
        urls = [line.strip().replace('.','') for line in f if line.strip()]

    if not urls:
        print(f"(!) '{INPUT_FILE}' is empty.")
        return

    print(f"\n--- Snapsora Bulk Downloader (mimicking UI) ---")
    print(f"Found {len(urls)} URLs.")
    
    async with aiohttp.ClientSession() as session:
        print(f"\n[Step 1] Fetching video list...")
        tasks = [fetch_and_display(session, url, i) for i, url in enumerate(urls, 1)]
        video_list = await asyncio.gather(*tasks)
        
        video_list = [v for v in video_list if v]
        
        if not video_list:
            print("\n[!] No videos were successfully fetched. Check your URLs and connectivity.")
            return

        print(f"\n[Step 2] Total {len(video_list)} videos ready.")
        input("\n--- Press [ENTER] to start 'Download All' (Direct to Folder) ---")

        sem = asyncio.Semaphore(CONCURRENT_LIMIT)
        
        async def download_task(video):
            async with sem:
                clean_title = "".join(c for c in video['title'] if c.isalnum() or c in (' ', '_', '-')).strip()
                filename = f"{video['id']:03d}_{clean_title[:30]}.mp4"
                output_path = os.path.join(DOWNLOAD_DIR, filename)
                return await VideoArchive.stream_download(session, video['url'], output_path)

        print(f"\n[Step 3] Downloading All to '{DOWNLOAD_DIR}/' folder...")
        download_tasks = [download_task(v) for v in video_list]
        await asyncio.gather(*download_tasks)

        print(f"\n--- SESSION COMPLETE ---")

if __name__ == "__main__":
    asyncio.run(main())
