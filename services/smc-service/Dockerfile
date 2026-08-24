FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY services/smc-service/requirements.txt .
RUN --mount=type=cache,id=smart-money-pip,target=/root/.cache/pip,sharing=locked \
    pip install -r requirements.txt
COPY services/smc-service/src src
COPY config/scenario-templates default-scenario-templates
RUN useradd --system --uid 10001 app \
    && mkdir -p /app/scenario-templates \
    && chown -R app /app
USER app
EXPOSE 8010
CMD ["uvicorn","src.app:app","--host","0.0.0.0","--port","8010"]
