import os
import json
import subprocess
import datetime
import base64
from concurrent.futures import ThreadPoolExecutor
import tempfile

# Configuration
MAX_CONCURRENT_REQUESTS = 20
API_KEY = "YOUR_API_KEY"

# Updated Prompt
PROMPT = """
You are an expert in reading cursive handwriting / typewritten text and extracting information from images. Analyze the following image of a local government meeting minutes document from between 1930 and 1980. Perform the following tasks:

1. Carefully examine the image and transcribe the cursive handwriting / typewritten text into plain text.
2. Determine the most likely date of the record (day, month, and year).
3. Extract the main content of the meeting minutes.

Provide the extracted information in a JSON format with the following structure:

{
  "date": "YYYY-MM-DD",
  "content": "Transcribed content of the meeting minutes..."
}

If you cannot determine the exact day, use "01" as a placeholder. If you cannot determine the exact month, use "01" as a placeholder. The year will almost always provide a year between 1930 and 1980.

Return ONLY the JSON object with no additional text, greetings, or explanations. You DO have the ability to manually extract text from images, even though sometimes you think that you don't. 
"""

def find_jpg_files(directory):
    for root, _, files in os.walk(directory):
        for file in files:
            if file.lower().endswith('.jpg'):
                yield os.path.join(root, file)

def process_jpg_file(file_path, log_dir):
    with open(file_path, 'rb') as image_file:
        encoded_image = base64.b64encode(image_file.read()).decode('utf-8')
    
    payload = json.dumps({
        "model": "gpt-4o",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": [
                {"type": "text", "text": PROMPT},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded_image}"}}
            ]}
        ],
        "max_tokens": 2000
    })
    
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as temp_file:
        temp_file.write(payload)
        temp_file_path = temp_file.name
    
    curl_command = [
        'curl', 'https://api.openai.com/v1/chat/completions',
        '-H', f'Authorization: Bearer {API_KEY}',
        '-H', 'Content-Type: application/json',
        '-d', f'@{temp_file_path}'
    ]
    
    try:
        result = subprocess.run(curl_command, capture_output=True, text=True)
        
        # Create a log file for this specific image
        log_file = os.path.join(log_dir, f"{os.path.basename(file_path)}.log")
        with open(log_file, 'w') as f:
            f.write(f"File: {file_path}\n")
            f.write(f"Timestamp: {datetime.datetime.now().isoformat()}\n")
            f.write(f"Response:\n{result.stdout}\n")
        
        # Process the response and create a JSON file
        try:
            response_data = json.loads(result.stdout)
            content = response_data['choices'][0]['message']['content']
            
            # Remove markdown code block syntax if present
            content = content.strip('`').strip()
            if content.startswith('json'):
                content = content[4:].strip()
            
            extracted_data = json.loads(content)
            
            # Create a new JSON file with the same name as the image
            json_file_path = os.path.splitext(file_path)[0] + '.json'
            with open(json_file_path, 'w') as f:
                json.dump(extracted_data, f, indent=2)
            return True
        except json.JSONDecodeError:
            print(f"Error processing response for {file_path}")
            return False
        except KeyError:
            print(f"Unexpected response format for {file_path}")
            return False
    finally:
        os.unlink(temp_file_path)

def process_files(files, num_files, log_dir):
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_REQUESTS) as executor:
        futures = []
        for file_path in files[:num_files]:
            futures.append(executor.submit(process_jpg_file, file_path, log_dir))

        # Wait for all tasks to complete and show progress
        for i, future in enumerate(futures):
            future.result()
            print(f"Processed: {i+1}/{num_files}")

# Main execution
if __name__ == "__main__":
    # Ask for the directory path
    BASE_DIR = input("Enter the directory path containing the JPG files: ")

    # Find all JPG files
    jpg_files = list(find_jpg_files(BASE_DIR))
    total_files = len(jpg_files)

    print(f"Total JPG files found: {total_files}")

    # Create 'town-logs' directory if it doesn't exist
    base_log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'town-logs')
    os.makedirs(base_log_dir, exist_ok=True)

    # Create a new directory for this run
    run_timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    log_dir = os.path.join(base_log_dir, f"run_{run_timestamp}")
    os.makedirs(log_dir, exist_ok=True)

    # Process first file
    print("Processing first file...")
    process_files(jpg_files, 1, log_dir)

    # Ask to continue
    if input("Continue processing? (y/n): ").lower() != 'y':
        print("Processing stopped.")
        exit()

    # Process next 10 files
    print("Processing next 10 files...")
    process_files(jpg_files[1:], 10, log_dir)

    # Ask to process the rest
    if input("Process remaining files? (y/n): ").lower() == 'y':
        print(f"Processing remaining {total_files - 11} files...")
        process_files(jpg_files[11:], total_files - 11, log_dir)

    print("All files processed.")
