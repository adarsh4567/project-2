#!/usr/bin/env python3

import logging
import sys
import json
from pyflink.table import EnvironmentSettings, TableEnvironment, DataTypes
from pyflink.table.udf import udf


def main():
    # Create Table Environment
    env_settings = EnvironmentSettings.new_instance().in_streaming_mode().build()
    table_env = TableEnvironment.create(env_settings)

    # Add connector JARs (updated for Flink 1.18 compatibility)
    connector_jars = ";".join([
        "file:///opt/flink/lib/flink-sql-connector-kafka-3.0.2-1.18.jar",
        "file:///opt/flink/lib/jackson-annotations-2.19.0.jar",
        "file:///opt/flink/lib/jackson-core-2.19.0.jar",
        "file:///opt/flink/lib/kafka-clients-3.6.0.jar",
        "file:///opt/flink/lib/bson-4.11.1.jar",
        "file:///opt/flink/lib/mongodb-driver-core-4.11.1.jar",
        "file:///opt/flink/lib/mongodb-driver-sync-4.11.1.jar",
        "file:///opt/flink/lib/jackson-databind-2.19.0.jar",
        "file:///opt/flink/lib/flink-connector-mongodb-1.2.0-1.18.jar"
    ])
    table_env.get_config().get_configuration().set_string("pipeline.jars", connector_jars)

    # Configure checkpointing
   

    # Kafka bootstrap servers
    kafka_servers = "my-cluster-kafka-bootstrap.kafka.svc.cluster.local:9092"

    source_ddl = f"""
        CREATE TABLE source_table (
            userid STRING,
            newsid STRING,
            top_category STRING,
            top_topic STRING,
            categories ARRAY<ROW<id STRING, score DOUBLE>>,
            topics ARRAY<ROW<id STRING, score DOUBLE>>,
            entities ARRAY<ROW<id BIGINT, type STRING>>,
            dwell DOUBLE,
            proctime AS PROCTIME(),
            event_time TIMESTAMP_LTZ(3) METADATA FROM 'timestamp' VIRTUAL,
            WATERMARK FOR event_time AS event_time
        ) WITH (
            'connector' = 'kafka',
            'topic' = 'user-events',
            'properties.bootstrap.servers' = '{kafka_servers}',
            'properties.group.id' = 'pyflink-consumer-group',
            'scan.startup.mode' = 'latest-offset',
            'value.format' = 'json',
            'value.json.fail-on-missing-field' = 'false',
            'value.json.ignore-parse-errors' = 'true'
        )
    """


    mongodb_sink_ddl = """
        CREATE TABLE mongo_sink_table (
            userid STRING,
            top_category STRING,
            top_topic STRING,
            window_start TIMESTAMP_LTZ(3),
            window_end TIMESTAMP_LTZ(3),
            short_term STRING,
            PRIMARY KEY (userid) NOT ENFORCED
        ) WITH (
            'connector' = 'mongodb',
            'uri' = 'mongodb://admin:password@mongodb-service.mongodb.svc.cluster.local:27017',
            'database' = 'flinkdb',
            'collection' = 'user_data'
        )
    """

    table_env.execute_sql(source_ddl)
    table_env.execute_sql(mongodb_sink_ddl)

    window_transform_query = """
        INSERT INTO mongo_sink_table
        SELECT
            c.userid,
            c.top_category,
            c.top_topic,
            c.window_start,
            c.window_end,
            CONCAT('{"categories":', c.categories_json, ', "topics":', t.topics_json, ', "entities":', e.entities_json, '}') AS short_term
        FROM (
            SELECT
                userid,
                top_category,
                top_topic,
                window_start,
                window_end,
                CONCAT('[', LISTAGG(CONCAT('{"category_id":"', category_id, '","cnt":', CAST(cnt AS STRING), '}'), ','), ']') AS categories_json
            FROM (
                SELECT
                    userid,
                    top_category,
                    top_topic,
                    category_id,
                    cnt,
                    window_start,
                    window_end
                FROM (
                    SELECT
                        userid,
                        top_category,
                        top_topic,
                        category_id,
                        COUNT(*) AS cnt,
                        window_start,
                        window_end,
                        ROW_NUMBER() OVER (
                            PARTITION BY
                                userid,
                                top_category,
                                top_topic,
                                window_start,
                                window_end
                            ORDER BY COUNT(*) DESC
                        ) AS rn
                    FROM (
                        SELECT 
                            userid,
                            top_category,
                            top_topic,
                            id AS category_id,
                            window_start,
                            window_end
                        FROM TABLE(TUMBLE(TABLE source_table, DESCRIPTOR(event_time), INTERVAL '15' SECONDS))
                        CROSS JOIN UNNEST(categories) AS t (id, score)
                        WHERE score >= 0.4 AND dwell >= 3
                    )
                    GROUP BY
                        userid,
                        top_category,
                        top_topic,
                        category_id,
                        window_start,
                        window_end
                )
                WHERE rn <= 3
            )
            GROUP BY userid, top_category, top_topic, window_start, window_end
        ) c
        JOIN (
            SELECT
                userid,
                top_category,
                top_topic,
                window_start,
                window_end,
                CONCAT('[', LISTAGG(CONCAT('{"topic_id":"', topic_id, '","cnt":', CAST(cnt AS STRING), '}'), ','), ']') AS topics_json
            FROM (
                SELECT
                    userid,
                    top_category,
                    top_topic,
                    topic_id,
                    cnt,
                    window_start,
                    window_end
                FROM (
                    SELECT
                        userid,
                        top_category,
                        top_topic,
                        topic_id,
                        COUNT(*) AS cnt,
                        window_start,
                        window_end,
                        ROW_NUMBER() OVER (
                            PARTITION BY
                                userid,
                                top_category,
                                top_topic,
                                window_start,
                                window_end
                            ORDER BY COUNT(*) DESC
                        ) AS rn
                    FROM (
                        SELECT 
                            userid,
                            top_category,
                            top_topic,
                            id AS topic_id,
                            window_start,
                            window_end
                        FROM TABLE(TUMBLE(TABLE source_table, DESCRIPTOR(event_time), INTERVAL '15' SECONDS))
                        CROSS JOIN UNNEST(topics) AS t (id, score)
                        WHERE dwell >= 3
                    )
                    GROUP BY
                        userid,
                        top_category,
                        top_topic,
                        topic_id,
                        window_start,
                        window_end
                )
                WHERE rn <= 3
            )
            GROUP BY userid, top_category, top_topic, window_start, window_end
        ) t
        ON c.userid = t.userid
        AND c.top_category = t.top_category
        AND c.top_topic = t.top_topic
        AND c.window_start = t.window_start
        AND c.window_end = t.window_end
        JOIN (
            SELECT
                userid,
                top_category,
                top_topic,
                window_start,
                window_end,
                CONCAT('[', LISTAGG(CONCAT('"', CAST(entity_id AS STRING), '"'), ','), ']') AS entities_json
            FROM (
                SELECT DISTINCT
                    userid,
                    top_category,
                    top_topic,
                    id AS entity_id,
                    window_start,
                    window_end
                FROM TABLE(TUMBLE(TABLE source_table, DESCRIPTOR(event_time), INTERVAL '15' SECONDS))
                CROSS JOIN UNNEST(entities) AS t (id, type)
                WHERE type = 'organization' AND dwell >= 3
            )
            GROUP BY userid, top_category, top_topic, window_start, window_end
        ) e
        ON c.userid = e.userid
        AND c.top_category = e.top_category
        AND c.top_topic = e.top_topic
        AND c.window_start = e.window_start
        AND c.window_end = e.window_end
    """

    table_result = table_env.execute_sql(window_transform_query)
    table_result.wait()


if __name__ == '__main__':
    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(message)s")
    main()