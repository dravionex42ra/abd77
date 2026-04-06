import asyncio
import os
import argparse
from archiver import SoraDownloader

class SoraManager:
    def __init__(self, input_dir="input", output_base_dir="downloads", concurrency=20):
        self.input_dir = input_dir
        self.output_base_dir = output_base_dir
        self.concurrency = concurrency
        os.makedirs(input_dir, exist_ok=True)
        os.makedirs(output_base_dir, exist_ok=True)

    def load_urls_from_file(self, filename):
        """
        Reads URLs from a .txt file, one per line.
        """
        filepath = os.path.join(self.input_dir, filename)
        if not os.path.exists(filepath):
            print(f"File not found: {filepath}")
            return []
            
        with open(filepath, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip().startswith('http')]

    async def process_all_batches(self):
        """
        Scans the input directory and processes each .txt file as a separate batch.
        """
        txt_files = [f for f in os.listdir(self.input_dir) if f.endswith('.txt')]
        
        if not txt_files:
            print("No .txt files found in input/ directory. Add some links to start.")
            return

        for batch_file in txt_files:
            print(f"\n🚀 Processing Batch: {batch_file}")
            urls = self.load_urls_from_file(batch_file)
            
            if not urls:
                print(f"Skipping empty file: {batch_file}")
                continue
                
            # Create a folder for this specific batch
            batch_name = os.path.splitext(batch_file)[0]
            batch_output_dir = os.path.join(self.output_base_dir, batch_name)
            
            downloader = SoraDownloader(batch_output_dir, self.concurrency)
            await downloader.run_batch(urls)
            print(f"✅ Finished Batch: {batch_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sora Advanced Bulk Archiver (Production Edition)")
    parser.add_argument("--concurrency", type=int, default=25, help="Number of simultaneous downloads")
    args = parser.parse_args()
    
    manager = SoraManager(concurrency=args.concurrency)
    asyncio.run(manager.process_all_batches())
