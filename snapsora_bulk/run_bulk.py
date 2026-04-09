import asyncio
import os
import aiohttp
import json
import shutil
import datetime
from api import SnapsoraFetcher
from download_core import VideoArchive

# Config
INPUT_DIR = "input"
JSON_DIR = os.path.join(INPUT_DIR, "json")
INF_DIR = "inf"
LOGS_DIR = "logs"
DOWNLOAD_DIR = "downloads"
CONCURRENT_LIMIT = 2

def setup_dirs():
    for d in [INPUT_DIR, JSON_DIR, INF_DIR, LOGS_DIR, DOWNLOAD_DIR]:
        os.makedirs(d, exist_ok=True)

def get_all_input_files():
    files = []
    if os.path.exists(INPUT_DIR):
        for f in os.listdir(INPUT_DIR):
            if f.endswith('.txt'):
                files.append({"name": f, "path": os.path.join(INPUT_DIR, f), "type": "txt"})
    
    if os.path.exists(JSON_DIR):
        for f in os.listdir(JSON_DIR):
            if f.endswith('.json'):
                files.append({"name": f, "path": os.path.join(JSON_DIR, f), "type": "json"})
    return files

def get_next_fail_folder(base_path):
    i = 1
    while os.path.exists(os.path.join(base_path, f"fail{i}")):
        i += 1
    return f"fail{i}"

def log_event(batch_name, event):
    """Save events to logs/[batch]/success.json or logs/[batch]/fail.json"""
    batch_log_dir = os.path.join(LOGS_DIR, batch_name)
    os.makedirs(batch_log_dir, exist_ok=True)
    
    event_type = "success" if "SUCCESS" in event.get('status', '').upper() or "fetch_ok" in event.get('type','') else "fail"
    log_path = os.path.join(batch_log_dir, f"{event_type}.json")
    
    logs = []
    if os.path.exists(log_path):
        try:
            with open(log_path, 'r') as f:
                logs = json.load(f)
        except: logs = []
    
    event["timestamp"] = datetime.datetime.now().isoformat()
    logs.append(event)
    
    with open(log_path, 'w') as f:
        json.dump(logs, f, indent=4)

async def fetch_and_display(session, url, index, batch_name):
    print(f"[*] Fetching Video {index} details...")
    mp4_url, video_data = await SnapsoraFetcher.get_direct_link(session, url)
    
    if mp4_url and video_data:
        title = video_data.get('title', f"video_{index:03d}")
        print(f"    [OK] Title: {title[:40]}...")
        log_event(batch_name, {"type": "fetch_ok", "id": index, "url": url})
        return {"url": mp4_url, "title": title, "id": index, "original_url": url}
    else:
        print(f"    [FAIL] Could not fetch: {url[:50]}...")
        log_event(batch_name, {"type": "fetch_fail", "id": index, "url": url})
        return None

async def main():
    setup_dirs()
    files = get_all_input_files()
    if not files:
        print(f"\n[!] Error: No files in '{INPUT_DIR}/'.")
        return

    print(f"\n--- Snapsora Bulk V5: Recovery Suite ---")
    for i, file in enumerate(files, 1):
        lbl = "[TXT]" if file['type'] == "txt" else "[JSON]"
        print(f"{i}. {lbl} {file['name']}")
    
    try:
        choice = int(input(f"\nEnter batch number: "))
        selected = files[choice-1]
    except: return

    batch_name = os.path.splitext(selected['name'])[0]
    if selected['type'] == 'json': batch_name += "_js"
    
    inf_path = os.path.join(INF_DIR, f"{batch_name}.json")
    
    # Check for Recovery
    pending_failures = []
    if os.path.exists(inf_path):
        with open(inf_path, 'r') as f:
            pending_failures = json.load(f)
    
    mode = "normal"
    if pending_failures:
        print(f"\n[!] ALERT: {len(pending_failures)} items failed in last session.")
        print("[1] Download ALL links (Normal)")
        print("[2] Retry FAILED links only (Recovery)")
        if input("\nChoice: ").strip() == "2":
            mode = "retry"

    # Load Source URLs
    source_links = []
    if mode == "retry":
        source_links = pending_failures
    else:
        # Load from file
        if selected['type'] == 'json':
            with open(selected['path'], "r", encoding="utf-8") as f:
                data = json.load(f)
                data = data['data'] if isinstance(data, dict) and 'data' in data else data
                if not isinstance(data, list): data = [data]
                source_links = [{"id": i+1, "url": d['url'].strip()} for i, d in enumerate(data) if 'url' in d]
        else:
            with open(selected['path'], "r", encoding="utf-8") as f:
                source_links = [{"id": i+1, "url": l.strip()} for i, l in enumerate(f) if l.strip()]

    # Setup Download Paths
    batch_final_dir = os.path.join(DOWNLOAD_DIR, batch_name)
    current_dest_dir = batch_final_dir
    if mode == "retry":
        fail_sub = get_next_fail_folder(batch_final_dir)
        current_dest_dir = os.path.join(batch_final_dir, fail_sub)
    
    os.makedirs(current_dest_dir, exist_ok=True)

    async with aiohttp.ClientSession() as session:
        print(f"\n[Step 1] Intercepting {len(source_links)} links...")
        
        # We fetch sequentially to be safe with rate limits
        video_list = []
        new_failures = []
        
        for item in source_links:
            v = await fetch_and_display(session, item['url'], item['id'], batch_name)
            if v:
                video_list.append(v)
            else:
                new_failures.append(item)
        
        if not video_list:
            # Sync failure file even if no downloads
            with open(inf_path, 'w') as f: json.dump(new_failures, f, indent=4)
            print("\n[!] No videos fetched. Failure state updated.")
            return

        print(f"\n[Step 2] Total {len(video_list)} videos ready in '{mode}' mode.")
        print(f"    Target: {current_dest_dir}")
        input(f"\n--- Press [ENTER] to start Download ---")

        sem = asyncio.Semaphore(CONCURRENT_LIMIT)
        
        async def download_task(video):
            async with sem:
                # Clean title for filename
                clean_title = "".join(c for c in video['title'] if c.isalnum() or c in (' ', '_', '-')).strip()
                filename = f"{video['id']:03d}_{clean_title[:30]}.mp4"
                output_path = os.path.join(current_dest_dir, filename)
                
                status, size = await VideoArchive.stream_download(session, video['url'], output_path)
                
                if status:
                    log_event(batch_name, {"status": "SUCCESS", "id": video['id'], "file": filename, "url": video['original_url']})
                    return True, video['original_url']
                else:
                    log_event(batch_name, {"status": "FAIL", "id": video['id'], "file": filename, "url": video['original_url']})
                    return False, video['original_url']

        print(f"\n[Step 3] Downloading...")
        results = await asyncio.gather(*[download_task(v) for v in video_list])
        
        # State Sync: Update inf folder
        final_failures = new_failures # Start with those that failed during fetch
        for success, orig_url in results:
            if not success:
                # Find the task info from source_links to add to failures
                for item in source_links:
                    if item['url'] == orig_url:
                        if item not in final_failures: final_failures.append(item)
                        break
        
        # Remove from failures list if they were previously there but now succeeded
        if mode == "retry":
            success_urls = {url for status, url in results if status}
            final_failures = [f for f in final_failures if f['url'] not in success_urls]

        with open(inf_path, 'w') as f:
            json.dump(final_failures, f, indent=4)

        print(f"\n" + "="*50)
        print(f"   SESSION COMPLETE")
        print(f"   Success: {sum(1 for r, u in results if r)}")
        print(f"   Failed:  {len(final_failures)}")
        if final_failures:
            print(f"   [!] Retrying later? Use Recovery Mode.")
        print("="*50)

if __name__ == "__main__":
    asyncio.run(main())
