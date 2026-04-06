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

class SoraDownloader:
    def __init__(self, output_dir, concurrency=10):
        self.output_dir = output_dir
        self.concurrency = concurrency
        self.semaphore = asyncio.Semaphore(concurrency)
        os.makedirs(output_dir, exist_ok=True)
        
    async def is_duplicate(self, filepath, expected_size=None):
        """
        Check if file already exists with the same name and (optionally) size.
        """
        if not os.path.exists(filepath):
            return False
            
        current_size = os.path.getsize(filepath)
        if expected_size is not None and current_size != expected_size:
            logger.info(f"Size mismatch for {filepath}: {current_size} != {expected_size}. Overwriting.")
            return False
            
        return True

    async def download_video(self, session, sora_url, filename):
        """
        Downloads a single Sora video after fetching the clean link.
        """
        async with self.semaphore:
            # 1. Fetch the clean link
            clean_link, api_data = await SoraAPI.get_clean_link(session, sora_url)
            
            if not clean_link:
                logger.error(f"Failed to get clean link for {sora_url}")
                return False
                
            filepath = os.path.join(self.output_dir, filename)
            
            # 2. Check for duplicates/partial downloads
            # We get the 'Content-Length' first if possible
            try:
                async with session.head(clean_link) as head_resp:
                    expected_size = int(head_resp.headers.get('Content-Length', 0))
                    
                    if await self.is_duplicate(filepath, expected_size if expected_size > 0 else None):
                        logger.info(f"Skipped duplicate: {filename}")
                        return True
                
                # 3. Stream Download
                async with session.get(clean_link) as response:
                    if response.status == 200:
                        async with aiofiles.open(filepath, mode='wb') as f:
                            async for chunk in response.content.iter_chunked(1024 * 1024): # 1MB chunks
                                await f.write(chunk)
                        logger.info(f"Successfully downloaded: {filename}")
                        return True
                    else:
                        logger.error(f"Download returned {response.status} for {clean_link}")
                        return False
            except Exception as e:
                logger.error(f"Error downloading {sora_url}: {str(e)}")
                return False

    async def run_batch(self, url_list):
        """
        Runs a batch of URLs with the configured concurrency.
        """
        async with aiohttp.ClientSession() as session:
            tasks = []
            for idx, url in enumerate(url_list):
                # We use the Sora ID or index as the filename
                # Example Sora URL structure: .../p/s_69adb1a6...
                sora_id = url.split('/')[-1] if '/p/' in url else f"video_{idx}"
                filename = f"{sora_id}.mp4"
                tasks.append(self.download_video(session, url, filename))
            
            # Wrap tasks in tqdm for progress tracking
            results = await tqdm.gather(*tasks, desc="Archiving Batch", leave=True)
            return results
