from pyspark.sql import SparkSession
from pyspark.sql.types import (
    StructType,
    StructField,
    StringType,
    IntegerType,
    TimestampType,
    DoubleType,
)
from pyspark.sql.functions import from_json, col
import os
from dotenv import load_dotenv

load_dotenv()


def main():
    spark = (
        SparkSession.builder.appName("TransitFlow")
        .config(
            "spark.jars.packages",
            "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,"
            "org.apache.hadoop:hadoop-aws:3.3.1,"
            "com.amazonaws:aws-java-sdk:1.11.469",
        )
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
        .config("spark.hadoop.fs.s3a.access.key", os.getenv("AWS_ACCESS_KEY_ID"))
        .config(
            "spark.hadoop.fs.s3a.secret.key",
            os.getenv("AWS_SECRET_ACCESS_KEY"),
        )
        .config(
            "spark.hadoop.fs.s3a.aws.credentials.provider",
            "org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider",
        )
        .getOrCreate()
    )

    # Adjust Log Level to minimize the console output --> Only the neccessary stuff

    spark.sparkContext.setLogLevel("WARN")

    # Vehicle Schema
    vehicle_schema = StructType(
        [
            StructField("id", StringType(), True),
            StructField("deviceId", StringType(), True),
            StructField("timestamp", TimestampType(), True),
            StructField("location", StringType(), True),
            StructField("speed", DoubleType(), True),
            StructField("direction", StringType(), True),
            StructField("make", StringType(), True),
            StructField("model", StringType(), True),
            StructField("year", IntegerType(), True),
            StructField("fuelType", StringType(), True),
        ]
    )

    # GPS Schema
    gps_schema = StructType(
        [
            StructField("id", StringType(), True),
            StructField("deviceId", StringType(), True),
            StructField("timestamp", TimestampType(), True),
            StructField("speed", DoubleType(), True),
            StructField("direction", StringType(), True),
            StructField("vehicleType", StringType(), True),
        ]
    )

    # Traffic Schema
    traffic_schema = StructType(
        [
            StructField("id", StringType(), True),
            StructField("deviceId", StringType(), True),
            StructField("cameraId", StringType(), True),
            StructField("location", StringType(), True),
            StructField("timestamp", TimestampType(), True),
            StructField("snapshot", StringType(), True),
        ]
    )

    # Weather Data Schema
    weather_schema = StructType(
        [
            StructField("id", StringType(), True),
            StructField("deviceId", StringType(), True),
            StructField("location", StringType(), True),
            StructField("timestamp", TimestampType(), True),
            StructField("temperature", DoubleType(), True),
            StructField("weatherCondition", StringType(), True),
            StructField("precipitation", DoubleType(), True),
            StructField("windSpeed", DoubleType(), True),
            StructField("humidity", IntegerType(), True),
            StructField("airQualityIndex", DoubleType(), True),
        ]
    )

    # Emergency Schema
    emergency_schema = StructType(
        [
            StructField("id", StringType(), True),
            StructField("deviceId", StringType(), True),
            StructField("incidentId", StringType(), True),
            StructField("type", StringType(), True),
            StructField("timestamp", TimestampType(), True),
            StructField("location", StringType(), True),
            StructField("status", StringType(), True),
            StructField("description", StringType(), True),
        ]
    )

    def read_kafka_topic(topic, schema):
        return (
            spark.readStream.format("kafka")
            .option("kafka.bootstrap.servers", "broker:29092")
            .option("subscribe", topic)
            .option("startingOffsets", "latest")
            .option("failOnDataLoss", "false")
            .load()
            .selectExpr("CAST(value AS STRING)")
            .select(from_json(col("value"), schema).alias("data"))
            .select("data.*")
            .withWatermark("timestamp", "2 minutes")
        )

    def stream_writer(df, checkpoint_folder, output):
        return (
            df.writeStream.format("parquet")
            .option("checkpointLocation", checkpoint_folder)
            .option("path", output)
            .outputMode("append")
            .start()
        )

    vehicle_df = read_kafka_topic("vehicle_data", vehicle_schema).alias("vehicle")
    gps_df = read_kafka_topic("gps_data", gps_schema).alias("gps")
    weather_df = read_kafka_topic("weather_data", weather_schema).alias("weather")
    traffic_df = read_kafka_topic("traffic_data", traffic_schema).alias("traffic")
    emergency_df = read_kafka_topic("emergency_data", emergency_schema).alias(
        "emergency"
    )

    # Join all the DF with id and timestamp
    # joinDF

    queries = [
        stream_writer(
            vehicle_df,
            f"s3a://{os.getenv('S3_BUCKET_NAME')}/{os.getenv('S3_PRFEIX')}/checkpoints/vehicle_data",
            f"s3a://{os.getenv('S3_BUCKET_NAME')}/{os.getenv('S3_PRFEIX')}/data/vehicle_data",
        ),
        stream_writer(
            gps_df,
            f"s3a://{os.getenv('S3_BUCKET_NAME')}/{os.getenv('S3_PRFEIX')}/checkpoints/gps_data",
            f"s3a://{os.getenv('S3_BUCKET_NAME')}/{os.getenv('S3_PRFEIX')}/data/gps_data",
        ),
        stream_writer(
            weather_df,
            f"s3a://{os.getenv('S3_BUCKET_NAME')}/{os.getenv('S3_PRFEIX')}/checkpoints/weather_data",
            f"s3a://{os.getenv('S3_BUCKET_NAME')}/{os.getenv('S3_PRFEIX')}/data/weather_data",
        ),
        stream_writer(
            traffic_df,
            f"s3a://{os.getenv('S3_BUCKET_NAME')}/{os.getenv('S3_PRFEIX')}/checkpoints/traffic_data",
            f"s3a://{os.getenv('S3_BUCKET_NAME')}/{os.getenv('S3_PRFEIX')}/data/traffic_data",
        ),
        stream_writer(
            emergency_df,
            f"s3a://{os.getenv('S3_BUCKET_NAME')}/{os.getenv('S3_PRFEIX')}/checkpoints/emergency_data",
            f"s3a://{os.getenv('S3_BUCKET_NAME')}/{os.getenv('S3_PRFEIX')}/data/emergency_data",
        ),
    ]

    for q in queries:
        q.awaitTermination()


if __name__ == "__main__":
    main()
