FROM python:3.12-slim
WORKDIR /app
COPY requirements-server.txt .
RUN pip install --no-cache-dir -r requirements-server.txt
COPY server.py .
COPY web ./web
RUN mkdir -p /app/data
ENV PORT=8080
ENV POLL_SECONDS=300
EXPOSE 8080
CMD ["python","server.py"]
