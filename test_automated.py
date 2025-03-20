from openai import OpenAI
import sys
import time
import subprocess
import requests
import logging
import threading

logging.basicConfig(level=logging.INFO, format='test: %(asctime)s - %(levelname)s - %(message)s')

venv_python_executable = sys.executable.replace("pythonw.exe", "python.exe") if "pythonw.exe" in sys.executable else sys.executable

def log_subprocess_output(pipe, logger, level):
    for line in iter(pipe.readline, b''):
        logger.log(level, line.decode('utf-8').rstrip())

proc = subprocess.Popen([venv_python_executable, "forwarder.py"], stderr=subprocess.PIPE, stdout=subprocess.PIPE)

stdout_thread = threading.Thread(target=log_subprocess_output, args=(proc.stdout, logging.getLogger("stdout"), logging.INFO))
stderr_thread = threading.Thread(target=log_subprocess_output, args=(proc.stderr, logging.getLogger("stderr"), logging.ERROR))
stdout_thread.daemon = True
stderr_thread.daemon = True
stdout_thread.start()
stderr_thread.start()

time.sleep(1)

logging.info(f"{requests.get('http://localhost:5000').text}")


client = OpenAI(
  base_url="http://localhost:5000/api/v1",
  api_key="any_key_if_undefined",
)

start_time = time.time()
first_token_time = 0

completion = client.chat.completions.create(
  extra_body={},
  model="free",
  messages=[
    {
      "role": "user",
      "content": "What is the meaning of life?"
    }
  ],
  stream=True
)

logging.info('Starting streaming response...')
try:
    for chunk in completion:
        if first_token_time == 0:
            first_token_time = time.time()
        print(f"{chunk.choices[0].delta.content or ''}", end="", flush=True)
    print("")
except Exception as e:
    logging.error(f"Error in test_forwarder: {e}")


logging.info(f'first token: {first_token_time-start_time:.2f}s')
logging.info(f'Resp duration: {time.time() - first_token_time:.2f}s')

logging.info('exiting app...')
proc.kill()
sys.exit()
