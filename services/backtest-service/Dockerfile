FROM python:3.13-slim
WORKDIR /app
COPY services/backtest-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY services/backtest-service/src src
COPY services/smc-service/src smc_core
COPY config/scenario-templates default-scenario-templates
RUN useradd --system --uid 10008 app && chown -R app /app
USER app
EXPOSE 8080
CMD ["uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "8080"]
