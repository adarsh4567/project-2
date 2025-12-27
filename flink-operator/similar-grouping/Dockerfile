FROM flink:1.18-scala_2.12-java17

USER root

RUN apt-get update && apt-get install -y \
    default-jdk \
    python3 python3-pip python3-venv && \
    ln -s /usr/bin/python3 /usr/bin/python && \
    rm -rf /var/lib/apt/lists/*

# Ensure JAVA_HOME points correctly on ARM64
ENV JAVA_HOME=/usr/lib/jvm/default-java

RUN pip3 install --upgrade pip

RUN pip3 install apache-flink==1.18.0 --timeout=100

RUN pip3 install redis

COPY sample.py /opt/flink/usrlib/sample.py

COPY group.py /opt/flink/usrlib/group.py

COPY flink-sql-connector-kafka-3.0.2-1.18.jar /opt/flink/lib/

COPY kafka-clients-3.6.0.jar /opt/flink/lib/

USER flink

RUN echo "Hello"

ENTRYPOINT ["/docker-entrypoint.sh"]