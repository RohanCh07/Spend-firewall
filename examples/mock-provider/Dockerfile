FROM python:3.12-slim
RUN pip install --no-cache-dir fastapi "uvicorn[standard]"
COPY examples/mock-provider/server.py /srv/server.py
WORKDIR /srv
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "9000"]
