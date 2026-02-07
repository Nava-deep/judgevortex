import subprocess
import os
import uuid
import time
import shutil
import re
from celery import shared_task
from django.conf import settings
from .models import Submission

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
        'image': 'devel-alphine3.23',
        'file_name': 'script.sh',
        'run_cmd': 'bash /code/script.sh'
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
    },
    'php': {
        'image': 'php:8.2-cli-alpine',
        'file_name': 'main.php',
        'run_cmd': 'php /code/{filename}'
    },
    'kotlin': {
        'image': 'judge-kotlin:latest',
        'file_name': 'main.kt',
        'compile_cmd': 'kotlinc /code/{filename} -include-runtime -d /code/main.jar',
        'run_cmd': 'java -cp /code/main.jar MainKt' 
    },
}

def run_docker(image, command, host_dir, input_data=None, timeout=30):
    # This host_dir MUST be the Azure Server path (/home/azureuser/...)
    # We trust the logic in process_submission to pass the correct path.
    
    docker_cmd = [
        'docker', 'run', 
        '-i',             # Interactive
        '--rm',           # Delete container after run
        '--network', 'none', # Security: No internet
        '--memory', '512m',
        '-v', f'{host_dir}:/code', # Mount the Azure Host Path to /code
        '-w', '/code',    # Set working directory
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
        
        # Reset results
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

        # 1. Create UNIQUE ID
        unique_id = uuid.uuid4().hex[:8]

        # ---------------------------------------------------------
        # THE FIX: PATH TRANSLATION
        # ---------------------------------------------------------
        
        # A. Internal Path (Where Python WRITES the file inside the container)
        # This is usually /app/temp_submissions/xyz
        internal_dir = os.path.join(settings.BASE_DIR, 'temp_submissions', unique_id)
        os.makedirs(internal_dir, exist_ok=True)

        # B. Host Path (Where Docker LOOKS for the file on the server)
        # We manually construct the path to match your Azure server structure
        # /home/azureuser/judgevortex/temp_submissions/xyz
        host_base = '/home/azureuser/judgevortex'
        host_dir = os.path.join(host_base, 'temp_submissions', unique_id)

        print(f"--> [DEBUG] Internal Write Path: {internal_dir}")
        print(f"--> [DEBUG] External Mount Path: {host_dir}")
        # ---------------------------------------------------------

        # 2. Handle Java Class Names
        user_class = "Main"
        if lang == 'java':
            match = re.search(r'public\s+class\s+(\w+)', submission.source_code)
            if match:
                user_class = match.group(1)
                config['file_name'] = f"{user_class}.java"
        
        # 3. Write Code to INTERNAL Path
        file_path = os.path.join(internal_dir, config['file_name'])
        with open(file_path, 'w') as f:
            f.write(submission.source_code)
            
        submission.memory_used = len(submission.source_code.encode('utf-8'))
        
        try:
            # 4. COMPILATION
            if 'compile_cmd' in config:
                compile_command = config['compile_cmd'].format(filename=config['file_name'])
                
                # We pass 'host_dir' (Azure path) so Docker finds the file
                c_result = run_docker(config['image'], compile_command, host_dir, input_data=None, timeout=60)
                
                if c_result.returncode != 0:
                    submission.result = "Compilation Error"
                    submission.stderr = c_result.stderr or c_result.stdout
                    submission.stdout = ""
                    submission.execution_time = 0
                    submission.status = Submission.Status.COMPLETED
                    submission.save()
                    shutil.rmtree(internal_dir) # Clean up internal path
                    return 

            # 5. EXECUTION
            run_command = config['run_cmd'].format(classname=user_class, filename=config['file_name'])
            
            start_time = time.perf_counter()
            r_result = run_docker(config['image'], run_command, host_dir, input_data=user_input, timeout=60)
            end_time = time.perf_counter()
            
            total_time = end_time - start_time
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
            # Clean up using INTERNAL path
            if os.path.exists(internal_dir):
                shutil.rmtree(internal_dir)

        submission.status = Submission.Status.COMPLETED
        submission.save()
        print(f"--> [Smart Runner] Finished {submission_id}: {submission.result}")

    except Exception as e:
        print(f"CRITICAL ERROR in Worker: {e}")