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
    """Independent API logic for gui-app"""
    BASE_URL = "https://api.soracdn.workers.dev/api-proxy/"
    
    @staticmethod
    async def get_clean_link(session, sora_url):
        encoded_url = urllib.parse.quote(sora_url, safe='')
        target_url = f"{SoraAPI.BASE_URL}{encoded_url}"
        headers = {
            "Origin": "https://snapsora.net",
            "Referer": "https://snapsora.net/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        }
        try:
            async with session.get(target_url, headers=headers, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    links = data.get('links', {})
                    return links.get('mp4_source') or links.get('mp4')
        except Exception as e:
            print(f"\n⚠️ API Error: {e}")
            return None
        return None

class SoraCore:
    def __init__(self, out_dir, concurrency=25):
        self.out_dir = out_dir
        self.semaphore = asyncio.Semaphore(concurrency)
        os.makedirs(out_dir, exist_ok=True)

    async def get_remote_size(self, session, url):
        try:
            async with session.head(url, timeout=5) as r: return int(r.headers.get('Content-Length', 0))
        except: return 0

    async def download_item(self, session, url, idx):
        async with self.semaphore:
            clean_url = await SoraAPI.get_clean_link(session, url)
            if not clean_url: return False
            
            s_id = url.split('/')[-1] if '/p/' in url else f"item_{idx}"
            filename = f"{idx}_{s_id}.mp4"
            filepath = os.path.join(self.out_dir, filename)
            
            # Smart duplicate check (Name + Size)
            size = await self.get_remote_size(session, clean_url)
            if os.path.exists(filepath) and os.path.getsize(filepath) == size and size > 0:
                return True # Skipped
                
            try:
                async with session.get(clean_url, timeout=60) as resp:
                    if resp.status == 200:
                        async with aiofiles.open(filepath, 'wb') as f:
                            async for chunk in resp.content.iter_chunked(1024*1024): await f.write(chunk)
                        return True
            except Exception as e:
                print(f"\n❌ Local Save Error: {e}")
                return False
        return False

    async def archiver_run(self, urls_with_indices):
        async with aiohttp.ClientSession() as session:
            tasks = [self.download_item(session, url, idx) for idx, url in urls_with_indices]
            await tqdm.gather(*tasks, desc=f"Downloading batch ({len(tasks)} items)", leave=True)
