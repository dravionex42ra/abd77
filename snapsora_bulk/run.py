import asyncio
import os
import aiohttp
from api import SnapsoraFetcher
from download_core import VideoArchive

# Configuration
INPUT_FILE = "urls.txt"
DOWNLOAD_DIR = "downloads"
CONCURRENT_LIMIT = 3 # Number of parallel downloads

async def process_video(session, sora_url, index, sem):
    """
    Process a single URL: Fetch -> Direct Stream Download.
    """
    async with sem:
        print(f"\n[Processing {index}] URL: {sora_url}")
        
        # Step 1: Fetch direct MP4 link
        mp4_url, data = await SnapsoraFetcher.get_direct_link(session, sora_url)
        
        if mp4_url:
            # Step 2: Determine filename (using index or cleaner title if available)
            filename = f"video_{index:03d}.mp4"
            output_path = os.path.join(DOWNLOAD_DIR, filename)
            
            # Step 3: Direct Streaming Download
            success = await VideoArchive.stream_download(session, mp4_url, output_path)
            if success:
                print(f"[Done {index}] Saved as {filename}")
            else:
                print(f"[Error {index}] Download failed for {sora_url}")
        else:
            print(f"[Error {index}] Could not fetch direct link. API response: {data}")

async def main():
    # Ensure environment is ready
    if not os.path.exists(INPUT_FILE):
        print(f"Error: {INPUT_FILE} not found. Please create it and paste URLs.")
        return
        
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    
    # Read URLs from file
    with open(INPUT_FILE, "r") as f:
        urls = [line.strip() for line in f if line.strip()]
    
    if not urls:
        print("No URLs found in urls.txt. Please add some!")
        return
        
    print(f"Found {len(urls)} URLs. Starting bulk download...")
    
    # Setup session and concurrency semaphore
    sem = asyncio.Semaphore(CONCURRENT_LIMIT)
    async with aiohttp.ClientSession() as session:
        tasks = []
        for i, url in enumerate(urls, 1):
            tasks.append(process_video(session, url, i, sem))
        
        await asyncio.gather(*tasks)
    
    print("\n[Complete] All tasks finished. Check the 'downloads/' folder!")

if __name__ == "__main__":
    asyncio.run(main())
