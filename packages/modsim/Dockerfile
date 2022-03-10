ARG PYTHON_TAG="3.6-slim-buster"
FROM python:$PYTHON_TAG
ARG APP_TAG="0.2.2"
WORKDIR /app

RUN pip install modsim==$APP_TAG

CMD ["modsim"]
