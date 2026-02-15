import os
import django
import json
import docker
import shlex  # Required to safely quote code for shell commands
from confluent_kafka import Consumer
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

# --- CONFIGURATION ---
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'judge_vortex.settings')
django.setup()

from submissions.models import Submission

# Kafka Config
conf = {
    'bootstrap.servers': 'localhost:29092', 
    'group.id': 'judge-code-executor', 
    'auto.offset.reset': 'earliest'
}

consumer = Consumer(conf)
consumer.subscribe(['submission_jobs'])

client = docker.from_env()
channel_layer = get_channel_layer()

print("🚀 Multi-Language Executor Engine Started...")

def run_code_in_docker(code, language):
    """
    Executes code for 14 different languages using dedicated Docker containers.
    """
    
    # --- LANGUAGE CONFIGURATION ---
    # 1. Image: The Docker container to use.
    # 2. Command: The shell script to Write -> Compile -> Run the code.
    # We use 'sh -c' + 'echo' to write the user's code to a file inside the container first.
    
    LANGUAGE_CONFIG = {
        # Python
        'python': {
            'image': 'python:3.9-slim',
            'cmd': 'sh -c "echo {} > main.py && python3 main.py"'
        },
        # C++ (GCC)
        'cpp': {
            'image': 'gcc:latest',
            'cmd': 'sh -c "echo {} > main.cpp && g++ main.cpp -o main && ./main"'
        },
        # C (GCC)
        'c': {
            'image': 'gcc:latest',
            'cmd': 'sh -c "echo {} > main.c && gcc main.c -o main && ./main"'
        },
        # Java (OpenJDK) - Requires class to be named 'Main'
        'java': {
            'image': 'openjdk:17-slim',
            'cmd': 'sh -c "echo {} > Main.java && javac Main.java && java Main"'
        },
        # JavaScript (Node.js)
        'javascript': {
            'image': 'node:18-alpine',
            'cmd': 'sh -c "echo {} > main.js && node main.js"'
        },
        # TypeScript (Using Deno for native TS support without config)
        'typescript': {
            'image': 'denoland/deno:alpine',
            'cmd': 'sh -c "echo {} > main.ts && deno run main.ts"'
        },
        # C# (Mono is lighter than .NET SDK for simple scripts)
        'csharp': {
            'image': 'mono:6.12-slim',
            'cmd': 'sh -c "echo {} > main.cs && mcs -out:main.exe main.cs && mono main.exe"'
        },
        # Go
        'go': {
            'image': 'golang:1.19-alpine',
            'cmd': 'sh -c "echo {} > main.go && go run main.go"'
        },
        # Rust
        'rust': {
            'image': 'rust:1.67-alpine',
            'cmd': 'sh -c "echo {} > main.rs && rustc main.rs && ./main"'
        },
        # PHP
        'php': {
            'image': 'php:8.2-cli-alpine',
            'cmd': 'sh -c "echo {} > main.php && php main.php"'
        },
        # Ruby
        'ruby': {
            'image': 'ruby:alpine',
            'cmd': 'sh -c "echo {} > main.rb && ruby main.rb"'
        },
        # Swift
        'swift': {
            'image': 'swift:5.7-slim',
            'cmd': 'sh -c "echo {} > main.swift && swift main.swift"'
        },
        # Kotlin
        'kotlin': {
            'image': 'zenika/kotlin', # Lightweight Kotlin image
            'cmd': 'sh -c "echo {} > main.kt && kotlinc main.kt -include-runtime -d main.jar && java -jar main.jar"'
        },
        # Bash
        'bash': {
            'image': 'bash:5.2',
            'cmd': 'sh -c "echo {} > script.sh && bash script.sh"'
        }
    }

    # Normalize language ID (lowercase) and fetch config
    lang_key = language.lower()
    config = LANGUAGE_CONFIG.get(lang_key)

    if not config:
        return "System Error", f"Language '{language}' is not supported yet."

    image = config['image']
    
    # SECURITY: Use shlex to escape the user's code safely.
    # This turns 'print("Hello")' into ''"'"'print("Hello")'"'"'' so it can be echo'd safely.
    safe_code = shlex.quote(code)
    
    # Format the final execution command
    final_command = config['cmd'].format(safe_code)

    try:
        # Spin up the container
        logs = client.containers.run(
            image=image,
            command=final_command,
            detach=False,
            stdout=True,
            stderr=True,
            network_disabled=True,      # No Internet Access
            mem_limit='256m',           # Increased to 256MB for Java/Kotlin/Swift
            cpu_period=100000,
            cpu_quota=50000,            # 50% CPU Cap
        )
        return "Accepted", logs.decode('utf-8')
    
    except docker.errors.ContainerError as e:
        # Returns standard error (Compiler errors, Runtime crashes)
        return "Runtime Error", e.stderr.decode('utf-8') if e.stderr else str(e)
    except docker.errors.ImageNotFound:
        return "System Error", f"Docker image {image} missing. Please run 'docker pull {image}'"
    except Exception as e:
        return "System Error", str(e)

# --- MAIN CONSUMER LOOP ---
while True:
    msg = consumer.poll(1.0)
    if msg is None: continue

    try:
        data = json.loads(msg.value().decode('utf-8'))
        sub_id = data.get('id') or data.get('submission_id')
        code = data.get('code')
        lang = data.get('language', 'python')

        print(f"🛠️  Job #{sub_id}: Executing {lang}...")

        # --- RUN ---
        result, output = run_code_in_docker(code, lang)
        # -----------

        # Update DB & Notify
        try:
            sub = Submission.objects.get(id=sub_id)
            sub.result = result
            sub.stdout = output
            sub.status = 'Completed'
            sub.save()

            async_to_sync(channel_layer.group_send)(
                f'submission_{sub_id}',
                {
                    'type': 'submission_update',
                    'message': {
                        'status': 'Completed',
                        'result': result,
                        'stdout': output,
                        'submission_id': sub_id
                    }
                }
            )
            print(f"✅ Job #{sub_id} Finished: {result}")
            
        except Submission.DoesNotExist:
            print(f"❌ Submission {sub_id} not found.")
            
    except Exception as e:
        print(f"⚠️ Error: {str(e)}")