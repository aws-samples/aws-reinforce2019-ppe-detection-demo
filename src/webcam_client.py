import base64
import json
import time

import boto3
import cv2

CAMERA_ID = 'cam1'
ALARM_ID = 'alarm1'


def resize_bbox(img, bbox):
    return {
        'Left': int(bbox['Left'] * img.shape[1]),
        'Top': int(bbox['Top'] * img.shape[0]),
        'Height': int(bbox['Height'] * img.shape[0]),
        'Width': int(bbox['Width'] * img.shape[1])
    }


def draw_bounding_box(img, bbox, color=(255, 0, 0)):
    pt1 = (bbox['Left'], bbox['Top'])
    pt2 = (bbox['Left'] + bbox['Width'], bbox['Top'] + bbox['Height'])
    cv2.rectangle(img, pt1, pt2, color, thickness=2)


def draw_label(img, bbox, label,
               bg_color=(255, 0, 0), text_color=(255, 255, 255)):
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 1
    thickness = 2
    size = cv2.getTextSize(label, font, font_scale, thickness)[0]

    x, y = (bbox['Left'], bbox['Top'])
    cv2.rectangle(img, (x, y-size[1]), (x+size[0], y), bg_color, cv2.FILLED)
    cv2.putText(img, label, (x, y), font, font_scale, text_color, thickness)


def annotate_frame(frame, response_dict):
    labels_to_annotate = {
        'Person': (255, 0, 0),  # cv2 is BGR, so this is blue
        'Helmet': (0, 255, 0)
    }

    for label, color in labels_to_annotate.items():
        for p in response_dict['labels'][label]['Instances']:
            bbox = resize_bbox(frame, p['BoundingBox'])
            draw_bounding_box(frame, bbox, color)

    # Draw label
    if response_dict['compliant']:
        draw_label(frame, dict(Left=0, Top=22), 'Protected', (255, 0, 0))
    else:
        draw_label(frame, dict(Left=0, Top=22), 'Not protected', (0, 0, 255))


def detect_ppe(frame, lambda_client):
    # Resize frame to 1/2 for faster processing
    small = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)

    # Encode to JPG and send to lambda
    ret, encoded = cv2.imencode('.jpg', small)
    if not ret:
        raise RuntimeError('Failed to encode frame')

    account_id = boto3.client('sts').get_caller_identity().get('Account')
    response = lambda_client.invoke(
        FunctionName=f'ppe-detection-function-{account_id}',
        InvocationType='RequestResponse',
        Payload=json.dumps({
            'camera_ID': CAMERA_ID,
            'alarm_ID': ALARM_ID,
            'img': base64.b64encode(encoded).decode('utf-8')
        }))

    # Annotate bounding boxes to frame
    response_dict = json.loads(response['Payload'].read())
    if 'FunctionError' not in response:
        annotate_frame(frame, response_dict)
    else:
        print(response_dict['errorMessage'])


if __name__ == '__main__':
    client = boto3.client('lambda')

    cap = cv2.VideoCapture(0)
    time.sleep(1)  # just to avoid that initial black frame

    frame_skip = 30
    frame_count = 0

    while True:
        # Grab a single frame of video
        ret, frame = cap.read()
        if not ret:
            raise RuntimeError('Failed to capture frame')

        if frame_count % frame_skip == 0:  # only analyze every n frames
            detect_ppe(frame, client)
            cv2.imshow("Press ESC or Q to quit", frame)

        frame_count += 1

        # Press ESC or 'q' to quit
        k = cv2.waitKey(1) & 0xFF
        if k == 27 or k == ord('q'):
            break

    # When everything done, release the capture
    cap.release()
    cv2.destroyAllWindows()
