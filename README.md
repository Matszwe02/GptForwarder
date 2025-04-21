# GPT-Forwarder

GPT-Forwarder is a lightweight and efficient API forwarder designed to route and manage API requests across multiple language models. It categorizes models, allowing you to direct specific types of requests (e.g., chat, code generation) to the most appropriate models. This system is configured via a simple JSON configuration file, making it easy to set up and customize for various model deployments and API key management scenarios.

## How to run

```bash
docker-compose up -d
```

## How to configure

Edit `config/config.json` to configure models, categories, and API keys.

### Configuration fields:

- `default_category`: The default category to use if not specified in the request.
- `api_keys`: A dictionary of API keys for each category.
- `models`: A list of model configurations. Each model configuration has the following fields:
    - `name`: The name of the model.
    - `url`: The URL of the model's API endpoint.
    - `category`: A list of categories this model belongs to.
    - `api_key`: The API key to use for this model (can be null if no API key is needed).
    - `latch`: (Optional) A boolean (`true`/`false`). If set to `true`, the program can "latch" this model for every request in its categories if it responds reliably. This model will be tried first for subsequent requests in the same category. If the model fails to respond, it will be unlatched and the program will try other available models. Defaults to `false` if not specified.
