import os
import django
import json
import time
from confluent_kafka import Consumer
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

# Setup Django Context (to access DB and Channels)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'judgevortex.settings')
django.setup()

from submissions.models import Submission

# Kafka Config
conf = {
    'bootstrap.servers': 'localhost:29092', # Localhost if running outside Docker
    'group.id': 'python_executors',
    'auto.offset.reset': 'earliest'
}
consumer = Consumer(conf)
consumer.subscribe(['submission_jobs'])

print("🔥 Executor Microservice Started...")

channel_layer = get_channel_layer()

while True:
    msg = consumer.poll(1.0)
    if msg is None: continue

    data = json.loads(msg.value().decode('utf-8'))
    sub_id = data['id']
    print(f"Processing Job #{sub_id}...")

    # --- EXECUTION LOGIC (Simulated) ---
    # In production, call Piston API or Docker here
    time.sleep(2) 
    result = "Accepted"
    output = "Hello World\n(Executed via Kafka)"
    # -----------------------------------

    # Update DB
    try:
        sub = Submission.objects.get(id=sub_id)
        sub.result = result
        sub.stdout = output
        sub.save()

        # Push to WebSocket (Real-Time)
        async_to_sync(channel_layer.group_send)(
            f'submission_{sub_id}',
            {
                'type': 'submission_update',
                'message': {
                    'status': 'Completed',
                    'result': result,
                    'stdout': output
                }
            }
        )
        print(f"✅ Job #{sub_id} Finished & Notified.")
    except Submission.DoesNotExist:
        print("Submission not found in DB")