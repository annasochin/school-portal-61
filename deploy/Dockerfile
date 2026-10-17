FROM python:3.12-slim

WORKDIR /srv/portal
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Данные (school.db и uploads) храним в /data — это том Docker
ENV DATA_DIR=/data
ENV SECRET_KEY=change-me-to-a-long-random-string
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
