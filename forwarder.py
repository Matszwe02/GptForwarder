from flask import Flask, request, jsonify, stream_with_context
from werkzeug.wrappers import Response
import json
import requests
import logging
import os
import threading
import queue


os.makedirs('logs', exist_ok=True)
os.makedirs('config', exist_ok=True)
logging.basicConfig(level=os.environ.get("LOGGING_LEVEL", "warning").upper(), format='%(asctime)s - %(levelname)s - %(message)s', filename='logs/python.log', filemode='a')

logging.info('Starting app')
app = Flask(__name__)


config = {}
models = []
categories = []
default_models = {}  # Category: model_name


def load_config():
    global categories, config, models
    try:
        with open('config/config.json', 'r') as f:
            config = json.load(f)
        models = config['models']
        categories = []
        for i in models:
            categories.extend(i['category'])
        categories = list(set(categories))
    except Exception as e:
        logging.error(f'Cannot read or parse config! {e}')


def index():
    load_config()
    models_str = ''
    try:
        for i in categories:
            models_str += f'<li>{i}</li>'
    except: pass
    return f"<h1>API endpoints:</h1><ul><li>/*/models</li><li>/*/completions</li></ul><h2>Available models:</h2><ul>{models_str}</ul>"


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
                default_models.pop(category, None)
    
    for model_config in models:
        if category not in model_config['category']:
            continue
        if model_config.get('latch', False) == True:
            logging.info(f'Trying latch model: {model_config["name"]} ({category})')
            response = process_model_request(model_config, request_data, category, model_exceptions)
            if response:
                default_models[category] = model_config['name']
                return response
    
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
        return Response(stream_with_context(generate()), mimetype=response.headers.get('Content-Type', 'text/plain')), response.status_code
    
    except Exception as e:
        logging.warning(e)
        model_exceptions.append(f'Python Error: {e}')
        return None


app.add_url_rule('/', 'index', index)
app.add_url_rule('/<path:path>/models', 'models', get_models)
app.add_url_rule('/<path:path>/completions', 'completions', chat_completions, methods=['POST'])
app.add_url_rule('/models', 'models', get_models)
app.add_url_rule('/completions', 'completions', chat_completions, methods=['POST'])

if __name__ == '__main__':
    app.run(port=5000)
