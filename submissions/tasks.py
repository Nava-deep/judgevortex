import subprocess
import os
import uuid
import time
import shutil
import re
from celery import shared_task
from django.conf import settings
from .models import Submission

# 1. UPDATED CONFIG (Using {filename} ensures names match exactly)
LANGUAGE_CONFIG = {
    'swift': {
        'image': 'swift:latest',
        'file_name': 'main.swift',
        'compile_cmd': 'swiftc /code/{filename} -o /code/main',
        'run_cmd': '/code/main'
    },
    'csharp': {
        'image': 'mcr.microsoft.com/dotnet/sdk:8.0-alpine',
        'file_name': 'Program.cs',
        'compile_cmd': 'dotnet new console -n app -o /code --force && dotnet build /code/app.csproj -o /code/build',
        'run_cmd': 'dotnet /code/build/app.dll'
    },
    'python': {
        'image': 'python:3.12-slim',
        'file_name': 'main.py',
        'run_cmd': 'python /code/{filename}'
    },
    'javascript': {
        'image': 'node:20-alpine',
        'file_name': 'main.js',
        'run_cmd': 'node /code/{filename}'
    },
    'bash': {
        'image': 'bash:5.2-alpine',
        'file_name': 'script.sh',
        'run_cmd': 'bash /code/{filename}'
    },
    'c': {
        'image': 'gcc:latest',
        'file_name': 'main.c',
        'compile_cmd': 'gcc /code/{filename} -o /code/main',
        'run_cmd': '/code/main'
    },
    'cpp': {
        'image': 'gcc:latest',
        'file_name': 'main.cpp',
        'compile_cmd': 'g++ /code/{filename} -o /code/main',
        'run_cmd': '/code/main'
    },
    'java': {
        'image': 'amazoncorretto:17-alpine',
        'file_name': 'Main.java',
        'compile_cmd': 'javac /code/{filename}',
        'run_cmd': 'java -cp /code {classname}'
    },
    'rust': {
        'image': 'rust:1.75-slim',
        'file_name': 'main.rs',
        'compile_cmd': 'rustc /code/{filename} -o /code/main',
        'run_cmd': '/code/main'
    },
    'go': {
        'image': 'golang:1.21-alpine',
        'file_name': 'main.go',
        'compile_cmd': 'go build -o /code/main /code/{filename}',
        'run_cmd': '/code/main'
    },
    'typescript': {
        'image': 'oven/bun:1',
        'file_name': 'main.ts',
        'run_cmd': 'bun run /code/{filename}'
    },
    'ruby': {
        'image': 'ruby:3.2-alpine',
        'file_name': 'main.rb',
        'run_cmd': 'ruby /code/{filename}'
    }
}

def run_docker(image, command, host_dir, input_data=None, timeout=30):
    # CRITICAL FIX: Docker volume mounts require ABSOLUTE paths
    abs_host_dir = os.path.abspath(host_dir)

    docker_cmd = [
        'docker', 'run', 
        '-i',             # Interactive (allows passing input)
        '--rm',           # Delete container after run
        '--network', 'none', # Disable internet for security
        '--memory', '512m',
        '-v', f'{abs_host_dir}:/code', # Mount host folder to /code
        '-w', '/code',    # Set working directory to /code
        image,
        '/bin/sh', '-c', command
    ]

    return subprocess.run(
        docker_cmd,
        input=input_data if input_data else "",
        capture_output=True,
        text=True,
        timeout=timeout
    )

@shared_task(soft_time_limit=65, time_limit=70)
def process_submission(submission_id):
    print(f"--> [Smart Runner] Processing {submission_id}")
    
    try:
        submission = Submission.objects.get(id=submission_id)
        
        # Reset previous results
        submission.stdout = ""
        submission.stderr = ""
        submission.result = "Processing"
        submission.save()

        lang = submission.language_id.lower()
        user_input = submission.custom_input or ""
        
        if lang not in LANGUAGE_CONFIG:
            submission.result = "System Error"
            submission.stderr = f"Language '{lang}' not supported."
            submission.status = Submission.Status.COMPLETED
            submission.save()
            return

        config = LANGUAGE_CONFIG[lang].copy()

        # 1. Create a Unique Folder for this submission
        unique_id = uuid.uuid4().hex[:8]
        # --- CRITICAL FIX: FORCE AZURE PATH ---
        # We explicitly tell the worker to use the path that matches the Host OS
        base_path = '/home/azureuser/judgevortex' 
        host_dir = os.path.join(base_path, 'temp_submissions', unique_id)
        # --------------------------------------

        # Ensure the folder exists (this will write to your server because of the volume map)
        os.makedirs(host_dir, exist_ok=True)

        # 2. Handle Java Class Names
        user_class = "Main"
        if lang == 'java':
            match = re.search(r'public\s+class\s+(\w+)', submission.source_code)
            if match:
                user_class = match.group(1)
                config['file_name'] = f"{user_class}.java"
        
        # 3. Write Source Code to File
        file_path = os.path.join(host_dir, config['file_name'])
        with open(file_path, 'w') as f:
            f.write(submission.source_code)
            
        submission.memory_used = len(submission.source_code.encode('utf-8'))
        
        try:
            # 4. COMPILATION PHASE
            if 'compile_cmd' in config:
                # Format command with the correct filename
                compile_command = config['compile_cmd'].format(filename=config['file_name'])
                
                c_result = run_docker(config['image'], compile_command, host_dir, input_data=None, timeout=60)
                
                if c_result.returncode != 0:
                    submission.result = "Compilation Error"
                    submission.stderr = c_result.stderr or c_result.stdout # Capture error output
                    submission.stdout = ""
                    submission.execution_time = 0
                    submission.status = Submission.Status.COMPLETED
                    submission.save()
                    shutil.rmtree(host_dir) # Clean up
                    return 

            # 5. EXECUTION PHASE
            run_command = config['run_cmd'].format(classname=user_class, filename=config['file_name'])
            
            start_time = time.perf_counter()
            r_result = run_docker(config['image'], run_command, host_dir, input_data=user_input, timeout=60)
            end_time = time.perf_counter()
            
            # Calculate Time
            total_time = end_time - start_time
            # Subtract overhead (approx 1.5s for Docker startup) but keep it positive
            submission.execution_time = max(round(total_time - 1.5, 3), 0.01)

            if r_result.returncode == 0:
                submission.result = "Accepted"
                submission.stdout = r_result.stdout
                submission.stderr = ""
            else:
                submission.result = "Runtime Error"
                submission.stderr = r_result.stderr
                submission.stdout = r_result.stdout

        except subprocess.TimeoutExpired:
            submission.result = "Time Limit Exceeded"
            submission.stderr = "Code took too long to execute."

        except Exception as e:
            submission.result = "System Error"
            submission.stderr = str(e)

        finally:
            # Clean up the folder
            if os.path.exists(host_dir):
                shutil.rmtree(host_dir)

        submission.status = Submission.Status.COMPLETED
        submission.save()
        print(f"--> [Smart Runner] Finished {submission_id}: {submission.result}")

    except Exception as e:
        print(f"CRITICAL ERROR in Worker: {e}")