FROM pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime

WORKDIR /app
RUN pip install --no-cache-dir fastapi==0.115.8 uvicorn==0.34.0 \
    && useradd --system --uid 10001 --create-home app
COPY app.py ./app.py
RUN chown -R app:app /app
USER app
EXPOSE 8001
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8001"]

