from flask import Flask, request, jsonify
import json
import traceback
import requests
import logging

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')


app = Flask(__name__)

with open('config/config.json', 'r') as f:
    config = json.load(f)

models = config['models']
self_models = []

for i in models:
    self_models.extend(i['category'])
self_models = list(set(self_models))


def index():
    models_str = ''
    for i in self_models:
        models_str += f'<li>{i}</li>'
    return f"<h1>API endpoints:</h1><ul><li>/*/models</li><li>/*/completions</li></ul><h2>Available models:</h2><ul>{models_str}</ul>"


def get_models(path=None):
    model_list = [{"id": model_name} for model_name in self_models]
    return jsonify({"data": model_list})


def chat_completions(path=None):
    request_data = json.loads(request.get_data(as_text=True))

    model_name = request_data.get('model', config.get('default_category'))
    if not model_name:
        return jsonify({"error": "Model name not provided"}), 400

    for model_config in models:
        if model_name not in model_config['category']: continue
        name = model_config["name"]
        
        logging.info(f'Using model: {name}')
        
        api_key = config['api_keys'][model_name]
        if api_key and request.headers.get('Authorization') != f'Bearer {api_key}':
            logging.warning(f'API key invalid for {name}')
            continue
        
        headers = {}
        
        payload = dict(request.json)
        headers['Authorization'] = f'Bearer {model_config["api_key"]}'
        payload['model'] = name
        try:
            logging.debug(f'posting request for {model_config["url"]}')
            logging.debug(f'{payload=}')
            response = requests.post(model_config['url'], headers=headers, json=payload)
            if response.status_code >= 300:
                logging.warning(f'LLM Call failed with response code {response.status_code} and message {response.text}')
                continue
            try:
                provider_error = json.loads(response.text.split('data:')[1]).get('error')
                if provider_error is not None:
                    print(f'PROVIDER ERROR: {provider_error}')
                    continue
            except:
                logging.error(traceback.format_exc())
            return response.text, response.status_code
        except:
            logging.error(traceback.format_exc())

    logging.error('No available models responded')
    return jsonify({"error": "No available models responded"}), 500


if __name__ == '__main__':
    app.add_url_rule('/', 'index', index)
    app.add_url_rule('/<path:path>/models', 'models', get_models)
    app.add_url_rule('/<path:path>/completions', 'completions', chat_completions)
    app.add_url_rule('/models', 'models', get_models)
    app.add_url_rule('/completions', 'completions', chat_completions)
    app.run(port=5000)
