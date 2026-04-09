import asyncio
import os
import aiohttp
import json
import shutil
from api import SnapsoraFetcher
from download_core import VideoArchive

# Config
INPUT_DIR = "input"
JSON_DIR = os.path.join(INPUT_DIR, "json")
FAIL_DIR = os.path.join(INPUT_DIR, "fail")
DOWNLOAD_DIR = "downloads"
CONCURRENT_LIMIT = 2 # Reduced for stability in Termux

def get_all_input_files():
    """
    Scans input/ and input/json/ for .txt and .json files.
    """
    files = []
    if os.path.exists(INPUT_DIR):
        for f in os.listdir(INPUT_DIR):
            if f.endswith('.txt'):
                files.append({"name": f, "path": os.path.join(INPUT_DIR, f), "type": "txt"})
    else: os.makedirs(INPUT_DIR, exist_ok=True)
    if not os.path.exists(JSON_DIR): os.makedirs(JSON_DIR, exist_ok=True)
    if not os.path.exists(FAIL_DIR): os.makedirs(FAIL_DIR, exist_ok=True)
    
    for f in os.listdir(JSON_DIR):
        if f.endswith('.json'):
            files.append({"name": f, "path": os.path.join(JSON_DIR, f), "type": "json"})
    return files

async def fetch_and_display(session, url, index):
    """
    Mimics the website's 'Fetch' action.
    """
    print(f"[*] Fetching Video {index} details...")
    mp4_url, video_data = await SnapsoraFetcher.get_direct_link(session, url)
    if mp4_url and video_data:
        title = video_data.get('title', f"video_{index:03d}")
        print(f"    [OK] Title: {title[:50]}...")
        return {"url": mp4_url, "title": title, "id": index, "original_url": url}
    else:
        print(f"    [FAIL] Could not fetch data for: {url}")
        return None

async def main():
    files = get_all_input_files()
    if not files:
        print(f"\n[!] Error: No files in '{INPUT_DIR}/'.")
        return

    print(f"\n--- Snapsora Bulk V4: Select Batch ---")
    for i, file in enumerate(files, 1):
        lbl = "[TXT]" if file['type'] == "txt" else "[JSON]"
        print(f"{i}. {lbl} {file['name']}")
    
    try:
        choice = int(input(f"\nEnter batch number (1-{len(files)}): "))
        selected = files[choice-1]
    except (ValueError, IndexError): return

    # Load URLs
    urls = []
    if selected['type'] == 'json':
        with open(selected['path'], "r", encoding="utf-8") as f:
            data = json.load(f)
            data = data['data'] if isinstance(data, dict) and 'data' in data else data
            if not isinstance(data, list): data = [data]
            urls = [d['url'].strip().replace('.','') for d in data if 'url' in d]
    else:
        with open(selected['path'], "r", encoding="utf-8") as f:
            urls = [l.strip().replace('.','') for l in f if l.strip()]

    if not urls: return

    # Setup Paths
    batch_name = os.path.splitext(selected['name'])[0]
    batch_download_dir = os.path.join(DOWNLOAD_DIR, batch_name)
    os.makedirs(batch_download_dir, exist_ok=True)
    
    # Sub-folder for partial failures
    batch_fail_folder = os.path.join(batch_download_dir, "fail")
    os.makedirs(batch_fail_folder, exist_ok=True)

    failed_links = []
    
    async with aiohttp.ClientSession() as session:
        print(f"\n[Step 1] Fetching video list...")
        tasks = [fetch_and_display(session, url, i) for i, url in enumerate(urls, 1)]
        video_list = [v for v in await asyncio.gather(*tasks) if v]
        
        if not video_list: return
        print(f"\n[Step 2] Total {len(video_list)} videos ready.")
        input(f"\n--- Press [ENTER] to start 'Download ALL' (Stability V4 Mode) ---")

        sem = asyncio.Semaphore(CONCURRENT_LIMIT)
        
        async def download_task(video):
            async with sem:
                clean_title = "".join(c for c in video['title'] if c.isalnum() or c in (' ', '_', '-')).strip()
                filename = f"{video['id']:03d}_{clean_title[:30]}.mp4"
                output_path = os.path.join(batch_download_dir, filename)
                
                # Check for resume and download
                status, size = await VideoArchive.stream_download(session, video['url'], output_path)
                
                if not status: # Still fails after retries
                    failed_links.append(video['original_url'])
                    # Move partial file to fail folder
                    if os.path.exists(output_path):
                        dest_fail_path = os.path.join(batch_fail_folder, filename)
                        shutil.move(output_path, dest_fail_path)
                    return False
                return True

        print(f"\n[Step 3] Downloading All to '{batch_download_dir}/' folder...")
        results = await asyncio.gather(*[download_task(v) for v in video_list])

        # Logging Failures
        if failed_links:
            fail_file_path = os.path.join(FAIL_DIR, f"{batch_name}_failed.txt")
            with open(fail_file_path, "w") as f:
                f.write("\n".join(failed_links))
            print(f"\n[!] WARNING: {len(failed_links)} videos failed after all retries.")
            print(f"    Failed links saved in: {fail_file_path}")
            print(f"    Partial files moved to: {batch_fail_folder}/")
        
        print(f"\n--- SESSION COMPLETE (Total: {len(video_list)} | Success: {sum(1 for r in results if r)}) ---")

if __name__ == "__main__":
    asyncio.run(main())
