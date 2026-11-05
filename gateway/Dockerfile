FROM python:3.12-slim
WORKDIR /srv/gateway
COPY gateway/pyproject.toml ./
COPY gateway/app ./app
RUN pip install --no-cache-dir .
COPY shared /srv/shared
ENV PRICING_PATH=/srv/shared/pricing/models.json
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "2"]
