FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN --mount=type=cache,id=smart-money-pip,target=/root/.cache/pip,sharing=locked \
    pip install -r requirements.txt
COPY src src
RUN useradd --system --uid 10003 app && chown -R app /app
USER app
EXPOSE 8030
CMD ["uvicorn","src.app:app","--host","0.0.0.0","--port","8030"]
