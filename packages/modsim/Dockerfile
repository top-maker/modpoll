ARG PYTHON_TAG="3.8-slim-buster"
FROM python:$PYTHON_TAG
ARG APP_TAG="0.3.0"
WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip3 install -r requirements.txt

COPY . .

CMD [ "python3", "main.py"]
