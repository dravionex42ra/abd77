import asyncio
import os
import aiohttp
import json
from api import SnapsoraFetcher
from download_core import VideoArchive

# Config
INPUT_DIR = "input"
JSON_DIR = os.path.join(INPUT_DIR, "json")
DOWNLOAD_DIR = "downloads"
CONCURRENT_LIMIT = 3

def get_all_input_files():
    """
    Scans input/ and input/json/ for .txt and .json files.
    Returns a unified list of (filename, path, type).
    """
    files = []
    
    # 1. Scan for .txt in input/
    if os.path.exists(INPUT_DIR):
        for f in os.listdir(INPUT_DIR):
            if f.endswith('.txt'):
                files.append({"name": f, "path": os.path.join(INPUT_DIR, f), "type": "txt"})
    else:
        os.makedirs(INPUT_DIR, exist_ok=True)
                
    # 2. Scan for .json in input/json/
    if os.path.exists(JSON_DIR):
        for f in os.listdir(JSON_DIR):
            if f.endswith('.json'):
                files.append({"name": f, "path": os.path.join(JSON_DIR, f), "type": "json"})
    else:
        os.makedirs(JSON_DIR, exist_ok=True)
        
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
        return {"url": mp4_url, "title": title, "id": index}
    else:
        print(f"    [FAIL] Could not fetch data for: {url}")
        return None

async def main():
    # 1. Scanning Input Files
    files = get_all_input_files()
    
    if not files:
        print(f"\n[!] Error: No .txt or .json files found in '{INPUT_DIR}/' or '{JSON_DIR}/'.")
        print(f"    Please paste your URL files there first.")
        return

    print(f"\n--- Snapsora Bulk: Select Batch File ---")
    for i, file in enumerate(files, 1):
        type_label = "[TXT]" if file['type'] == "txt" else "[JSON]"
        print(f"{i}. {type_label} {file['name']}")
    
    try:
        choice = int(input(f"\nEnter file number (1-{len(files)}): "))
        if not (1 <= choice <= len(files)):
            raise ValueError
        selected = files[choice-1]
    except (ValueError, IndexError):
        print("[!] Invalid selection. Exiting.")
        return

    # 2. Loading URLs based on Type
    urls = []
    print(f"\n[Selected: {selected['name']}] Loading URLs...")
    
    if selected['type'] == 'json':
        try:
            with open(selected['path'], "r", encoding="utf-8") as f:
                data = json.load(f)
                # Ensure data is a list
                if not isinstance(data, list):
                    data = [data]
                
                # Extract URL field
                for item in data:
                    if isinstance(item, dict) and 'url' in item:
                        urls.append(item['url'].strip().replace('.',''))
        except Exception as e:
            print(f"[!] Error reading JSON: {str(e)}")
            return
    else:
        with open(selected['path'], "r", encoding="utf-8") as f:
            urls = [line.strip().replace('.','') for line in f if line.strip()]

    if not urls:
        print(f"[!] Error: No URLs found in '{selected['name']}'. Check file content.")
        return

    # 3. Setup Subfolder for this Batch
    batch_name = os.path.splitext(selected['name'])[0]
    batch_download_dir = os.path.join(DOWNLOAD_DIR, batch_name)
    os.makedirs(batch_download_dir, exist_ok=True)

    print(f"Found {len(urls)} URLs. Starting session...")
    
    async with aiohttp.ClientSession() as session:
        print(f"\n[Step 1] Fetching video list (titles/links)...")
        tasks = [fetch_and_display(session, url, i) for i, url in enumerate(urls, 1)]
        video_list = await asyncio.gather(*tasks)
        
        video_list = [v for v in video_list if v]
        
        if not video_list:
            print("\n[!] No videos were successfully fetched. Check your URLs.")
            return

        print(f"\n[Step 2] Total {len(video_list)} videos ready.")
        input(f"\n--- Press [ENTER] to start Download ALL to /downloads/{batch_name}/ ---")

        # 4. Direct streaming to dedicated subfolder
        sem = asyncio.Semaphore(CONCURRENT_LIMIT)
        
        async def download_task(video):
            async with sem:
                clean_title = "".join(c for c in video['title'] if c.isalnum() or c in (' ', '_', '-')).strip()
                filename = f"{video['id']:03d}_{clean_title[:30]}.mp4"
                output_path = os.path.join(batch_download_dir, filename)
                return await VideoArchive.stream_download(session, video['url'], output_path)

        print(f"\n[Step 3] Downloading All to '{batch_download_dir}/' folder...")
        download_tasks = [download_task(v) for v in video_list]
        await asyncio.gather(*download_tasks)

        print(f"\n--- SESSION COMPLETE ---")

if __name__ == "__main__":
    asyncio.run(main())
