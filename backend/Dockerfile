FROM mcr.microsoft.com/playwright/python:v1.48.0-jammy
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY api /app/api
ENV PYTHONUNBUFFERED=1 \
    PORT=8000
EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
