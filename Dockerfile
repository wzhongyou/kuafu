FROM python:3.12-slim

WORKDIR /app

# Install system deps for lxml
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libxml2-dev libxslt1-dev && \
    rm -rf /var/lib/apt/lists/*

COPY . .

RUN pip install --no-cache-dir -e ".[web]"

EXPOSE 8080

CMD ["kuafu", "--web", "--host", "0.0.0.0", "--port", "8080"]
