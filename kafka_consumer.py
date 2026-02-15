import os
import json
import django
from confluent_kafka import Consumer
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

# --- CONFIGURATION ---
# 1. Setup Django Context
# Make sure 'judge_vortex' matches your actual project folder name
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'judge_vortex.settings')
django.setup()

from submissions.models import Submission

def run_consumer():
    # 2. Kafka Config
    conf = {
        'bootstrap.servers': 'kafka:9092',
        'group.id': 'judge-code-executor',  # Unique ID for execution
        'auto.offset.reset': 'earliest'
    }

    consumer = Consumer(conf)
    
    # 3. Subscribe to the SAME topic as your executor
    # Ensure this matches what your Django View sends
    consumer.subscribe(['submission_jobs']) 

    channel_layer = get_channel_layer()

    print("🚀 Status Consumer Started (Listening for jobs)...")

    try:
        while True:
            msg = consumer.poll(1.0)
            
            # Handle empty messages (timeouts)
            if msg is None: 
                continue
            
            # Handle Kafka Errors (Crucial for stability)
            if msg.error():
                print(f"⚠️ Consumer error: {msg.error()}")
                continue
            
            # 4. Parse Data
            try:
                data = json.loads(msg.value().decode('utf-8'))
                sub_id = data.get('submission_id') or data.get('id') # Handle both keys just in case
                
                print(f"📦 Status Update: Processing Submission #{sub_id}")

                # 5. Update DB to 'Processing'
                # This gives immediate feedback while Docker is spinning up
                try:
                    submission = Submission.objects.get(id=sub_id)
                    submission.status = 'Processing'
                    submission.save()

                    # 6. Notify WebSocket
                    async_to_sync(channel_layer.group_send)(
                        f'submission_{sub_id}',
                        {
                            'type': 'submission_update',
                            'message': {
                                'status': 'Processing', 
                                'submission_id': sub_id,
                                'result': 'Compiling...' # Temporary status text
                            }
                        }
                    )
                except Submission.DoesNotExist:
                    print(f"❌ Error: Submission {sub_id} not found in DB.")

            except json.JSONDecodeError:
                print("⚠️ Failed to decode JSON message")
                
    except KeyboardInterrupt:
        print("🛑 Stopping consumer...")
        consumer.close()

if __name__ == "__main__":
    run_consumer()