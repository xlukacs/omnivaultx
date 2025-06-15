import os
import time

import pika
from PIL import Image
from pdf2image import convert_from_path
import pytesseract
import torch
from transformers import BlipProcessor, BlipForConditionalGeneration, WhisperProcessor, WhisperForConditionalGeneration
import cv2
import json
import base64
from rake_nltk import Rake
import nltk

import concurrent.futures
from pydub import AudioSegment
import librosa

import ssl
from dotenv import load_dotenv
import chardet



print(" [x] Downloading nltk parts...")
nltk.download('stopwords')
nltk.download('punkt_tab')
print(" [+] Download done...")

load_dotenv()

RABBITMQ_HOST = os.getenv('RABBIT_HOST', '127.0.0.1')
RABBITMQ_USER = os.getenv('RABBIT_USER', 'om-processor')
RABBITMQ_PASS = os.getenv('RABBIT_PASS', 'om-processor')
RABBITMQ_VHOST = os.getenv('RABBIT_VHOST', '/')
RABBITMQ_PORT = os.getenv('RABBIT_PORT', 5672)

print(f" [+] RabbitMQ Host: {RABBITMQ_HOST}, User: {RABBITMQ_USER}, VHost: {RABBITMQ_VHOST}, Password: ****")

QUEUE_NAME = 'file_processing_queue'
credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
context = ssl.create_default_context()

print(" [x] Loading models...")
blip_processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base")
blip_model = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-base")

print(" [x] Loading further models...")
whisper_processor = WhisperProcessor.from_pretrained("openai/whisper-large")
whisper_model = WhisperForConditionalGeneration.from_pretrained("openai/whisper-large")

print(" [+] Model loading done...")

# Supported file extensions
IMAGE_EXTENSIONS = ['.png', '.jpg', '.jpeg', '.gif']
AUDIO_EXTENSIONS = ['.mp3', '.wav', '.m4a']
VIDEO_EXTENSIONS = ['.mp4', '.mov']
PDF_EXTENSIONS = ['.pdf']
TEXT_EXTENSIONS = ['.txt']


# Process Image (BLIP)
def process_image(file_path):
    image = Image.open(file_path)
    inputs = blip_processor(image, return_tensors="pt")
    out = blip_model.generate(**inputs)
    caption = blip_processor.decode(out[0], skip_special_tokens=True)

    # os.remove(file_path)
    return caption

def load_audio(file_path):
    audio, _ = librosa.load(file_path, sr=16000)  # Load with librosa at 16 kHz
    return audio

# Process Audio (Whisper)
def process_audio(file_path, isWav = False):
    try:
        if not isWav:
            # Convert MP3 or WAV to a 16kHz, mono WAV file using pydub
            audio = AudioSegment.from_file(file_path)
            audio = audio.set_frame_rate(16000).set_channels(1)

            # Export the processed audio to WAV format
            wav_path = file_path.replace(".mp3", ".wav").replace(".wav", "_processed.wav")
            audio.export(wav_path, format="wav")
        else:
            wav_path = file_path

        # Load the entire audio using librosa for chunk processing
        audio_data, sampling_rate = librosa.load(wav_path, sr=16000, mono=True)
        print(" [-] Audio data loaded")

        # Define chunk duration (e.g., 30 seconds) in samples
        chunk_duration = 30 * sampling_rate  # 30 seconds per chunk
        total_duration = len(audio_data) / sampling_rate  # Total duration in seconds
        print(f" [-] Total audio duration: {total_duration} seconds")

        # Split the audio into chunks of 30 seconds each
        audio_chunks = [audio_data[i:i + chunk_duration] for i in range(0, len(audio_data), chunk_duration)]
        print(f" [-] Audio split into {len(audio_chunks)} chunks for processing")

        transcription = ""

        # Process each chunk
        for idx, chunk in enumerate(audio_chunks):
            # Prepare the chunk for Whisper input
            audio_input = whisper_processor(chunk, return_tensors="pt", sampling_rate=16000)

            # Transcribe the chunk
            with torch.no_grad():
                predicted_ids = whisper_model.generate(audio_input['input_features'], task="transcribe")

            # Decode the transcription
            chunk_transcription = whisper_processor.decode(predicted_ids[0], skip_special_tokens=True)
            transcription += chunk_transcription + " "
            print(f" [-] Processed chunk {idx + 1}/{len(audio_chunks)}")

        print(" [-] Complete transcription done")
        print(transcription)
        return transcription.strip()

    except Exception as e:
        print(f"Error processing audio file: {str(e)}")
        return None


# Process Video (convert to audio, then use Whisper)
def process_video(file_path):
    # Create a temporary audio file path
    audio_file_path = "temp_audio.wav"
    
    # Use cv2 to extract audio from video
    cap = cv2.VideoCapture(file_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = frame_count / fps
    
    # Get audio properties
    audio = AudioSegment.from_file(file_path)
    audio.export(audio_file_path, format="wav")
    
    # Release the video capture
    cap.release()
    
    transcription = process_audio(audio_file_path, isWav=True)
    
    # Clean up temporary file
    try:
        os.remove(audio_file_path)
    except:
        pass
        
    print(transcription)
    return transcription


def pdf_to_images(pdf_path, output_folder='uploads'):
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    images = convert_from_path(pdf_path, thread_count=8)

    image_paths = []
    for i, image in enumerate(images):
        # Save each image in the output folder
        image_path = os.path.join(output_folder, f"page_{i + 1}.png")
        image.save(image_path, 'PNG')
        image_paths.append(image_path)

    return image_paths


def extract_text_from_image(image_path):
    image = Image.open(image_path)
    text = pytesseract.image_to_string(image)

    return text


def process_pdf(file_path, output_folder='uploads'):
    extracted_text = ""
    images = pdf_to_images(file_path)

    def process_image(image_path):
        print(f"Processing {image_path}...")
        return extract_text_from_image(image_path)

    with concurrent.futures.ThreadPoolExecutor() as executor:
        text_results = executor.map(process_image, images)

    for text in text_results:
        extracted_text += text + "\n"

    for i, image in enumerate(images):
        image_path = os.path.join(output_folder, f"page_{i + 1}.png")
        print(f"Removing {image_path}...")
        os.remove(image_path)

    return extracted_text

def extract_tags(content, top_results=5):
    """Extract key phrases from text content using RAKE"""
    r = Rake()

    # Force convert content to string
    if not isinstance(content, str):
        content = str(content)

    # Check if content is None or empty
    if not content or content.strip() == "" or content == "None":
        return []
    
    r.extract_keywords_from_text(content)
    ranked_tags = r.get_ranked_phrases()
    return ranked_tags[:top_results]


def process_text_file(file_path):
    """Process text file and extract metadata"""
    try:
        # Load text content
        content = load_text_file(file_path)
        if not content:
            return None

        # Extract tags from content
        tags = extract_tags(content)

        return tags
    except Exception as e:
        print(f"Error processing text file: {str(e)}")
        return None

def save_temp_file(file_name, file_data):
    temp_file_path = os.path.join("uploads", file_name)
    decoded_file_data = base64.b64decode(file_data)
    with open(temp_file_path, 'wb') as temp_file:
        temp_file.write(decoded_file_data)
    return temp_file_path

def load_text_file(file_path):
    print(f" [+] Loading text file")
    with open(file_path, 'rb') as f:
        raw = f.read()

        if not raw:
            print(" [!] File is empty.")
            return ""
        
        result = chardet.detect(raw)
        encoding = result['encoding']
        print(f" [+] Detected encoding: {encoding}")
        try:
            return raw.decode(encoding)
        except Exception as e:
            print(f"Error decoding file with detected encoding {encoding}: {str(e)}")
            return None

def dedupe_tags(tags):
    return list(set(tags))

def send_message_to_queue(queue_name, message):
    try:
        # Establish a new connection to RabbitMQ
        connection = pika.BlockingConnection(pika.ConnectionParameters(
            host=RABBITMQ_HOST,
            credentials=credentials,
            virtual_host=RABBITMQ_VHOST,
            port=RABBITMQ_PORT  # Standard AMQP port
        ))
        channel = connection.channel()

        channel.queue_declare(queue=queue_name, durable=True)

        # JSON encode the message before sending
        message_json = json.dumps(message)

        channel.basic_publish(
            exchange='',
            routing_key=queue_name,
            body=message_json,
            properties=pika.BasicProperties(delivery_mode=2)
        )
        print(f" [*] Message sent to queue '{queue_name}'")
    except (pika.exceptions.AMQPConnectionError, pika.exceptions.AMQPChannelError) as e:
        print(f" [!] Connection or channel error: {str(e)}, retrying in 5 seconds...")
        time.sleep(5)

        # retry
        try:
            connection = pika.BlockingConnection(pika.ConnectionParameters(
                host=RABBITMQ_HOST,
                credentials=credentials,
                virtual_host=RABBITMQ_VHOST,
                port=RABBITMQ_PORT  # Standard AMQP port
            ))
            channel = connection.channel()

            channel.queue_declare(queue=queue_name, durable=True)

            # JSON encode the message before sending (in retry as well)
            message_json = json.dumps(message)

            channel.basic_publish(
                exchange='',
                routing_key=queue_name,
                body=message_json,
                properties=pika.BasicProperties(delivery_mode=2)
            )
            print(f" [*] Message resent after reconnection to queue '{queue_name}'")

        except Exception as retry_error:
            print(f" [!] Failed to republish message after reconnecting: {str(retry_error)}")

    except Exception as e:
        print(f"Failed to publish message: {str(e)}")

    finally:
        if 'connection' in locals() and connection.is_open:
            connection.close()
            print(" [*] Connection closed after sending the message.")

def decide_dynamic_type(content):
    # YouTube detection
    if "youtube.com" in content or "youtu.be" in content:
        return "youtube"
    
    # Google Docs detection
    elif "docs.google.com" in content:
        return "google_docs"
    
    # Google Drive detection
    elif "drive.google.com" in content:
        return "google_drive"
    
    # Google Images detection
    elif "images.google.com" in content:
        return "google_images"
    
    # Medium or other blog platforms
    elif any(domain in content for domain in ["medium.com", "wordpress.com", "blogger.com", "tumblr.com"]):
        return "blog"
    
    # Social media platforms
    elif any(domain in content for domain in ["twitter.com", "facebook.com", "instagram.com", "linkedin.com"]):
        return "social_media"
    
    # GitHub or code repositories
    elif any(domain in content for domain in ["github.com", "gitlab.com", "bitbucket.org"]):
        return "code_repository"
    
    # News websites
    elif any(domain in content for domain in ["cnn.com", "bbc.com", "nytimes.com", "reuters.com"]):
        return "news"
    
    # Academic resources
    elif any(domain in content for domain in ["scholar.google.com", "researchgate.net", "academia.edu"]):
        return "academic"
    
    else:
        return "unsupported"

def process_youtube(content):
    try:
        # Import necessary libraries
        import re
        import requests
        import tempfile
        import os
        import json
        from bs4 import BeautifulSoup
        import subprocess
        
        # Find YouTube URL in the content
        youtube_regex = r'(https?://)?(www\.)?(youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]{11})'
        match = re.search(youtube_regex, content)
        
        if not match:
            print(" [!] No valid YouTube URL found in content")
            return ["youtube"]
        
        # Extract the video ID and construct full URL
        video_id = match.group(4)
        youtube_url = f"https://www.youtube.com/watch?v={video_id}"
        print(f" [-] Processing YouTube video: {youtube_url}")
        
        # Initialize variables for metadata
        title = f"YouTube Video {video_id}"
        uploader = "Unknown Uploader"
        description = ""
        
        # Scrape metadata from YouTube page
        try:
            print(" [-] Scraping metadata from YouTube page...")
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            response = requests.get(youtube_url, headers=headers)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Try to extract title
                meta_title = soup.find('meta', property='og:title')
                if meta_title and meta_title.get('content'):
                    title = meta_title['content']
                    print(f" [-] Scraped title: {title}")
                
                # Try to extract channel name
                meta_channel = soup.find('link', itemprop='name')
                if meta_channel and meta_channel.get('content'):
                    uploader = meta_channel['content']
                    print(f" [-] Scraped uploader: {uploader}")
                
                # Try to extract description
                meta_desc = soup.find('meta', property='og:description')
                if meta_desc and meta_desc.get('content'):
                    description = meta_desc['content']
                    print(" [-] Scraped description successfully")
                
                # Try to find more metadata in the page source
                for script in soup.find_all('script'):
                    if script.string and 'var ytInitialData' in script.string:
                        try:
                            # Extract JSON data
                            json_str = script.string.split('var ytInitialData = ')[1].split(';</script>')[0]
                            data = json.loads(json_str)
                            
                            # Navigate through the complex JSON structure to find more metadata
                            video_details = data.get('contents', {}).get('twoColumnWatchNextResults', {}).get('results', {}).get('results', {}).get('contents', [])
                            
                            for item in video_details:
                                if 'videoPrimaryInfoRenderer' in item:
                                    if not title or title == f"YouTube Video {video_id}":
                                        title_element = item['videoPrimaryInfoRenderer'].get('title', {}).get('runs', [{}])[0].get('text')
                                        if title_element:
                                            title = title_element
                                            print(f" [-] Found title in JSON: {title}")
                                
                                if 'videoSecondaryInfoRenderer' in item:
                                    if not uploader or uploader == "Unknown Uploader":
                                        uploader_element = item['videoSecondaryInfoRenderer'].get('owner', {}).get('videoOwnerRenderer', {}).get('title', {}).get('runs', [{}])[0].get('text')
                                        if uploader_element:
                                            uploader = uploader_element
                                            print(f" [-] Found uploader in JSON: {uploader}")
                        except Exception as e:
                            print(f" [!] Error parsing JSON data: {str(e)}")
            else:
                print(f" [!] Failed to scrape YouTube page: HTTP {response.status_code}")
        except Exception as e:
            print(f" [!] Error during web scraping: {str(e)}")
        
        # Create a temporary directory for downloaded files
        temp_dir = tempfile.mkdtemp()
        temp_file = None
        transcription = None
        
        # Try to download and process video using yt-dlp (more reliable than pytube)
        try:
            # Check if yt-dlp is installed
            try:
                subprocess.run(['yt-dlp', '--version'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                print(" [-] yt-dlp is installed, using it for download")
                
                # Download audio only (more efficient)
                temp_file = os.path.join(temp_dir, "audio.mp3")
                download_cmd = [
                    'yt-dlp',
                    '-f', 'bestaudio[ext=m4a]/bestaudio',
                    '-o', temp_file,
                    youtube_url
                ]
                
                print(" [-] Downloading audio with yt-dlp...")
                result = subprocess.run(download_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                
                if os.path.exists(temp_file):
                    print(f" [-] Successfully downloaded audio to {temp_file}")
                    
                    # Transcribe the audio
                    print(" [-] Transcribing audio...")
                    transcription = process_audio(temp_file)
                else:
                    print(" [!] Audio download failed, trying video download...")
                    
                    # Try downloading video instead
                    temp_file = os.path.join(temp_dir, "video.mp4")
                    download_cmd = [
                        'yt-dlp',
                        '-f', 'best[height<=720]',
                        '-o', temp_file,
                        youtube_url
                    ]
                    
                    print(" [-] Downloading video with yt-dlp...")
                    result = subprocess.run(download_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    
                    if os.path.exists(temp_file):
                        print(f" [-] Successfully downloaded video to {temp_file}")
                        
                        # Process the video to extract audio and transcribe
                        print(" [-] Transcribing video...")
                        transcription = process_video(temp_file)
                    else:
                        print(" [!] Video download failed")
            
            except subprocess.CalledProcessError:
                print(" [!] yt-dlp not installed or failed to run")
                print(" [!] Please install yt-dlp with: pip install yt-dlp")
                # We'll continue with just the metadata we have
            
            # Generate tags from metadata and transcription
            metadata_text = f"{title} {uploader} {description}"
            metadata_tags = extract_tags(metadata_text, 3)
            
            transcription_tags = extract_tags(transcription, 3) if transcription else []
            
            # Combine all information
            all_tags = ["youtube", title, uploader, video_id] + metadata_tags + transcription_tags
            
            # Return unique tags
            return list(set(all_tags))
            
        except Exception as e:
            print(f" [!] Error downloading or processing media: {str(e)}")
            # Return what we have so far
            return ["youtube", title, uploader, video_id]
        
        finally:
            # Clean up temporary files
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception as e:
                    print(f" [!] Error removing temp file: {str(e)}")
            else:
                print(f" [!] Error, no temp file, or temp folder not found...")
            
            # Try to remove the temp directory
            try:
                os.rmdir(temp_dir)
            except Exception as e:
                print(f" [!] Error removing temp directory: {str(e)}")
        
    except Exception as e:
        print(f" [!] Error processing YouTube video: {str(e)}")
        return ["youtube", "error", video_id if 'video_id' in locals() else "unknown"]

def process_dynamic(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()

            dynamic_type = decide_dynamic_type(content)

            if dynamic_type == "youtube":
                return process_youtube(content)
            else:
                return []
                
    except Exception as e:
        print(f"Error reading file: {str(e)}")
        return None

def check_module_availability(module_id):
    """Check if a module ID is available"""
    try:
        credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(
                host=RABBITMQ_HOST,
                port=RABBITMQ_PORT,
                credentials=credentials,
                virtual_host=RABBITMQ_VHOST
            )
        )
        channel = connection.channel()
        
        # Create a temporary queue for the response
        result = channel.queue_declare(queue='', exclusive=True)
        callback_queue = result.method.queue
        
        # Send availability check request
        channel.basic_publish(
            exchange='meta_extraction',
            routing_key='check_availability',
            properties=pika.BasicProperties(
                reply_to=callback_queue
            ),
            body=json.dumps({'module_id': module_id})
        )
        
        # Wait for response
        response = None
        def on_response(ch, method, props, body):
            nonlocal response
            response = json.loads(body)
            
        channel.basic_consume(
            queue=callback_queue,
            on_message_callback=on_response,
            auto_ack=True
        )
        
        # Wait for response with timeout
        connection.process_data_events(time_limit=5)
        connection.close()
        
        if response:
            if not response['is_available']:
                print(f" [-] Module ID {module_id} is not available")
                if response['suggested_id']:
                    print(f" [+] Suggested alternative: {response['suggested_id']}")
            return response
        else:
            print(" [-] No response received from meta manager")
            return None
            
    except Exception as e:
        print(f" [-] Error checking module availability: {str(e)}")
        return None

def register_module(module_id):
    """Register this module with the meta manager service"""
    try:
        # First check if the module ID is available
        availability = check_module_availability(module_id)
        if not availability:
            print(" [-] Could not verify module ID availability")
            return
            
        if not availability['is_available']:
            if availability['suggested_id']:
                print(f" [+] Using suggested module ID: {availability['suggested_id']}")
                module_id = availability['suggested_id']
            else:
                print(" [-] No available module ID found")
                return
        
        credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(
                host=RABBITMQ_HOST,
                port=RABBITMQ_PORT,
                credentials=credentials,
                virtual_host=RABBITMQ_VHOST
            )
        )
        channel = connection.channel()
        
        # Declare the exchange if it doesn't exist
        channel.exchange_declare(
            exchange='meta_extraction',
            exchange_type='direct',
            durable=True
        )
        
        # Register this module with its supported extensions
        registration_message = {
            'module_id': module_id,
            'supported_extensions': IMAGE_EXTENSIONS + AUDIO_EXTENSIONS + VIDEO_EXTENSIONS + PDF_EXTENSIONS + TEXT_EXTENSIONS
        }
        
        channel.basic_publish(
            exchange='meta_extraction',
            routing_key='register',
            body=json.dumps(registration_message)
        )
        
        connection.close()
        print(f" [+] Successfully registered module {module_id} with supported extensions")
        return module_id
    except Exception as e:
        print(f" [-] Failed to register module: {str(e)}")
        return None

# Modify the callback function to handle new message format
def callback(ch, method, properties, body):
    try:
        data = json.loads(body)
        file_path = data.get('filename')
        file_name = os.path.basename(file_path)
        file_data = data.get('filedata')  # base64 encoded
        status_id = data.get('status_id')
        is_dynamic = data.get('is_dynamic', False)

        print(f" [+] Received message for resource ID: {status_id}")
        
        if not all([file_name, file_data, status_id]):
            print(" [-] Invalid message format")
            return
            
        # Create uploads directory if it doesn't exist
        if not os.path.exists('uploads'):
            os.makedirs('uploads')
            
        # Save the file to our uploads directory
        local_file_path = os.path.join('uploads', file_name)
        try:
            decoded_data = base64.b64decode(file_data)
            with open(local_file_path, 'wb') as f:
                f.write(decoded_data)
            print(f" [+] Saved file to: {local_file_path}")
        except Exception as e:
            print(f" [!] Failed to save file: {str(e)}")
            return
            
        # Process based on file extension
        file_ext = os.path.splitext(local_file_path)[1].lower()
        print(f" [+] File extension: {file_ext}")
        
        if file_ext in IMAGE_EXTENSIONS:
            print(f" [+] Processing image")
            result = process_image(local_file_path)
        elif file_ext in AUDIO_EXTENSIONS:
            print(f" [+] Processing audio")
            result = process_audio(local_file_path)
        elif file_ext in VIDEO_EXTENSIONS:
            print(f" [+] Processing video")
            result = process_video(local_file_path)
        elif file_ext in PDF_EXTENSIONS:
            if is_dynamic:
                print(f" [+] Processing dynamic")
                result = process_dynamic(local_file_path)
            else:
                print(f" [+] Processing pdf")
                result = process_pdf(local_file_path)
        elif file_ext in TEXT_EXTENSIONS:
            print(f" [+] Processing text")
            result = process_text(local_file_path)
        else:
            print(f" [-] Unsupported file type: {file_ext}")
            try:
                os.remove(local_file_path)
                print(f" [+] Cleaned up unsupported file: {local_file_path}")
            except Exception as e:
                print(f" [-] Error cleaning up unsupported file: {str(e)}")
            return
            
        # Extract tags from result
        tags = extract_tags(result, 5)
        deduped_tags = dedupe_tags(tags)

        print(f" [+] Extracted tags: {deduped_tags} for resource ID: {status_id}")
        
        # Send results back through RabbitMQ using the expected format
        send_message_to_queue("meta_tags_results", {
            'tags': deduped_tags,  # This matches the FileData field in TagsPayload
            'processed_resource_id': int(status_id)  # Convert to int to match Go's type
        })
        
        # Clean up our local file
        try:
            os.remove(local_file_path)
            print(f" [+] Cleaned up processed file: {local_file_path}")
        except Exception as e:
            print(f" [-] Error cleaning up processed file: {str(e)}")
        
        print(f" [+] Successfully processed file and sent tags for resource ID: {status_id}")
        
    except Exception as e:
        print(f" [-] Error processing message: {str(e)}")

# Modify the start_rabbitmq_consumer function
def start_rabbitmq_consumer():
    while True:  # Main reconnection loop
        try:
            credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
            connection = pika.BlockingConnection(
                pika.ConnectionParameters(
                    host=RABBITMQ_HOST,
                    port=RABBITMQ_PORT,
                    credentials=credentials,
                    virtual_host=RABBITMQ_VHOST,
                    heartbeat=60,  # Add heartbeat to detect connection issues
                    blocked_connection_timeout=300  # Timeout for blocked connections
                )
            )
            channel = connection.channel()
            
            # Declare the exchange
            channel.exchange_declare(
                exchange='meta_extraction',
                exchange_type='direct',
                durable=True
            )
            
            # Create a queue for this module
            result = channel.queue_declare(queue='', exclusive=True)
            queue_name = result.method.queue
            
            # Bind to the appropriate routing key
            channel.queue_bind(
                exchange='meta_extraction',
                queue=queue_name,
                routing_key=f'extract.{MODULE_ID}'
            )
            
            # Set QoS to handle messages one at a time
            channel.basic_qos(prefetch_count=1)
            
            channel.basic_consume(
                queue=queue_name,
                on_message_callback=callback,
                auto_ack=True
            )
            
            print(f" [*] Waiting for extraction requests...")
            
            try:
                channel.start_consuming()
            except KeyboardInterrupt:
                channel.stop_consuming()
                connection.close()
                break
            except pika.exceptions.ConnectionClosedByBroker:
                print(" [-] Connection was closed by broker, retrying...")
                continue
            except pika.exceptions.AMQPChannelError as err:
                print(f" [-] Channel error: {err}, retrying...")
                continue
            except pika.exceptions.AMQPConnectionError:
                print(" [-] Connection was lost, retrying...")
                continue
            except Exception as err:
                print(f" [-] Unexpected error: {err}, retrying...")
                continue
                
        except pika.exceptions.AMQPConnectionError:
            print(" [-] Initial connection failed, retrying in 5 seconds...")
            time.sleep(5)
            continue
        except Exception as err:
            print(f" [-] Unexpected error during setup: {err}, retrying in 5 seconds...")
            time.sleep(5)
            continue

if __name__ == "__main__":
    # Define module ID
    MODULE_ID = 'meta_generator_1'
    
    # Register with meta manager
    actual_module_id = register_module(MODULE_ID)
    if not actual_module_id:
        print(" [-] Failed to register module, exiting...")
        exit(1)
    
    # Start consuming messages
    start_rabbitmq_consumer()
