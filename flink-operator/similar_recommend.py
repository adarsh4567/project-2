import logging
import sys
from pyflink.table import EnvironmentSettings, TableEnvironment

def main():
    env_settings = EnvironmentSettings.new_instance().in_streaming_mode().build()
    table_env = TableEnvironment.create(env_settings)

    connector_jars = ";".join([
        "file:///opt/flink/lib/flink-sql-connector-kafka-3.0.2-1.18.jar",
        "file:///opt/flink/lib/jackson-annotations-2.19.0.jar",
        "file:///opt/flink/lib/jackson-core-2.19.0.jar",
        "file:///opt/flink/lib/kafka-clients-3.6.0.jar",
        "file:///opt/flink/lib/jackson-databind-2.19.0.jar",
        "file:///opt/flink/lib/flink-http-connector-0.19.0.jar"
    ])

    table_env.get_config().get_configuration().set_string("pipeline.jars", connector_jars)

    
    kafka_servers = "my-cluster-kafka-bootstrap.kafka.svc.cluster.local:9092"

    source_ddl = f"""
        CREATE TABLE source_table (
            userid STRING,
            newsid STRING,
            top_category STRING,
            top_topic STRING,                              
            proctime AS PROCTIME(),
            event_time TIMESTAMP_LTZ(3) METADATA FROM 'timestamp' VIRTUAL,
            WATERMARK FOR event_time AS event_time
        ) WITH (
            'connector' = 'kafka',
            'topic' = 'user-events',
            'properties.bootstrap.servers' = '{kafka_servers}',
            'properties.group.id' = 'pyflink-consumer-group',
            'scan.startup.mode' = 'latest-offset',
            'format' = 'json',
            'json.timestamp-format.standard' = 'ISO-8601'
        )
    """

    api_lookup = """
            CREATE TABLE api_lookup (
                newsid STRING,
                top_category STRING,
                top_topic STRING,
                results ARRAY<ROW<
                    id BIGINT,
                    title STRING,
                    description STRING,
                    body STRING
                >>,
                PRIMARY KEY (newsid) NOT ENFORCED
            ) WITH (
                'connector' = 'rest-lookup',
                'format' = 'json',
                'url' = 'https://api.apitube.io/v1/news/everything?api_key=api_live_Nflbtv4UQKq5LD8N4LFhJvRuzqzBPqlNCTk6D4TL&language.code=en',
                'asyncPolling' = 'true',
                'gid.connector.http.request.query-param-fields' = 'top_category:category.id,top_topic:topic.id'
            )
    """

    similar_sink_ddl = f"""
        CREATE TABLE similar_sink_table (
            newsid STRING,
            results ARRAY<ROW<
                `id` BIGINT,
                `title` STRING,
                `description` STRING,
                `body` STRING
            >>
        ) WITH (
            'connector' = 'kafka',
            'topic' = 'processed-events',
            'properties.bootstrap.servers' = '{kafka_servers}',
            'format' = 'json',
            'json.timestamp-format.standard' = 'ISO-8601'
        )
    """

    table_env.execute_sql(source_ddl)
    table_env.execute_sql(api_lookup)
    table_env.execute_sql(similar_sink_ddl)


    transform_query = """
            INSERT INTO similar_sink_table
            SELECT 
                s.newsid,
                l.results
            FROM source_table as s
            LEFT JOIN api_lookup FOR SYSTEM_TIME AS OF s.proctime AS l
            ON s.top_category = l.top_category AND s.top_topic = l.top_topic
            WHERE l.results IS NOT NULL
    """

    table_result = table_env.execute_sql(transform_query)
    table_result.wait()


if __name__ == '__main__':
    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(message)s")
    main()    














