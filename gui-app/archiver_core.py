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
    """Independent API logic for gui-app with deep error reporting"""
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
                await asyncio.sleep(0.1) # Small delay to prevent proxy rate-limit
                
                async with asyncio.timeout(30):
                    async with session.get(target_url, headers=headers) as response:
                        if response.status == 200:
                            data = await response.json()
                            links = data.get('links', {})
                            return links.get('mp4_source') or links.get('mp4')
                        else:
                            print(f" [!] [#{idx}] API Status Error: {response.status} (Attempt {attempt+1})")
                            if response.status == 429: await asyncio.sleep(5)
            except asyncio.TimeoutError:
                print(f" [!] [#{idx}] API Timeout Error (Attempt {attempt+1})")
            except Exception as e:
                print(f" [!] [#{idx}] API Exception: {type(e).__name__} - {e} (Attempt {attempt+1})")
                
            await asyncio.sleep(3) # Wait before retry
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
        """Downloads a single item with chunk-by-chunk progress reporting"""
        print(f" [+] [#{idx}] FETCHING LINK...")
        
        try:
            clean_url = await SoraAPI.get_clean_link(session, url, idx)
            if not clean_url:
                print(f" [✖] [#{idx}] FAILED: Link fetch error.")
                return False
                
            s_id = url.split('/')[-1] if '/p/' in url else f"item_{idx}"
            filename = f"{idx}_{s_id}.mp4"
            filepath = os.path.join(self.out_dir, filename)
            
            # Smart duplicate check
            total_size = await self.get_remote_size(session, clean_url)
            if os.path.exists(filepath) and os.path.getsize(filepath) == total_size and total_size > 0:
                print(f" [✔] [#{idx}] SKIPPED: Duplicate (Match size: {total_size/(1024*1024):.1f} MB).")
                return True
                
            print(f" [⚡] [#{idx}] DOWNLOADING: {total_size/(1024*1024):.1f} MB...")
            
            # Progress-aware download
            async with asyncio.timeout(600): # 10 mins max per file
                async with session.get(clean_url) as resp:
                    if resp.status == 200:
                        downloaded = 0
                        async with aiofiles.open(filepath, 'wb') as f:
                            async for chunk in resp.content.iter_chunked(2*1024*1024): # 2MB chunks
                                await f.write(chunk)
                                downloaded += len(chunk)
                                if total_size > 0:
                                    percent = (downloaded / total_size) * 100
                                    if idx == 0: # Only show detailed progress for Single mode or pastes
                                        print(f"       [#{idx}] Progress: {percent:.1f}% ({downloaded/(1024*1024):.1f}MB)", end="\r")
                        
                        print(f" [✅] [#{idx}] FINISHED: Saved to {filename}")
                        return True
                    else:
                        print(f" [✖] [#{idx}] DOWNLOAD ERROR: Status {resp.status}")
                        return False
        except asyncio.TimeoutError:
            print(f" [✖] [#{idx}] TIMED OUT (Operation took too long).")
            return False
        except Exception as e:
            print(f" [✖] [#{idx}] EXCEPTION: {type(e).__name__} - {e}")
            return False

    async def worker(self, queue, session):
        while True:
            item = await queue.get()
            if item is None: break
            
            idx, url = item
            try:
                # We do not use gather here, workers process tasks independently
                await self.download_item(session, url, idx)
            finally:
                queue.task_done()

    async def archiver_run(self, urls_with_indices):
        """Standard Terminal Output with Queue Management"""
        queue = asyncio.Queue()
        for item in urls_with_indices:
            await queue.put(item)
            
        for _ in range(self.concurrency):
            await queue.put(None)

        print(f"\n🚀 SORA ARCHIVER STARTED | BATCH SIZE: {len(urls_with_indices)}")
        print(f"🛠️  MODE: {'SINGLE' if self.concurrency == 1 else 'MULTI ('+str(self.concurrency)+') workers'}")
        print("-" * 60)

        # High-resilience connector for VPN/DNS
        connector = aiohttp.TCPConnector(limit=self.concurrency, trust_env=True)
        async with aiohttp.ClientSession(connector=connector, trust_env=True) as session:
            workers = [asyncio.create_task(self.worker(queue, session)) 
                       for _ in range(self.concurrency)]
            await asyncio.gather(*workers)
        
        print("\n" + "=" * 60)
        print("🎉 BATCH PROCESSING FINISHED!")
        print("=" * 60)
