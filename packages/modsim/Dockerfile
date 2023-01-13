ARG PYTHON_TAG="3.8-slim-buster"
FROM python:$PYTHON_TAG
ARG APP_TAG="0.3.0"
WORKDIR /app

RUN pip install modsim==$APP_TAG

CMD ["modsim"]
