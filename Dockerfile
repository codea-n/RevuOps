FROM python:3.12-slim

# Don't run as root inside the container — security best practice
RUN useradd --create-home appuser

WORKDIR /app

# Copy and install dependencies first — Docker layer caching means
# this layer only rebuilds when requirements.txt changes, not on
# every code change. Saves minutes on every deploy.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Switch to non-root user before starting the app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
