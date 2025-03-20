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
    stream_response = request_data.get('stream', False)
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
            
            if stream_response:
                def generate():
                    try:
                        response = requests.post(model_config['url'], headers=headers, json=payload, stream=True)
                        if response.status_code >= 300:
                            logging.warning(f'LLM Call failed with response code {response.status_code} and message {response.text}')
                            yield f"Error: LLM call failed with status code {response.status_code}\n".encode()
                            return
                        
                        for chunk in response.iter_content(chunk_size=128):
                            yield chunk
                            
                    except Exception as e:
                        logging.error(traceback.format_exc())
                        yield f"An error occurred during streaming: {e}".encode()
                        
                    finally:
                        if 'response' in locals():
                            response.close()
                
                return app.response_class(generate(), mimetype='text/plain')
            else:
                try:
                    response = requests.post(model_config['url'], headers=headers, json=payload)
                    if response.status_code >= 300:
                        logging.warning(f'LLM Call failed with response code {response.status_code} and message {response.text}')
                    return response.text, response.status_code
                except:
                    logging.error(traceback.format_exc())
        
        except:
            logging.error(traceback.format_exc())

    logging.error('No available models responded')
    return jsonify({"error": "No available models responded"}), 500


if __name__ == '__main__':
    app.run(port=5000)
