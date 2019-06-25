#!/bin/bash

account_id=$(aws sts get-caller-identity --output text --query Account)

usage() {
    echo "usage: $0 <command>"

    echo "Available commands:"
    echo -e "  create\tCreate the PPE demo in your AWS account"
    echo -e "  delete\tDelete the resources created in the previous step"
}

create() {
    set -E -e

    read -p "Please inform an email to receive notifications [youremail@email.com]: " email
    email=${email:-"youremail@email.com"}
    read -p "Please inform the alarm message [You are not protected]: " alarm_message
    alarm_message=${alarm_message:-"You are not protected"}

    echo "Creating requirements stack. This can take about 3 minutes..."
    code_stack_id=$(aws cloudformation create-stack \
        --stack-name ppe-demo-code \
        --template-body file://ppe-cf-template-code.yaml \
        --capabilities CAPABILITY_NAMED_IAM \
        --output text --query StackId)

    code_check_status="aws cloudformation describe-stacks --stack-name $code_stack_id --output text --query Stacks[0].StackStatus"
    code_status=$($code_check_status)
    while [ $code_status != "CREATE_COMPLETE" ]; do
        if [[ $code_status == ROLLBACK_* ]]; then
            echo "Something went wrong. Please check CloudFormation events in the AWS console"
            exit 1
        fi
        sleep 5
        code_status=$($code_check_status)
    done

    echo "Waiting Lambda layer to finish..."
    sleep 60

    zip -q -j detection_function ../src/lambda/detection_function.py
    zip -q -j notification_function ../src/lambda/notification_function.py
    aws s3 cp detection_function.zip s3://ppe-code-bucket-$account_id/ --quiet
    aws s3 cp notification_function.zip s3://ppe-code-bucket-$account_id/ --quiet

    echo "Creating voice alarm..."
    aws polly synthesize-speech \
         --output-format="ogg_vorbis" \
         --text="$alarm_message" \
         --voice-id="Kendra" ../src/iot/not_protected.ogg > /dev/null

    echo "Creating architecture stack. This can take about 3 minutes..."
    architecture_stack_id=$(aws cloudformation create-stack \
        --stack-name ppe-demo-architecture \
        --template-body file://ppe-cf-template-architecture.yaml \
        --capabilities CAPABILITY_NAMED_IAM \
        --parameters ParameterKey=emailSNS,ParameterValue=$email \
        --output text --query StackId)

    architecture_check_status="aws cloudformation describe-stacks --stack-name $architecture_stack_id --output text --query Stacks[0].StackStatus"
    architecture_status=$($architecture_check_status)
    while [ $architecture_status != "CREATE_COMPLETE" ]; do
        if [[ $architecture_status == ROLLBACK_* ]]; then
            echo "Something went wrong. Please check CloudFormation events in the AWS console"
            exit 1
        fi
        sleep 5
        architecture_status=$($architecture_check_status)
    done

    echo "Finished!"
}

delete() {
    echo "Deleting resources..."
    aws s3 rm s3://ppe-code-bucket-$account_id/ --recursive --quiet
    aws cloudformation delete-stack --stack-name ppe-demo-code
    thing_certificates=$(aws iot list-thing-principals --thing-name ppe-raspberry-$account_id --output text --query principals)
    for certificate in $thing_certificates; do
        aws iot detach-thing-principal \
            --thing-name ppe-raspberry-$account_id \
            --principal $certificate
    done
    aws s3 rm s3://ppe-data-bucket-$account_id/ --recursive --quiet
    aws cloudformation delete-stack --stack-name ppe-demo-architecture
}


if [[ $# == 1 ]]; then
    command=$1

    case $command in

    create )
        create
        ;;

    delete )
        delete
        ;;

    * )
        usage
        exit 1

    esac
else
    usage
    exit
fi
