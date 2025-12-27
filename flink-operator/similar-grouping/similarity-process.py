from pyflink.common.typeinfo import Types
from pyflink.common import Time, Row
from pyflink.datastream import StreamExecutionEnvironment, RuntimeContext
from pyflink.datastream.state import MapStateDescriptor
from pyflink.datastream.connectors.kafka import FlinkKafkaConsumer,FlinkKafkaProducer
from pyflink.datastream.formats.json import JsonRowDeserializationSchema,JsonRowSerializationSchema
from pyflink.datastream.window import TumblingEventTimeWindows
from pyflink.datastream.functions import ProcessWindowFunction, KeyedProcessFunction
from pyflink.common.watermark_strategy import WatermarkStrategy, TimestampAssigner
from pyflink.common import Duration
from typing import Dict, Set, Iterable
import redis

# Debug ProcessFunction to see watermarks and data flow

# CORRECTED: Calculate Jaccard similarity across ALL users in each window
class JaccardSimilarity(ProcessWindowFunction):

    def open(self,context:RuntimeContext):
        self.redis_client = redis.Redis(host='redis-service.default.svc.cluster.local', port=6379,decode_responses=True)
        try:
            print("Connected to Redis!")
        except redis.ConnectionError as e:
            print(f"Failed to connect to Redis: {e}")
            raise e

    def process(self, key, context, elements: Iterable) -> Iterable:
        print(f"DEBUG - Window fired! Key: {key}, Window: {context.window()}")
        
        user_interests: Dict[str, Dict[str,Set[str]]] = {}
        
        # Collect all interests for each user in the window
        for ele in elements:
            userid = ele[0]
            interests = set(ele[1]) if ele[1] else set()
    
            user_interests[userid] = {
                "interests": interests
            }

        
        userids = list(user_interests.keys())
        
        # If less than 2 users, no pairs to compare
        if len(userids) < 2:
            print(f"DEBUG - Not enough users ({len(userids)}) for similarity calculation")
            return
        
        # Calculate Jaccard similarity for all user pairs
        for i in range(len(userids)):
            for j in range(i+1, len(userids)):
                u1, u2 = userids[i], userids[j]
                u1group = self.redis_client.lrange(u1,0,-1)
                u2group = self.redis_client.lrange(u2,0,-1)
                if u1 in u2group and u2 in u1group:
                    print(f"DEBUG - Continued for {u1} and {u2}")
                    continue
                set1 = user_interests[u1]["interests"]
                set2 = user_interests[u2]["interests"]
                intersect_for_group = list(set1 & set2)
                intersection = len(set1 & set2)
                union = len(set1 | set2)
                similarity = (intersection / union if union > 0 else 0.0) * 100

                result = Row(grouped=[u1,u2],content=intersect_for_group)

                if similarity > 50:
                    print(f"DEBUG - Result : {u1} <-> {u2} and similarity - {similarity}")
                    yield result 



# TimestampAssigner: Uses Kafka record_timestamp for event time
class MyTimestampAssigner(TimestampAssigner):
    def extract_timestamp(self, element, record_timestamp) -> int:
        # Returns Kafka message timestamp (ms) for event time
        timestamp = int(record_timestamp) if record_timestamp else 0
        return timestamp


# Setup execution environment
env = StreamExecutionEnvironment.get_execution_environment()
env.set_parallelism(1)  # IMPORTANT: Set to 1 or match Kafka partition count

# Set watermark interval
env.get_config().set_auto_watermark_interval(200)

# Add Kafka jars
connector_jars = ";".join([
    "file:///opt/flink/lib/flink-sql-connector-kafka-3.0.2-1.18.jar",
    "file:///opt/flink/lib/kafka-clients-3.6.0.jar"
])
env.add_jars(connector_jars)

# Input/Output row types
row_type = Types.ROW_NAMED(
    ["userid", "interests"],
    [Types.STRING(), Types.BASIC_ARRAY(Types.STRING())]
)

row_type_output = Types.ROW_NAMED(
    ["grouped","content"],
    [Types.BASIC_ARRAY(Types.STRING()),Types.BASIC_ARRAY(Types.STRING())]
)

# Configure Kafka consumer
deserialization_schema = JsonRowDeserializationSchema.builder().type_info(row_type).build()

kafka_consumer = FlinkKafkaConsumer(
    topics=["user-events"],
    deserialization_schema=deserialization_schema,
    properties={
        'bootstrap.servers': 'my-cluster-kafka-bootstrap.kafka.svc.cluster.local:9092',
        'group.id': 'pyflink-consumer-new-group',
        'auto.offset.reset': 'latest'  # Start from beginning
    }
)

serialization_schema = JsonRowSerializationSchema.builder().with_type_info(type_info=row_type_output).build()

kafka_producer = FlinkKafkaProducer(
    topic="output-signal",
    serialization_schema=serialization_schema,
    producer_config={
        'bootstrap.servers': 'my-cluster-kafka-bootstrap.kafka.svc.cluster.local:9092',
        'group.id': 'pyflink-producer-group'
    }

)

# Watermark strategy (1 second out-of-orderness)
wm_strategy = (WatermarkStrategy
               .for_bounded_out_of_orderness(Duration.of_seconds(1))
               .with_timestamp_assigner(MyTimestampAssigner()))

# Build pipeline
ds = (env
      .add_source(kafka_consumer)
      .assign_timestamps_and_watermarks(wm_strategy))

# Add debug to see incoming data and watermarks

calculated_window = (ds
                     .key_by(lambda x: "all_users", key_type=Types.STRING())  # FIXED: Single key for all
                     .window(TumblingEventTimeWindows.of(Time.seconds(15)))
                     .process(JaccardSimilarity(), output_type=row_type_output))

# Print results
calculated_window.add_sink(kafka_producer)

print("Starting Flink job - Check console for DEBUG output...")
env.execute("User Events Jaccard Similarity")