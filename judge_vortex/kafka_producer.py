from confluent_kafka import Producer
import json
import socket

# Connect to Kafka container
conf = {'bootstrap.servers': 'kafka:9092', 'client.id': socket.gethostname()}
producer = Producer(conf)

def send_submission_event(submission_id, code, language):
    topic = 'submission_jobs'
    message = {
        'id': submission_id,
        'code': code,
        'lang': language
    }
    
    producer.produce(topic, key=str(submission_id), value=json.dumps(message))
    producer.flush()
    print(f"🚀 Sent Submission #{submission_id} to Kafka.")