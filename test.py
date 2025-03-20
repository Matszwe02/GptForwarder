from openai import OpenAI

client = OpenAI(
  base_url="http://localhost:5000/api/v1",
  api_key="any_key_if_undefined",
)

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
        print(chunk.choices[0].delta.content or "", end="", flush=True)
    print()
except Exception as e:
    print(f"Error in test_forwarder: {e}")
