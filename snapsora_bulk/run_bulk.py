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
TODW_DIR = "input-todw" # Renamed from inf to match flik
LOGS_DIR = "logs"
DOWNLOAD_DIR = "downloads"
CONCURRENT_LIMIT = 3 # Increased back for speed

def setup_dirs():
    for d in [INPUT_DIR, JSON_DIR, TODW_DIR, LOGS_DIR, DOWNLOAD_DIR]:
        os.makedirs(d, exist_ok=True)

def list_input_files():
    files = []
    if os.path.exists(INPUT_DIR):
        for f in os.listdir(INPUT_DIR):
            if f.endswith('.txt'):
                files.append({"name": f, "path": os.path.join(INPUT_DIR, f), "type": "txt"})
    
    if os.path.exists(JSON_DIR):
        for f in os.listdir(JSON_DIR):
            if f.endswith('.json'):
                files.append({"name": f, "path": os.path.join(JSON_DIR, f), "type": "json"})
    return sorted(files, key=lambda x: x["name"])

def get_next_fail_folder(base_path):
    i = 1
    while os.path.exists(os.path.join(base_path, f"fail{i}")):
        i += 1
    return f"fail{i}"

def log_event(batch_name, event):
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

def load_json_file(path):
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except: return []
    return []

def save_json_file(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=4)

async def fetch_and_display(session, url, index, batch_name):
    print(f"[*] Fetching Video {index} details...")
    mp4_url, video_data = await SnapsoraFetcher.get_direct_link(session, url)
    
    if mp4_url and video_data:
        title = video_data.get('title', f"video_{index:03d}")
        print(f"    [OK] Title: {title[:40]}...")
        log_event(batch_name, {"type": "fetch_ok", "id": index, "url": url})
        return {
            "number": index,
            "input_link": url, 
            "fetched_link": mp4_url,
            "title": title
        }
    else:
        print(f"    [FAIL] Could not fetch: {url[:50]}...")
        log_event(batch_name, {"type": "fetch_fail", "id": index, "url": url})
        return None

async def main():
    setup_dirs()
    files = list_input_files()
    if not files:
        print(f"\n[!] Error: No files in '{INPUT_DIR}/'.")
        return

    print(f"\n--- Snapsora Bulk V5 (Retry & Precision Edition) ---")
    for i, file in enumerate(files, 1):
        lbl = "[TXT]" if file['type'] == "txt" else "[JSON]"
        print(f"{i}. {lbl} {file['name']}")
    
    try:
        choice = int(input(f"\nEnter batch number: "))
        selected = files[choice-1]
    except: return

    pure_name = os.path.splitext(selected['name'])[0]
    batch_name = f"{pure_name}_js" if selected['type'] == 'json' else pure_name
    
    todw_path = os.path.join(TODW_DIR, f"{batch_name}.json")
    metadata = load_json_file(todw_path)
    
    # Identify pending or failed links from previous session
    # (Items that are not in metadata OR have no fetched_link)
    mode = "normal"
    has_failures = any(not m.get('fetched_link') for m in metadata)
    
    if metadata and has_failures:
        print(f"\n[!] ALERT: Found previously failed links.")
        print("[1] Download ALL links (Normal)")
        print("[2] Retry FAILED links only (Recovery)")
        if input("\nChoice: ").strip() == "2":
            mode = "retry"

    # Load Source URLs for this batch
    all_source_links = []
    if selected['type'] == 'json':
        with open(selected['path'], "r", encoding="utf-8") as f:
            data = json.load(f)
            data = data['data'] if isinstance(data, dict) and 'data' in data else data
            if not isinstance(data, list): data = [data]
            all_source_links = [{"number": i+1, "url": d['url'].strip()} for i, d in enumerate(data) if 'url' in d]
    else:
        with open(selected['path'], "r", encoding="utf-8") as f:
            all_source_links = [{"number": i+1, "url": l.strip()} for i, l in enumerate(f) if l.strip()]

    # Filter links to process
    target_tasks = []
    if mode == "retry":
        target_tasks = [m for m in metadata if not m.get('fetched_link')]
    else:
        # Normal mode: process links not in metadata or incomplete
        processed_urls = {m['input_link'] for m in metadata if m.get('fetched_link')}
        target_tasks = [L for L in all_source_links if L['url'] not in processed_urls]

    if not target_tasks:
        print("\n[i] All links are already processed!")
        return

    # Setup Download Paths
    batch_final_root = os.path.join(DOWNLOAD_DIR, batch_name)
    current_dest_dir = batch_final_root
    if mode == "retry":
        fail_sub = get_next_fail_folder(batch_final_root)
        current_dest_dir = os.path.join(batch_final_root, fail_sub)
    
    os.makedirs(current_dest_dir, exist_ok=True)

    async with aiohttp.ClientSession() as session:
        print(f"\n[Step 1] Intercepting {len(target_tasks)} links (Parallel Mode)...")
        
        sem_fetch = asyncio.Semaphore(CONCURRENT_LIMIT)
        
        async def fetch_job(task):
            async with sem_fetch:
                t_url = task.get('url') or task.get('input_link')
                t_num = task.get('number')
                v = await fetch_and_display(session, t_url, t_num, batch_name)
                if v:
                    # Update metadata real-time - unique by number
                    nonlocal metadata
                    metadata = [m for m in metadata if m['number'] != t_num]
                    metadata.append(v)
                    save_json_file(todw_path, metadata)
                return v

        # Run Parallel Fetch
        session_results = await asyncio.gather(*[fetch_job(t) for t in target_tasks])
        session_successes = [v for v in session_results if v]

        if not session_successes:
            print("\n[!] No new videos fetched.")
            return

        print(f"\n[Step 2] Total {len(session_successes)} videos ready.")
        input(f"\n--- Press [ENTER] to start Parallel Download ({current_dest_dir}) ---")

        sem = asyncio.Semaphore(CONCURRENT_LIMIT)
        
        async def download_task(video):
            async with sem:
                clean_title = "".join(c for c in video['title'] if c.isalnum() or c in (' ', '_', '-')).strip()
                filename = f"{video['number']:03d}_{clean_title[:30]}.mp4"
                output_path = os.path.join(current_dest_dir, filename)
                
                status, size = await VideoArchive.stream_download(session, video['fetched_link'], output_path)
                
                if status:
                    log_event(batch_name, {"status": "SUCCESS", "number": video['number'], "file": filename, "url": video['input_link']})
                    return True
                else:
                    log_event(batch_name, {"status": "FAIL", "number": video['number'], "file": filename, "url": video['input_link']})
                    return False

        print(f"\n[Step 3] Downloading to {current_dest_dir}...")
        results = await asyncio.gather(*[download_task(v) for v in session_successes])
        
        print(f"\n" + "="*50)
        print(f"   SESSION COMPLETE")
        print(f"   Success: {sum(1 for r in results if r)}")
        print(f"   Download Path: {current_dest_dir}")
        print("="*50)

if __name__ == "__main__":
    asyncio.run(main())
