FROM python:3.11-slim

WORKDIR /app

# Install deps first so this layer caches independently of code changes
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py solar_system.py exoplanets.py .

# Ephemeris cache (de421.bsp, ~17MB) lands here on first pass-prediction
# request — mount this as a volume in docker-compose so it isn't
# re-downloaded every time the container restarts.
RUN mkdir -p /app/skyfield-data

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
