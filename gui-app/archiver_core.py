import aiohttp
import aiofiles
import asyncio
import os
import logging
import urllib.parse
from tqdm.asyncio import tqdm

# Configure Logging
os.makedirs('logs', exist_ok=True)
logging.basicConfig(level=logging.INFO, filename='logs/archiver.log', format='%(asctime)s - %(levelname)s - %(message)s')

class SoraAPI:
    """Independent API logic for gui-app with retry support"""
    BASE_URL = "https://api.soracdn.workers.dev/api-proxy/"
    
    @staticmethod
    async def get_clean_link(session, sora_url, retries=3):
        encoded_url = urllib.parse.quote(sora_url, safe='')
        target_url = f"{SoraAPI.BASE_URL}{encoded_url}"
        headers = {
            "Origin": "https://snapsora.net",
            "Referer": "https://snapsora.net/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        }
        
        for attempt in range(retries):
            try:
                # Add tiny delay between API calls to prevent rate-limit
                await asyncio.sleep(0.2)
                
                async with session.get(target_url, headers=headers, timeout=15) as response:
                    if response.status == 200:
                        data = await response.json()
                        links = data.get('links', {})
                        return links.get('mp4_source') or links.get('mp4')
            except Exception as e:
                if attempt == retries - 1:
                    print(f"\n⚠️ API Error (Max Retries): {e}")
                await asyncio.sleep(2) # Wait before retry
        return None

class SoraCore:
    def __init__(self, out_dir, concurrency=15):
        self.out_dir = out_dir
        self.concurrency = concurrency
        os.makedirs(out_dir, exist_ok=True)

    async def get_remote_size(self, session, url):
        try:
            async with session.head(url, timeout=10) as r: 
                return int(r.headers.get('Content-Length', 0))
        except: return 0

    async def download_item(self, session, url, idx, retries=3):
        """Downloads a single item with retry logic"""
        for attempt in range(retries):
            try:
                clean_url = await SoraAPI.get_clean_link(session, url)
                if not clean_url: continue
                
                s_id = url.split('/')[-1] if '/p/' in url else f"item_{idx}"
                filename = f"{idx}_{s_id}.mp4"
                filepath = os.path.join(self.out_dir, filename)
                
                # Smart duplicate check (Name + Size)
                size = await self.get_remote_size(session, clean_url)
                if os.path.exists(filepath) and os.path.getsize(filepath) == size and size > 0:
                    return True
                    
                async with session.get(clean_url, timeout=120) as resp:
                    if resp.status == 200:
                        async with aiofiles.open(filepath, 'wb') as f:
                            async for chunk in resp.content.iter_chunked(1024*1024): 
                                await f.write(chunk)
                        return True
            except Exception as e:
                if attempt == retries - 1:
                    print(f"\n❌ Download Error (Max Retries): {e}")
                await asyncio.sleep(3) # Wait before retry
        return False

    async def worker(self, queue, session, pbar):
        """Worker that pulls tasks from the queue"""
        while True:
            item = await queue.get()
            if item is None: break
            
            idx, url = item
            await self.download_item(session, url, idx)
            pbar.update(1)
            queue.task_done()

    async def archiver_run(self, urls_with_indices):
        """Main execution loop with Worker Pool & Queue"""
        queue = asyncio.Queue()
        for item in urls_with_indices:
            await queue.put(item)
            
        # Add termination flags for workers
        for _ in range(self.concurrency):
            await queue.put(None)

        async with aiohttp.ClientSession() as session:
            with tqdm(total=len(urls_with_indices), desc="Archiving Batch", leave=True) as pbar:
                workers = [asyncio.create_task(self.worker(queue, session, pbar)) 
                           for _ in range(self.concurrency)]
                await asyncio.gather(*workers)
