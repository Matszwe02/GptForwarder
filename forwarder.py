from flask import Flask, request, jsonify, stream_with_context, render_template
from werkzeug.wrappers import Response
import json
import requests
import logging
import os
import threading
import queue
import time
from collections import defaultdict
import re
import fcntl # For file locking


os.makedirs('logs', exist_ok=True)
os.makedirs('config', exist_ok=True)
logging.basicConfig(level=os.environ.get("LOGGING_LEVEL", "warning").upper(), format='%(asctime)s - %(levelname)s - %(message)s', filename='logs/python.log', filemode='a')

logging.info('Starting app')
app = Flask(__name__)

config = {}
models = []
categories = []
retries = 0
retry_delay = 0

SHARED_STATE_FILE = 'config/shared_state.json'
SHARED_STATE_LOCK_FILE = './shared_state.lock'

default_models = {}  # Category: model_name
request_timestamps = defaultdict(list)

def load_shared_state():
    global default_models, request_timestamps
    try:
        with open(SHARED_STATE_FILE, 'r') as f:
            state = json.load(f)
            default_models = state.get('default_models', {})
            loaded_timestamps = state.get('request_timestamps', {})
            request_timestamps = defaultdict(list, {k: v for k, v in loaded_timestamps.items()})
    except Exception as e:
        logging.error(f'Error loading shared state: {e}')

def save_shared_state():
    try:
        with open(SHARED_STATE_LOCK_FILE, 'w') as lock_file:
            fcntl.flock(lock_file, fcntl.LOCK_EX) # Acquire exclusive lock
            state = {
                'default_models': default_models,
                'request_timestamps': dict(request_timestamps) # Convert defaultdict to dict for serialization
            }
            with open(SHARED_STATE_FILE, 'w') as f:
                json.dump(state, f, indent=4)
            fcntl.flock(lock_file, fcntl.LOCK_UN) # Release lock
    except Exception as e:
        logging.error(f'Error saving shared state: {e}')

load_shared_state()

get_friendly_name = lambda model_config: f"{model_config['name']} ({re.search(r'[a-zA-Z0-9]{2,}(\.[a-zA-Z0-9]{2,})(\.[a-zA-Z0-9]{2,})?', model_config['url']).group()})"



def record_request(model_config):
    timestamp = time.time()
    one_week_ago = timestamp - (7 * 24 * 3600)
    model_friendly_name = get_friendly_name(model_config)

    request_timestamps[model_friendly_name] = [ts for ts in request_timestamps[model_friendly_name] if ts > one_week_ago]
    request_timestamps[model_friendly_name].append(timestamp)


def get_request_counts(model_identifier):
    now = time.time()
    one_hour_ago = now - 3600
    one_day_ago = now - 86400
    one_week_ago = now - (7 * 24 * 3600)

    last_hour_count = sum(1 for ts in request_timestamps[model_identifier] if ts > one_hour_ago)
    last_day_count = sum(1 for ts in request_timestamps[model_identifier] if ts > one_day_ago)
    last_week_count = sum(1 for ts in request_timestamps[model_identifier] if ts > one_week_ago)
    return last_hour_count, last_day_count, last_week_count


def load_config():
    global categories, config, models, retries, retry_delay
    load_shared_state()
    try:
        with open('config/config.json', 'r') as f:
            config = json.load(f)
        models = config['models']
        categories = []
        for i in models:
            categories.extend(i['category'])
        categories = list(set(categories))
        retries = max(config.get('retries', 0), 0)
        retry_delay = max(config.get('retry_delay', 0), 0)
    except Exception as e:
        logging.error(f'Cannot read or parse config! {e}')



def get_models(path=None):
    load_config()
    model_list = [{"id": category} for category in categories]
    return jsonify({"data": model_list})


def chat_completions(path=None):
    global default_models
    
    logging.debug(f'Received request for {path or ""}/completions')
    load_config()
    request_data = json.loads(request.get_data(as_text=True))
    
    logging.info(f'{default_models=}')
    
    category = request_data.get('model', config.get('default_category'))
    if not category:
        return jsonify({"error": "Model name not provided"}), 400
    
    model_exceptions = []
    
    default_model_name = default_models.get(category)
    if default_model_name:
        default_model_config = next((m for m in models if m['name'] == default_model_name and category in m['category']), None)
        if default_model_config:
            logging.info(f'Trying default model: {default_model_name} ({category})')
            response = process_model_request(default_model_config, request_data, category, model_exceptions)
            if response:
                return response
            else:
                logging.warning(f'Default model {default_model_name} failed, removing default.')
                load_shared_state()
                default_models.pop(category, None)
                save_shared_state()
    
    for _ in range(retries + 1):
        for model_config in models:
            if category not in model_config['category']:
                continue
            if model_config.get('latch', False) == True:
                logging.info(f'Trying latched model: {model_config["name"]} ({category})')
                response = process_model_request(model_config, request_data, category, model_exceptions)
                if response:
                    load_shared_state()
                    default_models[category] = model_config['name']
                    save_shared_state()
                    return response
        
        for model_config in models:
            if category not in model_config['category']:
                continue
            if model_config.get('latch', False) == False:
                logging.info(f'Trying model: {model_config["name"]} ({category})')
                response = process_model_request(model_config, request_data, category, model_exceptions)
                if response:
                    return response
        time.sleep(retry_delay)
    
    logging.error(f"No available models responded: {'; '.join(model_exceptions)}")
    return jsonify({"error": f"No available models responded:\n\n{'\n'.join(model_exceptions)}"}), 500


def process_model_request(model_config, request_data, category, model_exceptions):
    name = model_config["name"]
    url = model_config['url']
    
    logging.info(f'Using model: {name} ({category})')
    
    api_key = config['api_keys'][category]
    if api_key and request.headers.get('Authorization') != f'Bearer {api_key}':
        logging.warning(f'API key invalid for {name}')
        model_exceptions.append(f'API key invalid for {name}')
        return None
    
    headers = {}
    payload = dict(request_data)
    headers['Authorization'] = f'Bearer {model_config["api_key"]}'
    payload['model'] = name
    try:
        logging.info(f'posting request for {url}')
        logging.debug(f'{payload=}')
        response = requests.post(url, headers=headers, json=payload, stream=True, timeout=2)
        if response.status_code >= 300:
            logging.warning(f'LLM Call failed with response code {response.status_code} and message {response.text}')
            model_exceptions.append(f'LLM Call failed with response code {response.status_code} and message {response.text}')
            return None
        
        chunk_queue = queue.Queue()
        start_generating = threading.Event()
        error_found = False
        
        def process_chunks():
            nonlocal error_found
            wait_for_tokens = True
            try:
                for chunk in response.iter_content(chunk_size=None):
                    chunk_queue.put(chunk)
                    logging.debug(f'streaming "{str(chunk, encoding='utf-8')}"')
                    if wait_for_tokens:
                        try:
                            data = json.loads(str(chunk, encoding='utf-8').removeprefix('data:'))
                            error_name = data.get('error', {}).get('message', '')
                            if len(error_name) > 1:
                                error_found = True
                                model_exceptions.append(f'API returned an error: {error_name}')
                                logging.debug(f'API returned an error: {error_name}')
                                start_generating.set()
                                return
                            wait_for_tokens = False
                            start_generating.set()
                        except:
                            logging.debug(f'waiting for tokens to generate')
            finally:
                start_generating.set()
                chunk_queue.put(None)  # Ensure generator stops
        
        def generate():
            while True:
                chunk = chunk_queue.get()
                if chunk is None:
                    break  # End of stream
                yield chunk
        
        threading.Thread(target=process_chunks).start()
        
        start_generating.wait()  # Wait for the first 3 chunks to be processed
        if error_found:
            logging.warning(f'API returned an error - switching to next model')
            return None
        
        logging.info(f'returning resp with {url} ({name})')
        load_shared_state()
        record_request(model_config) # Record the request
        save_shared_state()
        
        return Response(stream_with_context(generate()), mimetype=response.headers.get('Content-Type', 'text/plain')), response.status_code
    
    except requests.exceptions.Timeout as e:
        logging.warning(f'LLM Call timed out: {e}')
        model_exceptions.append(f'LLM Call timed out: {e}')
        return None
    except Exception as e:
        logging.warning(e)
        model_exceptions.append(f'Python Error: {e}')
        return None


def index():
    load_config()
    model_stats = {}
    for model_config in models:
        last_hour, last_day, last_week = get_request_counts(get_friendly_name(model_config))
        model_stats[get_friendly_name(model_config)] = {'last_hour': last_hour, 'last_day': last_day, 'last_week': last_week}
    return render_template('index.html', categories=categories, model_stats=model_stats)


def chat():
    return render_template('chat.html')


app.add_url_rule('/<path:path>/models', 'models', get_models)
app.add_url_rule('/<path:path>/completions', 'completions', chat_completions, methods=['POST'])
app.add_url_rule('/models', 'models', get_models)
app.add_url_rule('/completions', 'completions', chat_completions, methods=['POST'])
app.add_url_rule('/', 'index', index)
app.add_url_rule('/chat', 'chat', chat)

if __name__ == '__main__':
    app.run(port=5000)
