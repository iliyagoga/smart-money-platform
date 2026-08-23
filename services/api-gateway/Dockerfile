FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src src
RUN useradd --system --uid 10005 app && chown -R app /app
USER app
EXPOSE 8050
CMD ["uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "8050"]

