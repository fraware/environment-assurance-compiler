FROM python:3.12-slim
WORKDIR /app
# Install a released envassure wheel in real images; editable for local scaffolds.
COPY . /app
RUN pip install --no-cache-dir "openenv==0.4.1" "gymnasium>=0.29" \
    && pip install --no-cache-dir -e /app 2>/dev/null || true
ENV PYTHONUNBUFFERED=1
CMD ["python", "server/environment.py"]
