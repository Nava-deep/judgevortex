import os
import json
import django
from confluent_kafka import Consumer

# Initialize Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'judge_vortex.settings')
django.setup()

from submissions.models import Submission 

def run_consumer():
    conf = {
        'bootstrap.servers': 'kafka:9092',
        'group.id': 'judge-group',
        'auto.offset.reset': 'earliest'
    }

    consumer = Consumer(conf)
    consumer.subscribe(['code_submissions'])

    print("🚀 Judge Vortex Consumer is listening for code...")

    try:
        while True:
            msg = consumer.poll(1.0)
            if msg is None: continue
            if msg.error():
                print(f"Consumer error: {msg.error()}")
                continue

            data = json.loads(msg.value().decode('utf-8'))
            submission_id = data.get('submission_id')
            print(f"📦 Processing Submission ID: {submission_id}")
            
    except KeyboardInterrupt:
        pass
    finally:
        consumer.close()

if __name__ == "__main__":
    run_consumer()