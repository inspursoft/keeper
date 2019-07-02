FROM python:3.7.3-alpine3.10
MAINTAINER wangkun_lc@inspur.com

COPY setup.py /setup.py
COPY keeper /keeper

ENV FLASK_APP keeper
ENV FLASK_ENV development

RUN pip install -e .
WORKDIR /

VOLUME [ "/instance" ]
EXPOSE 5000

