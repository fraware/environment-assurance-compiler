FROM python:3.12-slim
WORKDIR /app
COPY app/server.py /app/server.py
COPY migrations /app/migrations
ENV REFUND_SERVICE_HOST=0.0.0.0
ENV REFUND_SERVICE_PORT=8080
EXPOSE 8080
CMD ["python", "/app/server.py"]
