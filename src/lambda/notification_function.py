import base64
import io
import json
import os
from datetime import datetime

import boto3
from PIL import Image, ImageDraw

# Global
S3CLIENT = boto3.client('s3')
SNSCLIENT = boto3.client('sns')

BUCKET = os.environ['data_bucket']
SNS_TOPIC = os.environ['sns_topic']
PREFIX_ETL_IMG = 'images/'
PREFIX_ETL_CSV = 'responses/'


def build_filename(timestamp, camera_ID):
    # 2019-03-05T20-11-22
    ftime = timestamp.strftime('%Y-%m-%dT%H-%M-%S')
    return f'{ftime}-{camera_ID}'


def resize_bbox(img, bbox):
    width, height = img.size
    return {
        'Left': int(bbox['Left'] * width),
        'Top': int(bbox['Top'] * height),
        'Height': int(bbox['Height'] * height),
        'Width': int(bbox['Width'] * width)
    }


def draw_bounding_box(draw, bbox, color='#FF0000'):
    pt1 = (bbox['Left'], bbox['Top'])
    pt2 = (bbox['Left'] + bbox['Width'], bbox['Top'] + bbox['Height'])

    draw.rectangle([pt1, pt2], outline=color, width=2)


def annotate_img(img, labels):
    image = Image.open(io.BytesIO(img))
    draw = ImageDraw.Draw(image)

    labels_to_annotate = {
        'Person': '#0000FF',  # blue
        'Helmet': '#00FF00'   # green
    }

    for label, color in labels_to_annotate.items():
        for p in labels[label]['Instances']:
            bbox = resize_bbox(image, p['BoundingBox'])
            draw_bounding_box(draw, bbox, color)

    buffer = io.BytesIO()
    image.save(buffer, 'JPEG')
    buffer.seek(0)

    return buffer


def upload_img_to_s3(img, base_key):
    key = PREFIX_ETL_IMG + base_key + '.jpg'
    S3CLIENT.put_object(Body=img,
                        Bucket=BUCKET,
                        Key=key,
                        ACL='public-read',
                        ContentType='image/jpeg')

    return f'https://{BUCKET}.s3.amazonaws.com/{key}'


def upload_response_to_s3(response, base_key):
    key = PREFIX_ETL_CSV + base_key + '.csv'
    S3CLIENT.put_object(Body=response,
                        Bucket=BUCKET,
                        Key=key)

    return f'https://{BUCKET}.s3.amazonaws.com/{key}'


def send_notification(timestamp, camera_ID, s3_path):
    # Mar 5, 2019, 8:11:22 PM (GMT)
    ftime = timestamp.strftime('%b %-d, %Y, %-I:%M:%S %p (GMT)')

    return SNSCLIENT.publish(
        TopicArn=SNS_TOPIC,
        MessageStructure='json',
        Subject=f'Alert: worker without PPE caught on {camera_ID}',
        Message=json.dumps({
            'default': f'Alert: worker without PPE caught on {s3_path}',
            'email': f'Camera: {camera_ID}\nDate: {ftime}\nImage: {s3_path}',
        })
    )


def lambda_handler(event, context):
    # Extract and transform
    camera_ID = event['camera_ID']
    img = base64.b64decode(event['img'])
    labels = event['labels']
    timestamp = datetime.fromisoformat(event['timestamp'])

    base_key = build_filename(timestamp, camera_ID)

    # Annotate and upload image
    buffer = annotate_img(img, labels)
    s3_path = upload_img_to_s3(buffer, base_key)

    # Send SNS notification
    send_notification(timestamp, camera_ID, s3_path)

    # Upload csv file
    response = ','.join([timestamp.date().isoformat(),
                         timestamp.time().isoformat(timespec='seconds'),
                         camera_ID,
                         str(len(labels['Person']['Instances'])),
                         str(len(labels['Helmet']['Instances']))])
    upload_response_to_s3(response, base_key)

    return {
        'statusCode': 200,
        'body': base_key
    }
