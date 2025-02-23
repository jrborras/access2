FROM python:3.12-alpine
WORKDIR /app
COPY ./app/ /app/
RUN pip install --no-cache-dir -r requirements.txt
CMD [ "python3", "/app/app.py" ]