FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY astraflux ./astraflux
RUN useradd -m app && chown -R app /app
USER app
EXPOSE 7860
HEALTHCHECK CMD python -c "import urllib.request,os;urllib.request.urlopen('http://localhost:%s/api/health'%os.environ.get("PORT","7860"))" || exit 1
CMD ["sh","-c","uvicorn astraflux.api:app --host 0.0.0.0 --port ${PORT:-7860}"]
