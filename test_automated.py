from openai import OpenAI
import sys
import time
import subprocess
import requests
import sys

venv_python_executable = sys.executable.replace("pythonw.exe", "python.exe") if "pythonw.exe" in sys.executable else sys.executable

proc = subprocess.Popen([venv_python_executable, "forwarder.py"], stderr=subprocess.PIPE, stdout=subprocess.PIPE)

time.sleep(5)

print(requests.get('http://localhost:5000').text)


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
try:
    for chunk in completion:
        if first_token_time == 0:
            first_token_time = time.time()
        print(chunk.choices[0].delta.content or "", end="", flush=True)
    print()
except Exception as e:
    print(f"Error in test_forwarder: {e}")


print(f'first token: {first_token_time-start_time:.2f}s')
print(f'Resp duration: {time.time() - first_token_time:.2f}s')

print('exiting app...')
proc.kill()
stdout, stderr = proc.communicate()
print(f'{stdout=}')
print(f'{stderr=}')
sys.exit()
