import aiohttp
import aiofiles
import asyncio
import os
import logging
from api_wrapper import SoraAPI
from tqdm.asyncio import tqdm

# Configure Logging
logging.basicConfig(level=logging.INFO, filename='logs/archiver.log', 
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SoraEngine:
    def __init__(self, output_dir, concurrency=25):
        self.output_dir = output_dir
        self.concurrency = concurrency
        self.semaphore = asyncio.Semaphore(concurrency)
        os.makedirs(output_dir, exist_ok=True)
        
    async def get_remote_size(self, session, url):
        try:
            async with session.head(url, timeout=10) as resp:
                return int(resp.headers.get('Content-Length', 0))
        except: return 0

    async def is_duplicate(self, filepath, expected_size):
        if not os.path.exists(filepath): return False
        current_size = os.path.getsize(filepath)
        if expected_size > 0 and current_size != expected_size:
            return False
        return True

    async def download_one(self, session, sora_url, index):
        """
        Downloads a single video by its index in the batch.
        """
        async with self.semaphore:
            clean_link, _ = await SoraAPI.get_clean_link(session, sora_url)
            if not clean_link:
                logger.error(f"Failed to fetch clean link for #{index}: {sora_url}")
                return False
                
            sora_id = sora_url.split('/')[-1] if '/p/' in sora_url else f"item_{index}"
            filename = f"{index}_{sora_id}.mp4"
            filepath = os.path.join(self.output_dir, filename)
            
            # Smart duplicate check
            rem_size = await self.get_remote_size(session, clean_link)
            if await self.is_duplicate(filepath, rem_size):
                return True # Skipped duplicate
                
            try:
                async with session.get(clean_link, timeout=60) as resp:
                    if resp.status == 200:
                        async with aiofiles.open(filepath, 'wb') as f:
                            async for chunk in resp.content.iter_chunked(1024 * 1024):
                                await f.write(chunk)
                        return True
                    return False
            except Exception as e:
                logger.error(f"Download Error for #{index}: {e}")
                return False

    async def run_archiver(self, urls_with_indices):
        """
        Runs the engine for a subset of URLs with their original indices.
        """
        async with aiohttp.ClientSession() as session:
            tasks = [self.download_one(session, url, idx) for idx, url in urls_with_indices]
            # Parallel processing with progress bar
            await tqdm.gather(*tasks, desc=f"Downloading {len(tasks)} videos", leave=True)
