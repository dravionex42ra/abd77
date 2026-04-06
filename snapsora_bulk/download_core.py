import aiohttp
import aiofiles
import os
from tqdm.asyncio import tqdm

class VideoArchive:
    """
    Streaming downloader for video files. Saves chunks to disk to handle large batches without RAM crashes.
    """
    
    @staticmethod
    async def stream_download(session, mp4_url, output_path):
        """
        Saves the video chunks directly to the specified path with a progress bar.
        """
        try:
            async with session.get(mp4_url, timeout=30) as response:
                if response.status == 200:
                    # Get file size for progress bar
                    file_size = int(response.headers.get('content-length', 0))
                    
                    # Ensure directory exists
                    os.makedirs(os.path.dirname(output_path), exist_ok=True)
                    
                    # Setup progress bar
                    filename = os.path.basename(output_path)
                    progress_bar = tqdm(
                        total=file_size,
                        unit='B',
                        unit_scale=True,
                        desc=f"Downloading {filename[:20]}...",
                        leave=False
                    )
                    
                    async with aiofiles.open(output_path, mode='wb') as f:
                        async for chunk in response.content.iter_chunked(1024 * 1024): # 1MB chunk size
                            await f.write(chunk)
                            progress_bar.update(len(chunk))
                    
                    progress_bar.close()
                    return True
                else:
                    print(f"Download Error: Status {response.status} for {mp4_url}")
                    return False
        except Exception as e:
            print(f"Exception during download: {str(e)}")
            return False
