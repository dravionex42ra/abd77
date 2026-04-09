import aiohttp
import aiofiles
import os
import asyncio
from tqdm.asyncio import tqdm

class VideoArchive:
    """
    Advanced streaming downloader with Auto-Resume and Retry support.
    """
    
    @staticmethod
    def _get_unique_path(path):
        """
        Handles duplicates by appending #1, #2, etc. (Not used for resume).
        """
        if not os.path.exists(path):
            return path
        base, ext = os.path.splitext(path)
        counter = 1
        while True:
            new_path = f"{base}#{counter}{ext}"
            if not os.path.exists(new_path):
                return new_path
            counter += 1

    @staticmethod
    async def stream_download(session, mp4_url, output_path, retries=3):
        """
        Downloads a video with 'Range' resume support and automatic retries.
        """
        # Ensure directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Check if we should resume
        current_size = 0
        if os.path.exists(output_path):
            current_size = os.path.getsize(output_path)
            
        for attempt in range(retries):
            try:
                headers = {}
                if current_size > 0:
                    headers = {'Range': f'bytes={current_size}-'}
                
                async with session.get(mp4_url, headers=headers, timeout=60) as response:
                    # 206 means partial content (Resuming), 200 means full download
                    if response.status in (200, 206):
                        total_size = int(response.headers.get('content-length', 0)) + current_size
                        
                        # Fix for servers that don't support Range (Restart from 0)
                        mode = 'ab' if response.status == 206 else 'wb'
                        if response.status == 200:
                            current_size = 0
                        
                        filename = os.path.basename(output_path)
                        pbar = tqdm(
                            total=total_size,
                            initial=current_size,
                            unit='B',
                            unit_scale=True,
                            desc=f"Download {filename[:20]}...",
                            leave=False
                        )
                        
                        async with aiofiles.open(output_path, mode=mode) as f:
                            async for chunk in response.content.iter_chunked(1024 * 1024): # 1MB chunk
                                await f.write(chunk)
                                current_size += len(chunk)
                                pbar.update(len(chunk))
                        
                        pbar.close()
                        return True, current_size # Success
                        
                    elif response.status == 416: # Range not satisfiable (might be finished)
                        print(f"(!) {os.path.basename(output_path)} might already be complete (HTTP 416).")
                        return True, current_size
                    else:
                        print(f"(!) Attempt {attempt+1} failed: Status {response.status}")
                
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                print(f"(!) Attempt {attempt+1} network error for {os.path.basename(output_path)}: {str(e)}")
            except Exception as e:
                print(f"(!) Unexpected error on attempt {attempt+1}: {str(e)}")
            
            # Wait before retry (Exponential backoff)
            if attempt < retries - 1:
                await asyncio.sleep(2 * (attempt + 1))
        
        return False, current_size # Failed after all retries
