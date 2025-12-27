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
import ast
import json

# Debug ProcessFunction to see watermarks and data flow

# CORRECTED: Calculate Jaccard similarity across ALL users in each window
class JaccardSimilarityForGroups(ProcessWindowFunction):

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
            # existgroups = set(ele[2]) if ele[2] else set()
    
            user_interests[userid] = {
                "interests": interests
                # "existgroups": existgroups
            }

        userids = list(user_interests.keys())

        groupkeys = self.redis_client.keys("groups:*")
        all_groups = [self.redis_client.hgetall(key) for key in groupkeys]

        filtered_groups = [item for item in all_groups if item.get('active') == 'true']


        # result = Row(userid="1",groups=["a"])
        # yield result

        for i in range(len(userids)):
            u1 = userids[i]
            set1 = user_interests[u1]["interests"]
            # exist_groups_for_user = user_interests[u1].get("existgroups", set())
            for g in filtered_groups:
                x = g.get('interests')
                interests_arr = json.loads(x)
                group_id = g.get('id')

                if u1 in group_id:
                    continue

                set2 = set(interests_arr)
                intersection = len(set1 & set2)
                union = len(set1 | set2)
                similarity = (intersection / union if union > 0 else 0.0) * 100

                result = Row(userid=u1, group=group_id)

                # yield result
        
            
                if similarity >= 50:
                    print(f"DEBUG - Result : {result} and similarity - {similarity}")
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
    ["userid","group"],
    [Types.STRING(),Types.STRING()]
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
    topic="output-group-signals",
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
                     .process(JaccardSimilarityForGroups(), output_type=row_type_output))

# Print results
calculated_window.add_sink(kafka_producer)

print("Starting Flink job - Check console for DEBUG output...")
env.execute("User Events Jaccard Similarity")