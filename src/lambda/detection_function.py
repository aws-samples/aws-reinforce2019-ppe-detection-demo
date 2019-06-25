import base64
import json
import os
from datetime import datetime

import boto3

REKOGNITION = boto3.client('rekognition')
IOT_DATA = boto3.client('iot-data')
LAMBDA = boto3.client('lambda')

IOT_TOPIC = os.environ['iot_topic']
NOTIFICATION_FUNCTION_NAME = os.environ['notification_function_name']


def invoke_notifications(camera_ID, timestamp, img, labels):
    return LAMBDA.invoke(
        FunctionName=NOTIFICATION_FUNCTION_NAME,
        InvocationType='Event',
        Payload=json.dumps({
            'camera_ID': camera_ID,
            'timestamp': timestamp.isoformat(),
            'img': img,
            'labels': labels
        }))


def iot_publish(camera_ID, alarm_ID):
    return IOT_DATA.publish(
        topic=IOT_TOPIC,
        qos=1,  # At least once delivery
        payload=json.dumps({
            'camera_ID': camera_ID,
            'alarm_ID': alarm_ID
        })
    )


def get_label(response, label):
    for l in response['Labels']:
        if l['Name'] == label:
            return l

    return {
        'Name': label,
        'Instances': []
    }


def detect_labels(img):
    response = REKOGNITION.detect_labels(Image={'Bytes': img})

    return {
        'Person': get_label(response, 'Person'),
        'Helmet': get_label(response, 'Helmet')
    }


def is_compliant(labels):
    num_person = len(labels['Person']['Instances'])
    num_helmet = len(labels['Helmet']['Instances'])

    if num_person <= num_helmet:
        return True

    return False


def lambda_handler(event, context):
    # Extract and transform
    camera_ID = event['camera_ID']
    alarm_ID = event['alarm_ID']
    encoded_img = event['img']
    timestamp = datetime.utcnow()

    # Check if equipment is present
    img = base64.b64decode(encoded_img)
    labels = detect_labels(img)
    compliant = is_compliant(labels)

    # Invoke alarm and notifications
    if not compliant:
        iot_publish(camera_ID, alarm_ID)
        invoke_notifications(camera_ID, timestamp, encoded_img, labels)

    return {
        'compliant': compliant,
        'labels': labels,
    }
