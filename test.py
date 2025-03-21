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

for chunk in completion:
    print(f"{chunk.choices[0].delta.content or ''}", end="", flush=True)
print("")