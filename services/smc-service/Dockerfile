FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY services/smc-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY services/smc-service/src src
COPY config/scenario-templates scenario-templates
RUN useradd --system --uid 10001 app && chown -R app /app
USER app
EXPOSE 8010
CMD ["uvicorn","src.app:app","--host","0.0.0.0","--port","8010"]
