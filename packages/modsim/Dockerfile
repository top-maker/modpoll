ARG PYTHON_TAG=3.8-slim-buster

###############################################
# Builder Image
###############################################
FROM helloysd/poetry:$PYTHON_TAG as builder
WORKDIR /app
COPY . /app/

# update dependencies (disable if needed)
RUN poetry update

# # install app
# RUN poetry install --no-dev

# build the app as module
RUN poetry install --no-dev --no-root
RUN poetry build

###############################################
# Final Image
###############################################
FROM python:$PYTHON_TAG as final
WORKDIR /app
COPY --from=builder /app /app

# install the app as module
RUN python -m pip install dist/*.whl

# start the app
CMD ["modsim"]
