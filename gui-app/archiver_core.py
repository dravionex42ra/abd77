import aiohttp
import aiofiles
import asyncio
import os
import logging
import urllib.parse
from datetime import datetime

# Configure Logging
os.makedirs('logs', exist_ok=True)
logging.basicConfig(level=logging.INFO, filename='logs/archiver.log', format='%(asctime)s - %(levelname)s - %(message)s')

class SoraAPI:
    """Independent API logic for gui-app with retry and timeout support"""
    BASE_URL = "https://api.soracdn.workers.dev/api-proxy/"
    
    @staticmethod
    async def get_clean_link(session, sora_url, idx, retries=3):
        encoded_url = urllib.parse.quote(sora_url, safe='')
        target_url = f"{SoraAPI.BASE_URL}{encoded_url}"
        headers = {
            "Origin": "https://snapsora.net",
            "Referer": "https://snapsora.net/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        }
        
        for attempt in range(retries):
            try:
                # Small delay to prevent proxy rate-limit
                await asyncio.sleep(0.1)
                
                # Hard timeout for API fetch
                async with asyncio.timeout(30):
                    async with session.get(target_url, headers=headers) as response:
                        if response.status == 200:
                            data = await response.json()
                            links = data.get('links', {})
                            return links.get('mp4_source') or links.get('mp4')
                        elif response.status == 429:
                            print(f" [!] Rate Limited (# {idx}). Retrying in 5s...")
                            await asyncio.sleep(5)
            except Exception:
                if attempt == retries - 1:
                    return None
                await asyncio.sleep(3)
        return None

class SoraCore:
    def __init__(self, out_dir, concurrency=15):
        self.out_dir = out_dir
        self.concurrency = concurrency
        os.makedirs(out_dir, exist_ok=True)

    async def get_remote_size(self, session, url):
        try:
            async with asyncio.timeout(15):
                async with session.head(url) as r: 
                    return int(r.headers.get('Content-Length', 0))
        except: return 0

    async def download_item(self, session, url, idx):
        """Downloads a single item with hard timeout and verbose status"""
        print(f" [+] [#{idx}] FETCHING LINK...")
        
        try:
            clean_url = await SoraAPI.get_clean_link(session, url, idx)
            if not clean_url:
                print(f" [!] [#{idx}] FAILED TO FETCH CLEAN LINK.")
                return False
                
            s_id = url.split('/')[-1] if '/p/' in url else f"item_{idx}"
            filename = f"{idx}_{s_id}.mp4"
            filepath = os.path.join(self.out_dir, filename)
            
            # Smart duplicate check
            size = await self.get_remote_size(session, clean_url)
            if os.path.exists(filepath) and os.path.getsize(filepath) == size and size > 0:
                print(f" [✔] [#{idx}] SKIPPED (Duplicate).")
                return True
                
            print(f" [⚡] [#{idx}] DOWNLOADING (Size: {size/(1024*1024):.1f} MB)...")
            
            # Hard timeout for file download
            async with asyncio.timeout(300):
                async with session.get(clean_url) as resp:
                    if resp.status == 200:
                        async with aiofiles.open(filepath, 'wb') as f:
                            async for chunk in resp.content.iter_chunked(1024*1024): 
                                await f.write(chunk)
                        print(f" [✅] [#{idx}] SUCCESSFULLY ARCHIVED.")
                        return True
                    else:
                        print(f" [!] [#{idx}] SERVER RETURNED STATUS: {resp.status}")
                        return False
        except asyncio.TimeoutError:
            print(f" [✖] [#{idx}] TIMED OUT (Skipping to next).")
            return False
        except Exception as e:
            print(f" [✖] [#{idx}] ERROR: {e}")
            return False

    async def worker(self, queue, session):
        while True:
            item = await queue.get()
            if item is None: break
            
            idx, url = item
            try:
                await self.download_item(session, url, idx)
            finally:
                queue.task_done()

    async def archiver_run(self, urls_with_indices):
        """Standard Terminal Output (No TQDM to avoid flickering)"""
        queue = asyncio.Queue()
        for item in urls_with_indices:
            await queue.put(item)
            
        for _ in range(self.concurrency):
            await queue.put(None)

        print(f"\n🚀 ARCHIVER STARTED | CONCURRENCY: {self.concurrency} | BATCH SIZE: {len(urls_with_indices)}")
        print(f"📂 SAVING TO: {self.out_dir}")
        print("-" * 50)

        # Fix: trust_env belongs to ClientSession, not TCPConnector
        connector = aiohttp.TCPConnector(limit=self.concurrency)
        async with aiohttp.ClientSession(connector=connector, trust_env=True) as session:
            workers = [asyncio.create_task(self.worker(queue, session)) 
                       for _ in range(self.concurrency)]
            await asyncio.gather(*workers)
        
        print("\n" + "=" * 50)
        print("🎉 BATCH PROCESSING COMPLETE!")
        print("=" * 50)
