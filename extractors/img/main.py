import os
import time
import json
import base64
import pika
from PIL import Image
import torch
from transformers import BlipProcessor, BlipForConditionalGeneration
from dotenv import load_dotenv

print(" [x] Loading models...")
blip_processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base")
blip_model = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-base")
print(" [+] Model loading done...")

load_dotenv()

RABBITMQ_HOST = os.getenv('RABBIT_HOST', 'localhost')
RABBITMQ_USER = os.getenv('RABBIT_USER', 'dp-processor')
RABBITMQ_PASS = os.getenv('RABBIT_PASS', 'dp-processor')
RABBITMQ_VHOST = os.getenv('RABBIT_VHOST', '/')
RABBITMQ_PORT = os.getenv('RABBIT_PORT', 5672)

print(f" [+] RabbitMQ Host: {RABBITMQ_HOST}, User: {RABBITMQ_USER}, VHost: {RABBITMQ_VHOST}, Password: ****")

credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)

def process_image(file_path):
    """Process image file and extract metadata using BLIP"""
    try:
        # Load image
        image = Image.open(file_path)
        
        # Generate caption using BLIP
        inputs = blip_processor(image, return_tensors="pt")
        out = blip_model.generate(**inputs)
        caption = blip_processor.decode(out[0], skip_special_tokens=True)
        
        return caption
    except Exception as e:
        print(f"Error processing image file: {str(e)}")
        return None

def send_message_to_queue(queue_name, message):
    """Send message to RabbitMQ queue"""
    try:
        connection = pika.BlockingConnection(pika.ConnectionParameters(
            host=RABBITMQ_HOST,
            credentials=credentials,
            virtual_host=RABBITMQ_VHOST,
            port=RABBITMQ_PORT
        ))
        channel = connection.channel()

        channel.queue_declare(queue=queue_name, durable=True)
        message_json = json.dumps(message)

        channel.basic_publish(
            exchange='',
            routing_key=queue_name,
            body=message_json,
            properties=pika.BasicProperties(delivery_mode=2)
        )
        print(f" [*] Message sent to queue '{queue_name}'")
    except Exception as e:
        print(f"Failed to publish message: {str(e)}")
    finally:
        if 'connection' in locals() and connection.is_open:
            connection.close()
            print(" [*] Connection closed after sending the message.")

def dedupe_caption(caption):
    """Deduplicate caption by removing duplicate words"""
    words = caption.split()
    unique_words = list(set(words))
    return unique_words

def callback(ch, method, properties, body):
    """Callback function for RabbitMQ messages"""
    try:
        data = json.loads(body)
        file_path = data.get('filename')
        file_name = os.path.basename(file_path)
        file_data = data.get('filedata')  # base64 encoded
        status_id = data.get('status_id')
        
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
            
        # Process the image file
        #########################EDITME###################################
        ##### CHANGE THIS FUNCTION TO EXTRACT METADATA FROM THE FILE #####
        ##################################################################
        caption = process_image(local_file_path)
        deduped_caption = dedupe_caption(caption)
        
        if caption:
            # Send results back through RabbitMQ
            send_message_to_queue("meta_tags_results", {
                'tags': deduped_caption,  # Using the caption as a tag
                'processed_resource_id': int(status_id)
            })
            
        # Clean up local file
        try:
            os.remove(local_file_path)
            print(f" [+] Cleaned up processed file: {local_file_path}")
        except Exception as e:
            print(f" [-] Error cleaning up processed file: {str(e)}")
        
        print(f" [+] Successfully processed file and sent tags for resource ID: {status_id}")
        
    except Exception as e:
        print(f" [-] Error processing message: {str(e)}")

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
            'supported_extensions': ['.png', '.jpg', '.jpeg']  # Image extractor supports these formats
                ######################EDITME############################
                ##### EDIT THIS BASED ON SUPPORTED FILE EXTENSIONS #####
                ########################################################
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

def check_module_availability(module_id):
    """Check if a module ID is available"""
    try:
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(
                host=RABBITMQ_HOST,
                port=RABBITMQ_PORT,
                credentials=credentials,
                virtual_host=RABBITMQ_VHOST,
                heartbeat=60,
                blocked_connection_timeout=300
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

def start_rabbitmq_consumer():
    """Start RabbitMQ consumer for image processing"""
    while True:  # Main reconnection loop
        try:
            connection = pika.BlockingConnection(
                pika.ConnectionParameters(
                    host=RABBITMQ_HOST,
                    port=RABBITMQ_PORT,
                    credentials=credentials,
                    virtual_host=RABBITMQ_VHOST,
                    heartbeat=60,
                    blocked_connection_timeout=300
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
            
            print(f" [*] Waiting for image extraction requests...")
            
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
    MODULE_ID = 'image_meta_extractor_1'
    
    # Register with meta manager
    actual_module_id = register_module(MODULE_ID)
    if not actual_module_id:
        print(" [-] Failed to register module, exiting...")
        exit(1)
    
    # Start consuming messages
    start_rabbitmq_consumer() 