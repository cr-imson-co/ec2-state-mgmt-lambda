#!/usr/bin/env python
'''
#
# cr.imson.co
#
# Automated state management service for EC2 instances
#
# @author Damian Bushong <katana@odios.us>
#
'''

from datetime import datetime
from enum import Enum
import json
import logging
import re
from os import environ

import boto3
import pytz
from aws_xray_sdk.core import patch_all
from pythonjsonlogger import jsonlogger

patch_all()

LAMBDA_NAME = 'ec2-state-mgmt'
logger = logging.getLogger()
logger.setLevel(logging.DEBUG if environ.get('DEBUG_MODE') == 'true' else logging.INFO)

class CustomJsonFormatter(jsonlogger.JsonFormatter):
    '''
    Customizations for JSON formatting
    '''
    def add_fields(self, log_record, record, message_dict):
        '''
        Add level field for our use.
        '''
        super().add_fields(log_record, record, message_dict)

        if log_record.get('level'):
            log_record['level'] = log_record['level'].upper()
        else:
            log_record['level'] = record.levelname

for handler in logger.handlers:
    handler.setFormatter(CustomJsonFormatter(timestamp=True))

if environ.get('CI') != 'true':
    ec2 = boto3.resource('ec2', region_name=environ.get('AWS_REGION'))
    sns = boto3.resource('sns', region_name=environ.get('AWS_REGION'))

# note: time should be specified in 24hr time and according to the configured STATE_MGMT_TIMEZONE
HARDCODED_START = '06:00'.split(':')[0]
HARDCODED_STOP = '18:00'.split(':')[0]
TIME_PATTERN = re.compile('^([01][0-9]|2[0-3]):[0-5][0-9]$')

class StateManagementPhase(Enum):
    ''' Helper enum '''
    PHASE_ONE = 1   # :00 - :14
    PHASE_TWO = 2   # :15 - :29
    PHASE_THREE = 3 # :30 - :44
    PHASE_FOUR = 4  # :45 - :59

class RecoveredError(Exception): # pylint: disable=C0115
    pass

def get_invoke_time(now):
    ''' Get the invocation time. '''
    return now.strftime('%H:%M').split(':')

def check_if_weekend(now):
    ''' Check to see if the specified date is a weekend. '''
    return now.weekday() in [5, 6] # 5-6 are Saturday, Sunday ordinally

def get_hour_phase(current_minute):
    ''' Identifies which segment of the hour the current invocation falls into. '''
    if 0 <= int(current_minute) < 15:
        return StateManagementPhase.PHASE_ONE

    if 15 <= int(current_minute) < 30:
        return StateManagementPhase.PHASE_TWO

    if 30 <= int(current_minute) < 45:
        return StateManagementPhase.PHASE_THREE

    return StateManagementPhase.PHASE_FOUR

def check_tag_time_format(instance, time_type, time_value):
    ''' Check to see if the time specified for an ec2_start or ec2_stop value is correctly formatted. '''
    if not re.match(TIME_PATTERN, time_value):
        logger.warning(f'Instance {instance.id} tag value for "{time_type}" tag is incorrectly formatted, ignoring')
        return False

    return True

def tag_list_to_dict(tags):
    ''' Collapses the list of tags that AWS provides for EC2s down into a simple dict. '''
    return {t['Key']:t['Value'] for t in tags}

def check_configured_time(instance, time_type, minute_value):
    ''' Massages user-specified minute value for ec2_start and ec2_stop to a sane value. '''
    if 0 < int(minute_value) < 15:
        logger.warning(f'Invalid minute specifier for instance {instance.id} {time_type} time (specified :{minute_value}, assuming :00)')
        minute_value = '00'
    elif 15 < int(minute_value) < 30:
        logger.warning(f'Invalid minute specifier for instance {instance.id} {time_type} time (specified :{minute_value}, assuming :15)')
        minute_value = '15'
    elif 30 < int(minute_value) < 45:
        logger.warning(f'Invalid minute specifier for instance {instance.id} {time_type} time (specified :{minute_value}, assuming :30)')
        minute_value = '30'
    elif 45 < int(minute_value) < 60:
        logger.warning(f'Invalid minute specifier for instance {instance.id} {time_type} time (specified :{minute_value}, assuming :45)')
        minute_value = '45'

    return minute_value

def _filter_start_instances(instance, current_hour, hour_phase, is_weekend):
    state = instance.state.get('Name')
    if state != 'stopped':
        logger.debug(f'Instance {instance.id} is not stopped (status: {state}), ignoring')
        return False

    tags = tag_list_to_dict(instance.tags)

    # supports {'ec2_start_on_weekends' => 'true'}
    # notes:
    # - forces start events to process during weekends if the ec2_start_on_weekends tag is set to "true"
    if is_weekend and ('ec2_start_on_weekends' not in tags or tags['ec2_start_on_weekends'].lower() != 'true'):
        logger.debug(f'Instance {instance.id} is not tagged with "ec2_start_on_weekends" and it is a weekend, ignoring')
        return False

    # supports {'ec2_start' => 'XX:00'}, {'ec2_start' => 'XX:15'}, {'ec2_start' => 'XX:30'} and {'ec2_start' => 'XX:45'}
    # notes:
    # - additional specificity in the ec2 tag is ignored! don't try to be cheeky and say XX:48.  it will not be supported.
    if 'ec2_start' in tags:
        logger.debug(f'Instance {instance.id} is tagged with "ec2_start" tag')

        if not check_tag_time_format(instance, 'ec2_start', tags['ec2_start']):
            return False

        tag_hour, tag_minute = tags['ec2_start'].split(':')
        if current_hour == tag_hour:
            tag_minute = check_configured_time(instance, 'ec2_start', tag_minute)

            if ((hour_phase == StateManagementPhase.PHASE_ONE and tag_minute == '00') # pylint: disable=R0916
                or (hour_phase == StateManagementPhase.PHASE_TWO and tag_minute == '15')
                or (hour_phase == StateManagementPhase.PHASE_THREE and tag_minute == '30')
                or (hour_phase == StateManagementPhase.PHASE_FOUR and tag_minute == '45')
            ):
                return True

    # catchall; do not send any start events
    return False

def _filter_stop_instances(instance, current_hour, hour_phase): # pylint: disable=R0911
    '''
    Function to filter out which instances should be stopped, given the current hour and hour_phase (quarter hour)
    '''
    state = instance.state.get('Name')
    if state != 'running':
        logger.debug(f'Instance {instance.id} is not running (status: {state}), ignoring')
        return False

    tags = tag_list_to_dict(instance.tags)

    # supports {'ec2_stop' => 'XX:00'}, {'ec2_stop' => 'XX:15'}, {'ec2_stop' => 'XX:30'} and {'ec2_stop' => 'XX:45'}
    # notes:
    # - additional specificity in the ec2 tag is ignored! don't try to be cheeky and say XX:48.  it will not be supported.
    if 'ec2_stop' in tags:
        logger.debug(f'Instance {instance.id} is tagged with "ec2_stop" tag')

        if not check_tag_time_format(instance, 'ec2_stop', tags['ec2_stop']):
            return False

        tag_hour, tag_minute = tags['ec2_stop'].split(':')
        if current_hour == tag_hour:
            tag_minute = check_configured_time(instance, 'ec2_stop', tag_minute)

            if ((hour_phase == StateManagementPhase.PHASE_ONE and tag_minute == '00') # pylint: disable=too-many-boolean-expressions
                or (hour_phase == StateManagementPhase.PHASE_TWO and tag_minute == '15')
                or (hour_phase == StateManagementPhase.PHASE_THREE and tag_minute == '30')
                or (hour_phase == StateManagementPhase.PHASE_FOUR and tag_minute == '45')
            ):
                return True

    # catchall; do not send any stop events
    return False

def filter_start_instances(instance, current_hour, hour_phase, is_weekend):
    ''' Tiny wrapper around the filter_start_instances function to shim in some extra logging. '''
    result = _filter_start_instances(instance, current_hour, hour_phase, is_weekend)

    if result:
        logger.debug(f'Instance {instance.id} identified as qualifying for sending start event')
    else:
        logger.debug(f'Instance {instance.id} does not qualify for start event, ignoring')

    return result

def filter_stop_instances(instance, current_hour, hour_phase):
    ''' Tiny wrapper around the filter_stop_instances function to shim in some extra logging. '''
    result = _filter_stop_instances(instance, current_hour, hour_phase)

    if result:
        logger.debug(f'Instance {instance.id} identified as qualifying for sending stop event')
    else:
        logger.debug(f'Instance {instance.id} does not qualify for stop event, ignoring')

    return result

def lambda_handler(_event, _context):
    ''' Lambda handler '''
    try:

        timezone = pytz.timezone(environ.get('STATE_MGMT_TIMEZONE') or 'UTC')
        now = datetime.now(timezone)

        current_hour, current_minute = get_invoke_time(now)
        is_weekend = check_if_weekend(now)
        hour_phase = get_hour_phase(current_minute)

        # due to us needing to interact with both started and stopped EC2 instances with
        #   filtering more complex than AWS's APIs can support, it's more efficient to just
        #   get a full instance list and roll with it up front.
        #
        # also, pylint apparently doesn't understand that LAMBDA.ec2 is lazy-loaded...
        instances = list(ec2.instances.all()) # pylint: disable=E1101

        logger.debug(f'Retrieved {len(instances)} instances total')

        start_instances = list(filter(
            lambda instance_list: filter_start_instances(instance_list, current_hour, hour_phase, is_weekend), instances[:]
        ))
        stop_instances = list(filter(
            lambda instance_list: filter_stop_instances(instance_list, current_hour, hour_phase), instances[:]
        ))

        logger.debug(f'Filtered instances to start down to {len(start_instances)} instances total')
        logger.debug(f'Filtered instances to stop down to {len(stop_instances)} instances total')

        failure_count = 0
        if (len(start_instances)) > 0:
            for instance in start_instances:
                logger.info(f'Starting instance {instance.id}')

                try:
                    instance.start()
                except Exception as ex: # pylint: disable=W0703
                    logger.error(f'Failed to start instance {instance.id}', exc_info=ex)
                    failure_count += 1
        else:
            logger.info('No instances to start.')

        if (len(stop_instances)) > 0:
            for instance in stop_instances:
                logger.info(f'Stopping instance {instance.id}')

                try:
                    instance.stop()
                except Exception as ex: # pylint: disable=W0703
                    logger.error(f'Failed to stop instance {instance.id}', exc_info=ex)
                    failure_count += 1
        else:
            logger.info('No instances to stop.')

        if failure_count:
            raise RecoveredError(f'{failure_count} instance control failures occurred')
    except Exception as ex:
        logger.error('Fatal error during script runtime', exc_info=ex)

        if environ.get('NOTIFICATION_ARN'):
            log_stream = environ.get('AWS_LAMBDA_LOG_STREAM_NAME')
            sns.publish(
                TargetArn=environ.get('NOTIFICATION_ARN'),
                Message=json.dumps({'default':
                    json.dumps({
                        'type': 'error',
                        'lambda': LAMBDA_NAME,
                        'message': f'{LAMBDA_NAME} lambda error notification; reference logstream {log_stream}'
                    })
                }),
                MessageStructure='json'
            )

        raise
