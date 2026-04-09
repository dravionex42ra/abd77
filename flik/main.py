import os
import json
import time
import datetime
from api_client import FliflikAPI
from downloader import VideoDownloader

# Directories
INPUT_DIR = "input"
JSON_INPUT_DIR = os.path.join(INPUT_DIR, "json")
TODW_DIR = "input-todw"
INF_DIR = "inf"
LOGS_DIR = "logs"
DOW_DIR = "dow"

def setup_dirs():
    for d in [INPUT_DIR, JSON_INPUT_DIR, TODW_DIR, INF_DIR, LOGS_DIR, DOW_DIR]:
        os.makedirs(d, exist_ok=True)

def list_input_files():
    """Lists both .txt and .json files (from json subfolder)."""
    txt_files = [{"name": f, "type": "txt", "path": os.path.join(INPUT_DIR, f)} 
                 for f in os.listdir(INPUT_DIR) if f.endswith(".txt")]
    
    json_files = []
    if os.path.exists(JSON_INPUT_DIR):
        json_files = [{"name": f, "type": "json", "path": os.path.join(JSON_INPUT_DIR, f)} 
                      for f in os.listdir(JSON_INPUT_DIR) if f.endswith(".json")]
    
    return sorted(txt_files + json_files, key=lambda x: x["name"])

def load_links(file_info):
    """Loads links from either TXT or JSON based on file type."""
    links = []
    path = file_info["path"]
    
    if file_info["type"] == "txt":
        with open(path, 'r', encoding='utf-8') as f:
            raw_links = [line.strip() for line in f if line.strip().startswith("http")]
            links = [{"number": i+1, "url": url} for i, url in enumerate(raw_links)]
    
    elif file_info["type"] == "json":
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Support the specific format: {"data": [{"url": "..."}]}
            if "data" in data and isinstance(data["data"], list):
                for i, item in enumerate(data["data"]):
                    if "url" in item:
                        links.append({"number": i+1, "url": item["url"]})
    
    return links

def get_next_fail_folder(base_path):
    i = 1
    while os.path.exists(os.path.join(base_path, f"fail{i}")):
        i += 1
    return f"fail{i}"

def log_event(filename, event):
    base_log_dir = os.path.join(LOGS_DIR, filename)
    os.makedirs(base_log_dir, exist_ok=True)
    
    event_type = "success" if "success" in event["type"] else "fail"
    log_path = os.path.join(base_log_dir, f"{event_type}.json")
    
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
        with open(path, 'r') as f:
            return json.load(f)
    return []

def save_json_file(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=4)

def main():
    setup_dirs()
    print("="*60)
    print("   FLIFLIK HYBRID DOWNLOADER (TXT & JSON SUPPORT)")
    print("="*60)
    
    # 1. Selection
    all_files = list_input_files()
    if not all_files:
        print("[!] No .txt or .json files found.")
        return

    print("\nSelect an input file:")
    for i, f in enumerate(all_files, 1):
        suffix = "(JSON)" if f["type"] == "json" else "(TXT)"
        print(f"[{i}] {f['name']} {suffix}")
    
    try:
        choice = int(input("\nEnter number: ")) - 1
        selected_file_info = all_files[choice]
    except (ValueError, IndexError):
        print("[!] Invalid selection.")
        return

    # Basename Logic with _js suffix for JSON
    pure_name = os.path.splitext(selected_file_info["name"])[0]
    basename = f"{pure_name}_js" if selected_file_info["type"] == "json" else pure_name
    
    metadata_path = os.path.join(TODW_DIR, f"{basename}.json")
    failure_path = os.path.join(INF_DIR, f"{basename}.json")
    final_download_root = os.path.join(DOW_DIR, basename)

    # 2. Check for Previous Sessions
    failures = load_json_file(failure_path)
    metadata = load_json_file(metadata_path)
    
    mode = "normal"
    if failures:
        print(f"\n[!] ALERT: {len(failures)} tasks failed previously.")
        print("Choose Mode:")
        print("[1] Normal (Process new links)")
        print("[2] Recovery (Retry failed links only)")
        
        if input("\nEnter choice [1 or 2]: ").strip() == "2":
            mode = "retry"

    # 3. Load Application Links
    all_links = load_links(selected_file_info)
    if not all_links:
        print(f"[!] No valid links found in {selected_file_info['name']}")
        return

    # 4. Filter Target Tasks
    target_tasks = []
    if mode == "retry":
        target_tasks = failures
        failures = [] # Reset for this session
    else:
        fetched_urls = {item["input_link"] for item in metadata}
        target_tasks = [L for L in all_links if L["url"] not in fetched_urls]

    if not target_tasks:
        print("\n[i] Everything is already up-to-date!")
        return

    print(f"\n--- STEP 1: Fetching Links ({len(target_tasks)} pending) ---")
    api = FliflikAPI()
    
    session_successes = []
    current_failures = []
    
    for task in target_tasks:
        idx = task["number"]
        url = task["url"]
        
        print(f"[{idx}] Intercepting: {url[:55]}...")
        direct_link = api.get_video_link(url)
        
        if direct_link:
            print("  [+] Link Captured!")
            entry = {"number": idx, "input_link": url, "fetched_link": direct_link}
            session_successes.append(entry)
            metadata.append(entry)
            save_json_file(metadata_path, metadata)
            log_event(basename, {"type": "fetch_success", "number": idx, "url": url})
            time.sleep(0.5)
        else:
            print("  [!] API Failure.")
            current_failures.append(task)
            log_event(basename, {"type": "fetch_fail", "number": idx, "url": url})
            time.sleep(2)

    save_json_file(failure_path, current_failures)

    # 5. Download Phase
    if not session_successes:
        print("\n[!] No new videos to download in this session.")
        return

    dest_path = final_download_root
    if mode == "retry":
        fail_dir = get_next_fail_folder(final_download_root)
        dest_path = os.path.join(final_download_root, fail_dir)
        print(f"\n[i] Retry files will be saved in: {dest_path}")

    print(f"\n--- STEP 2: Downloading ({len(session_successes)} items) ---")
    dw = VideoDownloader(dest_path)
    
    for item in session_successes:
        fname = f"video_{item['number']:03d}.mp4"
        print(f"\n[Task {item['number']}]: {fname}")
        if dw.download(item["fetched_link"], fname):
            log_event(basename, {"type": "download_success", "number": item["number"], "file": fname})
        else:
            log_event(basename, {"type": "download_fail", "number": item["number"], "file": fname})

    print("\n" + "="*60)
    print("   SORA HYBRID SESSION COMPLETED!")
    print(f"   Final Path: {dest_path}")
    print("="*60)

if __name__ == "__main__":
    main()
