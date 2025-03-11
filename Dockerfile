FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir gunicorn
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY forwarder.py .

EXPOSE 5000
ENV FLASK_APP=main.py
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "forwarder:app"]