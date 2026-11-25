FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /studio
RUN useradd --system --uid 10001 --create-home studio && mkdir -p /studio/var && chown studio:studio /studio/var
COPY atlas /studio/atlas
USER studio
EXPOSE 8764
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s CMD python -c "import json,urllib.request; r=json.load(urllib.request.urlopen('http://127.0.0.1:8764/api/v1/health',timeout=3));assert r['worker'] and r['status']=='ok'"
CMD ["python", "-m", "atlas", "serve", "--bind", "0.0.0.0"]
