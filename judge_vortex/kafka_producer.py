import json
import socket
from confluent_kafka import Producer

# --- CONFIGURATION ---
# 'kafka:9092' assumes this script runs INSIDE a Docker container (like your Django app).
# If running locally (outside Docker), change this to 'localhost:29092'.
conf = {
    'bootstrap.servers': 'kafka:9092', 
    'client.id': socket.gethostname()
}

producer = Producer(conf)

def delivery_report(err, msg):
    """ Called once for each message produced to indicate delivery result. """
    if err is not None:
        print(f"❌ Message delivery failed: {err}")
    else:
        print(f"✅ Message delivered to {msg.topic()} [{msg.partition()}]")

def send_submission_event(submission_id, code, language):
    topic = 'submission_jobs'
    
    # Payload matches what executor_service.py expects
    message = {
        'id': submission_id,
        'code': code,
        'language': language  # CRITICAL: Changed from 'lang' to 'language'
    }
    
    # Produce the message
    producer.produce(
        topic, 
        key=str(submission_id), 
        value=json.dumps(message), 
        callback=delivery_report
    )
    
    # Flush ensures the message is sent before the function ends
    producer.flush()
    print(f"🚀 Sent Submission #{submission_id} to Kafka.")