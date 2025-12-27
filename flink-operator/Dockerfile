FROM flink:1.18-scala_2.12-java17

USER root

RUN apt-get update && apt-get install -y \
    default-jdk \
    python3 python3-pip python3-venv && \
    ln -s /usr/bin/python3 /usr/bin/python && \
    rm -rf /var/lib/apt/lists/*

# Ensure JAVA_HOME points correctly on ARM64
ENV JAVA_HOME=/usr/lib/jvm/default-java

COPY flink-sql-connector-kafka-3.0.2-1.18.jar /opt/flink/lib/

COPY jackson-annotations-2.19.0.jar /opt/flink/lib/

COPY jackson-core-2.19.0.jar /opt/flink/lib/

COPY jackson-databind-2.19.0.jar /opt/flink/lib/

COPY flink-connector-mongodb-1.2.0-1.18.jar /opt/flink/lib/

COPY mongodb-driver-core-4.11.1.jar /opt/flink/lib/

COPY mongodb-driver-sync-4.11.1.jar /opt/flink/lib/

COPY bson-4.11.1.jar /opt/flink/lib/

COPY kafka-clients-3.6.0.jar /opt/flink/lib/

COPY flink-python-1.18.0.jar /opt/flink/lib/

COPY flink-http-connector-0.19.0.jar /opt/flink/lib/

RUN pip3 install --upgrade pip

RUN pip3 install apache-flink==1.18.0 --timeout=100

COPY short_term_process.py /opt/flink/usrlib/short_term_process.py

COPY medium_term_process.py /opt/flink/usrlib/medium_term_process.py

COPY long_term_process.py /opt/flink/usrlib/long_term_process.py

COPY similar_recommend.py /opt/flink/usrlib/similar_recommend.py

RUN $JAVA_HOME/bin/java -version

COPY config.yaml /opt/flink/conf/config.yaml

RUN chown -R flink:flink /opt/flink/usrlib/

RUN chown flink:flink /opt/flink/conf/config.yaml

USER flink
ENTRYPOINT ["/docker-entrypoint.sh"]
