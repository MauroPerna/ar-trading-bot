FROM python:3.11-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN pip install --no-cache-dir poetry
COPY pyproject.toml poetry.lock* /app/
# Agregar --no-root para no instalar el proyecto actual
RUN poetry config virtualenvs.create false && poetry install --no-interaction --no-ansi --no-root
COPY . /app
EXPOSE 8000
CMD ["uvicorn","src.application.app:app","--host","0.0.0.0","--port","8000","--reload"]