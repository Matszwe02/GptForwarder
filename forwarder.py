from flask import Flask, request, jsonify
import json
import traceback
import requests
import logging
from werkzeug.wrappers import Response
from flask import stream_with_context
import os

logging.basicConfig(level=os.environ.get("LOGGING_LEVEL", "info").upper(), format='%(asctime)s - %(levelname)s - %(message)s')


app = Flask(__name__)

with open('config/config.json', 'r') as f:
    config = json.load(f)

models = config['models']
self_models = []

for i in models:
    self_models.extend(i['category'])
self_models = list(set(self_models))

@app.route('/')
def main():
    return "<h1>API endpoints:</h1><ul><li>/api/v1/models</li><li>/api/v1/chat/completions</li></ul>"


@app.route('/api/v1/models', methods=['GET'])
def get_models():
    model_list = [{"id": model_name} for model_name in self_models]
    return jsonify({"data": model_list})

@app.route('/api/v1/chat/completions', methods=['POST'])
def chat_completions():
    request_data = json.loads(request.get_data(as_text=True))

    model_name = request_data.get('model', config.get('default_category'))
    if not model_name:
        return jsonify({"error": "Model name not provided"}), 400

    for model_config in models:
        if model_name not in model_config['category']: continue
        name = model_config["name"]
        url = model_config['url']
        
        logging.info(f'Using model: {name} ({name})')
        
        api_key = config['api_keys'][model_name]
        if api_key and request.headers.get('Authorization') != f'Bearer {api_key}':
            logging.warning(f'API key invalid for {name}')
            continue
        
        headers = {}
        
        payload = dict(request.json)
        headers['Authorization'] = f'Bearer {model_config["api_key"]}'
        payload['model'] = name
        try:
            logging.debug(f'posting request for {url}')
            logging.debug(f'{payload=}')
            response = requests.post(url, headers=headers, json=payload, stream=True, timeout=2)
            if response.status_code >= 300:
                logging.warning(f'LLM Call failed with response code {response.status_code} and message {response.text}')
                continue

            def generate():
                for chunk in response.iter_content(chunk_size=None):
                    logging.debug('streaming')
                    yield chunk

            logging.info(f'returning resp with {url} ({name})')
            return Response(stream_with_context(generate()), mimetype=response.headers.get('Content-Type', 'text/plain')), response.status_code

        except Exception as e:
            logging.warning(e)

    logging.error('No available models responded')
    return jsonify({"error": "No available models responded"}), 500


if __name__ == '__main__':
    app.run(port=5000)
