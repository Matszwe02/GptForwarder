from flask import Flask, request, jsonify
import json
import traceback
import requests


app = Flask(__name__)

with open('config/config.json', 'r') as f:
    config = json.load(f)

models = config['models']
self_models = []

for i in models:
    self_models.extend(i['category'])
self_models = list(set(self_models))

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
        
        print(f'using {name}')
        
        api_key = config['api_keys'][model_name]
        if api_key and request.headers.get('Authorization') != f'Bearer {api_key}':
            print(f'API key invalid for {name}')
            continue
        
        # headers = {}
        headers = dict(request.headers)
        headers.pop('Host', None)
        
        payload = dict(request.json)
        headers['Authorization'] = f'Bearer {model_config["api_key"]}'
        payload['model'] = name
        try:
            response = requests.post(model_config['url'], headers=headers, json=payload)
            if response.status_code >= 300: continue
            try:
                provider_error = json.loads(response.text.split('data:')[1]).get('error')
                if provider_error is not None:
                    print(f'PROVIDER ERROR: {provider_error}')
                    continue
            except: pass
            return response.text, response.status_code
        except:
            traceback.print_exc()

    print('No available models responded')
    return jsonify({"error": "No available models responded"}), 500
if __name__ == '__main__':
    app.run(port=5000)
