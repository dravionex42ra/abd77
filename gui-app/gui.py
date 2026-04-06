import os
import asyncio
import argparse
import aiohttp
from archiver_core import SoraCore

def parse_range(range_str, total):
    if range_str.lower() == 'all': return list(range(1, total+1))
    indices = set()
    parts = range_str.replace(' ', '').split(',')
    for part in parts:
        if '-' in part:
            try:
                start, end = map(int, part.split('-'))
                indices.update(range(start, end + 1))
            except: continue
        else:
            try: indices.add(int(part))
            except: continue
    return sorted([i for i in indices if 1 <= i <= total])

async def main():
    INPUT_DIR = "input"
    OUT_BASE = "out"
    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(OUT_BASE, exist_ok=True)
    os.makedirs("logs", exist_ok=True)

    files = [f for f in os.listdir(INPUT_DIR) if f.endswith('.txt')]
    
    print("\n--- Sora CLI Batch Selector ---")
    print("0. [Paste Single Sora URL]")
    for i, f in enumerate(files, 1):
        print(f"{i}. {f}")
    
    try:
        choice = input("\nEnter choice (0 or batch number): ")
        if choice == '0':
            url = input("\nPaste Sora URL: ").strip()
            if not url.startswith('http'):
                print("Invalid URL.")
                return
            
            manual_dir = os.path.join(OUT_BASE, "manual")
            print(f"🚀 Downloading single video to: {manual_dir}...")
            
            engine = SoraCore(manual_dir, concurrency=1)
            async with aiohttp.ClientSession() as session:
                success = await engine.download_item(session, url, 0)
                if success: print("✅ Downloaded successfully!")
                else: print("❌ Download failed.")
            return

        choice = int(choice)
        if not (1 <= choice <= len(files)):
            print("Invalid choice.")
            return
            
        filename = files[choice-1]
        filepath = os.path.join(INPUT_DIR, filename)
        
        with open(filepath, 'r', encoding='utf-8') as f:
            urls = [line.strip() for line in f if line.strip().startswith('http')]
            
        print(f"\n📊 Batch: {filename} ({len(urls)} links)")
        range_str = input("Enter range (e.g., 'all' or '1-10, 20-30'): ")
        indices = parse_range(range_str, len(urls))
        
        if not indices:
            print("No valid indices selected.")
            return
            
        batch_folder = os.path.splitext(filename)[0]
        out_dir = os.path.join(OUT_BASE, batch_folder)
        
        print(f"🎬 Archiving {len(indices)} videos to: {out_dir}\n")
        
        urls_to_download = [(idx, urls[idx-1]) for idx in indices]
        engine = SoraCore(out_dir, concurrency=25)
        await engine.archiver_run(urls_to_download)
        
    except ValueError: print("Please enter a valid number.")
    except Exception as e: print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
