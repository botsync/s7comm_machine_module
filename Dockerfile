FROM python:3.8-slim
RUN mkdir app

WORKDIR /app

COPY . /app

RUN pip install -r requirements.txt
RUN pip install sdk_machine_module-0.1.0-py3-none-any.whl

EXPOSE 8080

CMD ["python", "server.py"]