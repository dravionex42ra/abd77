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
TODW_DIR = "input-todw"
LOGS_DIR = "logs"
DOWNLOAD_DIR = "downloads"
CONCURRENT_LIMIT = 3

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
    logs = load_json_file(log_path)
    event["timestamp"] = datetime.datetime.now().isoformat()
    logs.append(event)
    save_json_file(log_path, logs)

def load_json_file(path):
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f: return json.load(f)
        except: return []
    return []

def save_json_file(path, data):
    with open(path, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4)

async def fetch_and_display(session, url, index, batch_name):
    print(f"[*] Fetching Video {index} details...")
    try:
        mp4_url, video_data = await SnapsoraFetcher.get_direct_link(session, url)
        if mp4_url and video_data:
            title = video_data.get('title') or ""
            print(f"    [OK] Title: {str(title)[:40]}...")
            log_event(batch_name, {"type": "fetch_ok", "id": index, "url": url})
            return {"number": index, "input_link": url, "fetched_link": mp4_url, "title": title}
    except Exception as e:
        print(f"    [!] API Error: {str(e)[:50]}")
    
    print(f"    [FAIL] Could not fetch: {url[:50]}")
    log_event(batch_name, {"type": "fetch_fail", "id": index, "url": url})
    return None

async def main():
    setup_dirs()
    files = list_input_files()
    if not files:
        print(f"\n[!] Error: No files in '{INPUT_DIR}/'.")
        return

    print(f"\n" + "="*50)
    print(f"   SNAPSORA BULK V5 (DEEP RESUME EDITION)")
    print(f"="*50)

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
    
    # 1. Session Management (Resume vs Restart)
    mode = "resume"
    if metadata:
        print(f"\n[!] ALERT: Previous session for '{batch_name}' detected.")
        print("[1] Resume Session (Skip already fetched)")
        print("[2] Restart Session (Discard all progress)")
        if input("\nEnter choice [1 or 2]: ").strip() == "2":
            mode = "restart"
            print("[i] Restarting... backing up old metadata.")
            shutil.copy(todw_path, todw_path + ".bak")
            metadata = []
            save_json_file(todw_path, metadata)

    # 2. Load Source Links
    all_source = []
    if selected['type'] == 'json':
        with open(selected['path'], "r", encoding="utf-8") as f:
            data = json.load(f).get('data', [])
            all_source = [{"number": i+1, "url": d['url'].strip()} for i, d in enumerate(data) if 'url' in d]
    else:
        with open(selected['path'], "r", encoding="utf-8") as f:
            all_source = [{"number": i+1, "url": l.strip()} for i, l in enumerate(f) if l.strip()]

    # Filter links that need fetching
    processed_urls = {m['input_link'] for m in metadata if m.get('fetched_link')}
    links_to_fetch = [L for L in all_source if L['url'] not in processed_urls]

    # 3. Step 1: Fetch Phase
    async with aiohttp.ClientSession() as session:
        if links_to_fetch:
            print(f"\n[Step 1] Fetching {len(links_to_fetch)} new/missing links...")
            sem_fetch = asyncio.Semaphore(CONCURRENT_LIMIT)
            
            async def fetch_job(task):
                async with sem_fetch:
                    v = await fetch_and_display(session, task['url'], task['number'], batch_name)
                    if v:
                        nonlocal metadata
                        metadata = [m for m in metadata if m['number'] != v['number']]
                        metadata.append(v)
                        save_json_file(todw_path, metadata)
                    return v

            await asyncio.gather(*[fetch_job(t) for t in links_to_fetch])
        else:
            print(f"\n[i] Step 1 Skipped: All {len(all_source)} links already captured.")

        # 4. Step 2: Download Phase
        # Success is defined as any link we have a direct MP4 for
        success_list = [m for m in metadata if m.get('fetched_link')]
        if not success_list:
            print("\n[!] Nothing fetched. Check your internet/API.")
            return

        # Folder management
        batch_root = os.path.join(DOWNLOAD_DIR, batch_name)
        # Check if we should use a fail subfolder (only if retrying manually)
        current_dest = batch_root
        # Note: In deep resume, we don't necessarily need fail1/fail2 unless user wants it.
        # But we'll keep the option for "only failures" if they exist.
        failures = [m for m in all_source if m['url'] not in processed_urls]
        
        os.makedirs(current_dest, exist_ok=True)
        print(f"\n[Step 2] Total {len(success_list)} videos ready.")
        input(f"\n--- Press [ENTER] to start Parallel Download ({current_dest}) ---")

        sem_dw = asyncio.Semaphore(CONCURRENT_LIMIT)
        async def download_job(video):
            async with sem_dw:
                raw_title = str(video.get('title') or "")
                clean_t = "".join(c for c in raw_title if c.isalnum() or c in (' ', '_', '-')).strip()
                fname = f"{video['number']:03d}_{clean_t[:30]}.mp4"
                fpath = os.path.join(current_dest, fname)
                
                # Double check if file exists and is complete
                if os.path.exists(fpath):
                    print(f"  [i] Already exists: {fname}")
                    return True
                
                res, size = await VideoArchive.stream_download(session, video['fetched_link'], fpath)
                if res:
                    log_event(batch_name, {"status": "SUCCESS", "number": video['number'], "file": fname, "url": video['input_link']})
                else:
                    log_event(batch_name, {"status": "FAIL", "number": video['number'], "file": fname, "url": video['input_link']})
                return res

        await asyncio.gather(*[download_job(v) for v in success_list])

    print("\n" + "="*50)
    print(f"   SESSION COMPLETE (Mode: {mode.upper()})")
    print(f"   Project: {batch_name}")
    print("="*50)

if __name__ == "__main__":
    asyncio.run(main())
