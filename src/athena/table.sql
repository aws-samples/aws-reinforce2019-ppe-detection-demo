CREATE EXTERNAL TABLE IF NOT EXISTS ppeDatabase.ppe_non_compliant (
 `Date` string,
 `Time` string,
 `CameraID` string,
 `NPerson` int,
 `NHelmet` int
)
ROW FORMAT SERDE 'org.apache.hadoop.hive.serde2.lazy.LazySimpleSerDe'
WITH SERDEPROPERTIES (
    'serialization.format' = ',',
    'field.delim' = ','
) LOCATION 's3://<YOUR_DATA_BUCKET>/responses/'
