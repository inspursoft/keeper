FROM python:3.6-slim-jessie
MAINTAINER wangkun_lc@inspur.com

RUN mkdir /keeper /keeper/instance

COPY setup.py /keeper/setup.py
COPY keeper /keeper/keeper

WORKDIR /keeper
RUN pip install -e .

WORKDIR /
VOLUME [ "/keeper/instance" ]
EXPOSE 5000

ENV FLASK_APP keeper
ENV FLASK_ENV development

CMD [ "flask", "run", "-h", "0.0.0.0"]
